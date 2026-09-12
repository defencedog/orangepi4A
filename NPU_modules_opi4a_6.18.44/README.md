# Allwinner T527 (Orange Pi 4A) VIP9000 NPU Activation & Optimization Suite

**Target Board:** Orange Pi 4A / Radxa Cubie A5E (Allwinner T527 / sun55i-t527)  

**NPU Silicon:** VeriSilicon VIP9000nano-di (`ChipID: 0x9000`, `Revision: 0x9003`, `ProductID: 0x5090009`, `CustomerID: 0x10000016`)  

**Operating System:** Linux Kernel `6.18.44-g61025ec85b88` (ARM64 / aarch64)  

**Inference Runtime:** Google LiteRT (`ai_edge_litert`) + Patched Mesa Teflon (`libteflon.so`)  

**Tested on:** [aurealnix-opi4a-ubuntu2604-kubuntu-v0.4.1.img.xz](https://github.com/ut-slayer/orangepi-4a-mainline/releases/tag/v0.4.1)

---

## 1. Overview & Executive Summary

The **Allwinner T527** SoC features an integrated **VeriSilicon VIP9000 NPU** rated at **2.0 TOPS INT8**. While mainline Linux device trees expose the NPU node (`soc/npu@7122000` with `compatible = "vivante,gc"`), running inference out-of-the-box has historically been broken across the community:
1. Stock Mesa Teflon and upstream mainline `etnaviv.ko` were designed for Vivante 3D GPUs (GC7000, GC2000) and assumed 3D Pixel Engines (`PE`) exist, causing indefinite Front-End stalls, DMA hangs, and kernel watchdog resets (`recover hung GPU!`).
2. Upstream kernel runtime power management failed with `-EBUSY` (`GPU not yet idle, mask: 0x7ffbbff6`), leaving the NPU awake and causing system monitoring tools to report false `100%` load continuously.

**This repository provides a complete, tested, production-ready solution:**
- **Precompiled Patched Kernel Module (`kernel/etnaviv.ko`):** Linux 6.18.44 driver eliminating all PE stalls, MMU race conditions, and runtime autosuspend bugs.
- **Patched Out-of-Tree Kernel Source (`kernel/src/`):** Complete C source tree from `~/test_etnaviv` allowing recompilation against future kernel releases.
- **Precompiled Mesa Teflon Delegate (`lib/libteflon.so`):** Built from Mesa 26.0.8 with T527 VIP9000 HWDB parameters and split-submit race condition fixes.
- **Production Management Utility (`NPU_enable.sh`):** On-demand driver activation, deactivation, status reporting, and verification.
- **Hardware Telemetry CLI (`opi-mon` & `opi-mon.md`):** Lightweight mobile-optimized monitoring dashboard tracking true dynamic NPU load.
- **End-to-End Smoke Test (`smoke_test/`):** Standalone hardware diagnostic script verifying silicon execution and sysfs active time deltas.

---

## 2. Hardware Architecture & The DMA Hang Root Cause

### 2.1 The Silicon Reality
The VIP9000 (`vip9000nano-di`) is a dedicated neural accelerator consisting of:
- **Front-End (`FE`):** Instruction fetch and command streamer.
- **Neural Network Multi-Cores (`NN`):** 6 active tensor computing cores (`0x3910 = 0x3F`).
- **Tensor Processing Cores (`TP`):** 2 active cores.
- **NO 3D Pixel Engine (`PE`):** The core **completely lacks** a 3D rasterizer, depth buffer, or color output engine.

### 2.2 Why Stock Drivers Failed (Milestones 14–18 Breakthroughs)
- **Pixel Engine (PE) Stall Fallacy:** Stock Mesa Teflon emitted `0x48000000` stall instructions waiting for token `0x30000701` from recipient `0x07` (PE). The kernel ring buffer similarly emitted `CMD_SEM(FE, PE)` and `CMD_STALL(FE, PE)`. Because the PE does not exist on the NPU, the Front-End halted indefinitely (`DEBUG=0x00000800` / `0x00000816`), until the 1000 ms watchdog triggered `recover hung GPU!`.
- **Split Submits:** Mesa's `init_npu()` previously issued an unaligned `pctx->flush()`, causing an unaligned header to race with the main inference command buffer on the ring waitlink.
- **3D Register Contamination:** Teflon emitted 3D-specific registers (`VIVS_PA_SYSTEM_MODE` and `VIVS_GL_API_MODE`) that faulted on NPU hardware.
- **MMU Invalidation Race:** The kernel driver unconditionally flushed the MMU on every submit without giving the MTLB time to settle, stalling the AXI bus on rapid back-to-back inferences.
- **Runtime PM Autosuspend Failure:** `gpu->idle_mask` in `etnaviv_gpu.c` tested non-existent 3D Shader (`SH`, bit 3 = 0x8) and Tensor Processor (`TP`, bit 18 = 0x40000) bits, causing `etnaviv_gpu_rpm_suspend()` to return `-EBUSY` and keeping the NPU awake forever.

### 2.3 Applied Fixes Summary
| Component | Source File | Patch Summary |
| :--- | :--- | :--- |
| **Mesa Teflon** | `src/gallium/drivers/etnaviv/etnaviv_ml.c` | Gated multi-VIP stalls behind `ETNA_ENABLE_STALL` (default OFF); removed split submit in `init_npu()`; gated 3D registers behind `model != 0x9000`. |
| **Mesa HWDB** | `src/etnaviv/hwdb/allwinner/gc_feature_database.h` | Added native HWDB feature definitions for Allwinner T527 VIP9000 (`model: 0x9000`, `product: 0x5090009`). |
| **Kernel Ring** | `drivers/gpu/drm/etnaviv/etnaviv_buffer.c` | Guarded MMUv2 and pipe PE stalls with `model != 0x9000`; return target uses `VIVS_GL_FLUSH_CACHE_SHADER_L1` (`0x20`), `VIVS_GL_EVENT_FROM_FE`, and sets `return_dwords = 4`. |
| **Kernel Buffer End**| `drivers/gpu/drm/etnaviv/etnaviv_buffer.c` | Set `flush = 0` in `etnaviv_buffer_end()` on `0x9000` to eliminate PE stalls during buffer close and autosuspend. |
| **Kernel MMU** | `drivers/gpu/drm/etnaviv/etnaviv_buffer.c` | Removed forced MMU flush on consecutive submits; added `CMD_WAIT(buffer, 64)` settling delay during context invalidations. |
| **Kernel Power** | `drivers/gpu/drm/etnaviv/etnaviv_gpu.c` | Excluded absent bits (`SH` 0x8, `TP` 0x40000, `FE` 0x1) from `gpu->idle_mask` before HWDB early return, restoring clean autosuspend. |

---

## 3. Architectural Decision: Why the Vendor VIPCore Pathway Was Not Selected

During platform research (documented in `~/NPU_VIPCORE/NPU_findings.md`), both available driver pathways for the VeriSilicon VIP9000 on Allwinner T527 were thoroughly evaluated:
1. **The Vendor VIPCore Pathway (`vipcore.ko` / VIPLite 2.0.3)**
2. **The Mainline Open-Source Pathway (`etnaviv.ko` + Mesa `libteflon.so`)**

While `vipcore.ko` was successfully compiled and bound to hardware, it ultimately proved to be a **userspace dead-end** for modern Linux distributions. Here is why `etnaviv` + Mesa Teflon was chosen as the sole production architecture.

### 3.1 Kernel Driver Feasibility: `vipcore.ko` Proved Portable
The vendor VIPLite 2.0.3 driver (`npu-vipcore` from `skitzo2000/a7s-linux-drivers`), originally ported from the Allwinner A733 BSP (`sun60iw2`), was evaluated on our T527 (`sun55iw3`).
- **Device Tree Matching:** Both `vipcore.ko` and `etnaviv.ko` target the identical DT node: `/soc/npu@7122000` (`compatible = "vivante,gc"`).
- **The Mainline T527 Reset Bug:** The vendor driver failed probe initially because mainline Linux DT does not define named resets (`reset-names`), whereas the vendor driver looked for `"npu_rst"` and `"core"`.
- **The Patch:** We patched `vip_drv_device_platform.c` to add an unnamed reset controller fallback (`devm_reset_control_get_by_index(&pdev->dev, 0)`).
- **Compilation Success:** With this patch, `vipcore.ko` compiled cleanly against kernel `6.18.44-g61025ec85b88` with zero errors (1.5 MB artifact), successfully probed, and instantiated the character device `/dev/vipcore`.

### 3.2 The Userspace Dead-End: Missing Proprietary Stack
Despite having a functional kernel module and `/dev/vipcore`, the vendor ecosystem cannot perform neural inference on modern mainline Linux due to critical userspace gaps:
1. **Missing Proprietary Runtime Binaries:**
   The kernel driver only exposes a raw ioctl interface. Application inference requires VeriSilicon's closed-source userspace libraries: `libVIPlite.so` (the core C runtime), `libVIPhal.so`, `libNBGlinker.so`, and the executable runner `vpm_run`. In publicly available vendor BSPs and model zoos (e.g. Radxa Cubie A7S SDK), only `libVIPhal.so` and `libNBGlinker.so` are distributed; the essential `libVIPlite.so` and runtime tools are missing or locked behind closed NDAs.
2. **Mandatory Offline Compilation to Proprietary NBG Format:**
   Unlike standard AI runtimes that directly load standard `.tflite` or `.onnx` models, `/dev/vipcore` cannot parse graph formats. Models must be pre-compiled ahead-of-time using VeriSilicon's proprietary, closed-source **ACUITY Toolkit** into **Network Binary Graphs (NBG)**.
3. **Silicon Revision Incompatibility:**
   NBG machine code is tightly coupled to the exact silicon Product ID and hardware core count. Existing NBG binaries compiled for the A733 (chip PID `0x1000003B`) fail to execute on the T527 VIP9000 (Product ID `0x5090009`). Compiling new NBG binaries requires closed-source hardware configuration files for `vip9000nano-di` that are not available in public Debian/Ubuntu repositories.
4. **No Upstream Framework Integration:**
   Neither TensorFlow Lite, Google LiteRT, ONNX Runtime, nor PyTorch have upstream execution providers that interface with `/dev/vipcore`. The community pull request to add a VIPLite Execution Provider to ONNX Runtime (Microsoft ONNX Runtime Issue #28244) was abandoned in 2026.

### 3.3 Why Etnaviv + Mesa Teflon is the Superior Production Stack
By contrast, the Etnaviv + Mesa Teflon pathway provides a 100% open-source, standard-compliant solution:
- **Standard Linux DRM Subsystem:** Uses the mainline DRM driver exposing `/dev/dri/renderD129` with standard render group permissions.
- **Direct Google LiteRT / TFLite Compatibility:** Mesa Teflon (`libteflon.so`) implements Google's standard LiteRT External Delegate C API (`tflite_plugin_create_delegate`). Standard, un-obfuscated INT8 `.tflite` models run natively on hardware without vendor compilation toolchains.
- **Root Cause Fixes Applied:** The only reason Etnaviv originally hung was the Vivante 3D GPU legacy baggage (PE stalls, unaligned submits, idle mask checking absent SH/TP units). With these fixed in our patches, the open-source stack delivers rock-solid silicon acceleration with clean runtime power management.

### 3.4 Summary Comparison

| Dimension | Vendor VIPCore Pathway (`vipcore.ko`) | Mainline Open-Source Pathway (`etnaviv.ko` + `libteflon.so`) |
| :--- | :--- | :--- |
| **Kernel Module** | Available (`vipcore.ko` 1.5 MB, compiled cleanly) | **Active & Production-Ready** (`etnaviv.ko`, fully patched) |
| **Kernel Device Node**| `/dev/vipcore` (custom char dev) | `/dev/dri/renderD129` (standard Linux DRM) |
| **Userspace Runtime** | ❌ **Dead-end** (`libVIPlite.so` missing / proprietary) | ✅ **100% Open-Source** (Mesa Teflon `libteflon.so`) |
| **Model Format** | ❌ Proprietary compiled NBG (Network Binary Graph) | ✅ Standard Google LiteRT / TFLite (`.tflite` INT8) |
| **Compiler Toolchain** | ❌ Closed ACUITY Toolkit (chip PID locked) | ✅ Standard AI Edge / TFLite Quantizer |
| **Framework Support** | ❌ No upstream framework support (stale ONNX PR) | ✅ Native Google LiteRT, TensorFlow Lite, Python, C++ |
| **Power Management**  | ⚠️ Incomplete devfreq OPP / voltage regulation | ✅ Clean runtime autosuspend (`suspended` ↔ `active`) |
| **Verdict** | **Abandoned due to missing userspace stack** | **Selected Production Architecture** |

---

## 4. Operating System Dependencies

Before installing, ensure the host system has the necessary kernel headers and runtime dependencies installed.

### 4.1 Debian / Ubuntu Packages
The core runtime and userspace dependencies can be installed directly via `apt`:
```bash
sudo apt update
sudo apt install -y \
    build-essential \
    libdrm2 \
    libdrm-common \
    python3 \
    python3-pip \
    python3-numpy \
    python3-pil
```

> [!NOTE]
> **Kernel Headers are NOT required for standard installation:**
> The automated installer (`install.sh`) deploys the verified, precompiled `kernel/etnaviv.ko` directly to `/lib/modules/$(uname -r)/`. You do **not** need to install `linux-headers` via `apt` (in fact, custom SBC kernels like `6.18.44-g61025ec85b88` are not in Ubuntu's apt repository).
> Kernel headers are only needed if you wish to recompile the driver from source (Section 8).

### 4.2 Python Machine Learning Runtime
Install Google LiteRT (recommended) or TensorFlow Lite runtime:
```bash
pip install ai-edge-litert numpy pillow
```

---

## 5. Quick Installation Guide

Clone this repository to your Orange Pi 4A and run the automated installer:

```bash
git clone https://github.com/<your-user>/NPU_modules_opi4a_6.18.44.git
cd NPU_modules_opi4a_6.18.44
sudo ./install.sh
```

### What `install.sh` Does Automatically:
1. Deploys `kernel/etnaviv.ko` to `/lib/modules/$(uname -r)/kernel/drivers/gpu/drm/etnaviv/` and runs `depmod -a`.
2. Deploys `lib/libteflon.so` to `/usr/local/lib/libteflon.so` and creates symlink `/usr/lib/teflon/libteflon.so`.
3. Installs udev rules (`/etc/udev/rules.d/99-etnaviv-npu.rules`) to grant the `render` group read/write access to `/dev/dri/renderD129`.
4. Installs `/etc/modprobe.d/blacklist-etnaviv.conf` to prevent display servers from grabbing the NPU as primary 3D GPU on boot.
5. Adds your user account to `render` and `video` groups.
6. Installs `NPU_enable.sh` and `opi-mon` into `/usr/local/bin/`.
7. Activates the NPU driver on-demand.

---

## 6. Verification & Dmesg Log Inspection

After installation, verify that the NPU driver has initialized cleanly:

### 6.1 CLI Status Command
```bash
npu status
```
**Expected Output:**
```text
================================================================
 Orange Pi 4A (Allwinner T527) - NPU Subsystem Status
================================================================
Driver 'etnaviv' (Production DRM) : LOADED (size: 98304, used by: 0)
Driver 'vipcore' (Vendor Legacy)  : NOT LOADED (OK)
NPU DRM Node (/dev/dri/renderD129)   : AVAILABLE
  Permissions : crw-rw----+ root render
User 'ukhan' in 'render' group   : YES (Direct access enabled)
Modprobe Blacklist Status         : Present (/etc/modprobe.d/blacklist-etnaviv.conf)
NPU Hardware Power Telemetry      :
  runtime_status         : suspended
  runtime_active_time    : 14060772 ms (increments during inference)
================================================================
```

### 6.2 Kernel Log (`dmesg`) Verification
Run `dmesg | grep -i etnaviv`. Verify that you see the following milestone markers:

```text
[  100.066147] etnaviv etnaviv: bound 7122000.npu (ops gpu_ops [etnaviv])
[  100.066468] etnaviv-gpu 7122000.npu: model: GC9000, revision: 9003
[  100.066484] etnaviv-gpu 7122000.npu: etnaviv has been instantiated on a NPU, for which the UAPI is still experimental
[  100.067155] [drm] Initialized etnaviv 1.4.0 for etnaviv on minor 0
```

During active hardware inference, confirm hardware completion interrupts:
```text
[  105.119576] etnaviv_irq: intr 0x00000001
```

**Critical Quality Checks:**
- Ensure **NO** `etnaviv-gpu 7122000.npu: recover hung GPU!` entries appear.
- Ensure **NO** `etnaviv-gpu 7122000.npu: timed out waiting for idle` warnings appear.
- Ensure **NO** `etnaviv-gpu 7122000.npu: GPU not yet idle` warnings appear.

---

## 7. Running the Hardware Smoke-Test

Run the standalone hardware smoke-test included in this repository:

```bash
python3 smoke_test/test_npu_smoke.py
```

**Expected Output:**
```text
====================================================================
   Orange Pi 4A (Allwinner T527 VIP9000) — NPU Hardware Smoke-Test
====================================================================
[1/5] Checking DRM device node (/dev/dri/renderD129)...
      [OK] Render node accessible (rw).
[2/5] Locating Mesa Teflon delegate library...
      [OK] Teflon delegate: .../lib/libteflon.so (11.3 MB)
[3/5] Verifying test model (conv2d.tflite)...
      [OK] Test model loaded (51.5 KB).
[4/5] Loading Teflon delegate onto VIP9000 hardware...
      [OK] Teflon delegate initialized in 72.77 ms.
[5/5] Executing forward inference on silicon...
====================================================================
                     SMOKE TEST RESULTS
====================================================================
Hardware Execution Time   : 32.04 ms
Output Tensor Dimensions  : (1, 40, 40, 128) (uint8)
Initial Power State       : suspended
Active Time Delta (sysfs) : +33 ms (Proves real silicon core activity)
Post-Inference State      : suspended (Clean autosuspend verified)
====================================================================
STATUS: NPU SUBSYSTEM & TEFLON DELEGATE 100% OPERATIONAL
====================================================================
```

---

## 8. Rebuilding the Kernel Module from Source (`kernel/src/`)

If you are using a custom kernel build or a different kernel revision, you can recompile `etnaviv.ko` directly on your board.

> [!IMPORTANT]
> **Kernel Header / Build Tree Requirement:**
> Compiling from source requires the kernel build tree at `/lib/modules/$(uname -r)/build`. On this Orange Pi 4A installation, this tree is provided at `/usr/src/linux-headers-6.18.44-g61025ec85b88` with matching symbols (`Module.symvers`). If running on a different kernel image, ensure your board vendor's kernel development package or build tree (`make modules_prepare`) is in place.

```bash
cd kernel/src
make -C /lib/modules/$(uname -r)/build M=$PWD modules -j4
sudo cp etnaviv.ko /lib/modules/$(uname -r)/kernel/drivers/gpu/drm/etnaviv/etnaviv.ko
sudo depmod -a
sudo ./NPU_enable.sh enable
```

---

## 9. Empirical Benchmarks Across Workloads

| Project / Task | Mode / Framework | Average Latency | Throughput | Hardware Telemetry Delta | Status |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **IAPWS-97 Steam Tables** | Exact Analytical CPU | 1.6211 ms | 616.9 evals/sec | — | Ground truth baseline |
| **IAPWS-97 Steam Tables** | Neural Surrogate (CPU XNNPACK) | **0.0277 ms** | **36,104.7 evals/sec** | — | **58.5x FASTER** (< 0.5% error) |
| **IAPWS-97 Steam Tables** | Hardware NPU (Mesa Teflon) | **0.89 ms – 1.17 ms** | ~900 evals/sec | `+2,510 ms` (burst) / `+5,357 ms` (stress) | Fully verified on silicon |
| **MobileNet V1 (224x224)** | CPU 1-thread (XNNPACK) | 114.34 ms | 8.7 FPS | — | Single-thread baseline |
| **MobileNet V1 (224x224)** | CPU 4-threads (XNNPACK) | 30.07 ms | 33.3 FPS | — | Quad-core scaling |
| **MobileNet V1 (224x224)** | CPU 8-threads (XNNPACK) | **18.91 ms** | **52.9 FPS** | — | Octa-core full saturation |
| **SSD Detection (300x300)** | CPU 1-thread (XNNPACK) | 154.13 ms | 6.5 FPS | — | Single-thread baseline |
| **SSD Detection (300x300)** | CPU 8-threads (XNNPACK) | **27.28 ms** | **36.7 FPS** | — | Octa-core full saturation |
| **SSD Detection (300x300)** | NPU (`libteflon.so`) 10-run | Hardware active | 10/10 runs passed (`rc=0`) | `+4,900 ms` avg active delta / run | Rock-solid on silicon |

---

## 10. Directory Structure & File Manifest

```text
~/NPU_modules_opi4a_6.18.44/
├── install.sh                     # Master one-click installer
├── README.md                      # This comprehensive guide
├── NPU_enable.sh                  # On-demand NPU driver enable/disable CLI
├── NPU_enable.md                  # Comprehensive NPU operations manual
├── opi-mon                        # 37-col terminal monitoring dashboard
├── opi-mon.md                     # Deep-dive on NPU load calculation & fixes
├── config/
│   ├── 99-etnaviv-npu.rules       # Udev rule for /dev/dri/renderD129
│   └── blacklist-etnaviv.conf     # Modprobe blacklist configuration
├── kernel/
│   ├── etnaviv.ko                 # Precompiled module for 6.18.44-g61025ec85b88
│   ├── install_kmod.sh            # Kernel module installation script
│   ├── opt/                       # Optional alternative vendor artifacts
│   │   └── vipcore.ko             # Patched VeriSilicon VIPLite 2.0.3 module (1.5 MB)
│   └── src/                       # Complete patched out-of-tree kernel C source
│       ├── Makefile, Kconfig
│       ├── etnaviv_buffer.c       # Patched buffer & ring management
│       ├── etnaviv_gpu.c          # Patched runtime PM & idle mask
│       ├── etnaviv_hwdb.c         # Patched HWDB table
│       └── ...                    # Full driver source tree
├── lib/
│   ├── libteflon.so               # Patched Mesa Teflon delegate (12 MB)
│   └── install_lib.sh             # Library deployment & ldconfig script
└── smoke_test/
    ├── test_npu_smoke.py          # Standalone hardware diagnostic script
    ├── conv2d.tflite              # Validated INT8 test tensor model (51 KB)
    └── requirements.txt           # Python package requirements
```

---

## 11. License & Credits

- **Kernel Driver:** GNU General Public License v2 (GPL-2.0), Linux Foundation & Etnaviv DRM Project.
- **Mesa Teflon:** MIT / X11 License, Mesa 3D Project & Google LiteRT.
- **Patches & Integration:** Custom Allwinner T527 VIP9000 stabilization patches developed for Orange Pi 4A.
