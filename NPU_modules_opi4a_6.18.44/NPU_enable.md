# Orange Pi 4A (Allwinner T527) — NPU Activation & Management Guide

**Quick Reference:**
- Enable NPU (`/dev/dri/renderD129`): `sudo ~/NPU_enable.sh enable`
- Disable NPU (clean desktop state): `sudo ~/NPU_enable.sh disable`
- Check status & telemetry: `~/NPU_enable.sh status`
- Test hardware inference: `~/NPU_enable.sh test`

---

## 1. Executive Summary & Production Architecture

The Orange Pi 4A features an integrated **VeriSilicon VIP9000** Neural Processing Unit (NPU core `vivante,gc` revision `9003`, located at SoC device-tree node `npu@7122000`).

### Production Verdict: `etnaviv` vs `vipcore`

| Metric / Feature | `etnaviv` (Mesa DRM Subsystem) | `vipcore` (VeriSilicon VIPLite) |
| :--- | :--- | :--- |
| **Status** | **PRODUCTION READY (Recommended)** | **Non-Functional for Production** |
| **Kernel Driver** | Mainline `etnaviv.ko` (built into kernel) | Out-of-tree `vipcore.ko` port |
| **Device Node** | `/dev/dri/renderD129` | `/dev/vipcore` |
| **Userspace Runtime** | Patched Mesa Teflon (`libteflon.so`) | Proprietary `libVIPlite.so` / `libVIPhal.so` |
| **Framework Support** | Google LiteRT (`ai_edge_litert`), TFLite | None upstream (requires custom execution provider) |
| **Model Compatibility**| Standard quantized `.tflite` models | Requires proprietary ACUITY offline compiled NBG |
| **Telemetry & Health**| Monitored via sysfs + live in `opi-mon` | Unverified |
| **Usability** | **Fully functional & verified** | Blocked by missing userspace SDK |

> [!IMPORTANT]
> **Why `vipcore` cannot be effectively utilized:**
> Although the kernel module `vipcore.ko` can be compiled, there is no functional userspace runtime library (`libVIPlite.so`/`libVIPhal.so`), no standard framework execution provider (such as ONNX-Runtime EP or LiteRT delegate), and no compiler toolchain available on the board to convert models into T527-specific NBG binaries.
>
> In contrast, **`etnaviv` + Mesa Teflon (`libteflon.so`)** directly enables Google LiteRT to execute quantized neural networks on the VIP9000 hardware core via `/dev/dri/renderD129`.

---

## 2. The DRM Device Node & Desktop GPU Interaction

### Why stock Linux blacklists `etnaviv`
On stock Orange Pi 4A OS images, `/etc/modprobe.d/blacklist-etnaviv.conf` is configured with `blacklist etnaviv`. The file contains the following explanation from the board maintainers:

```ini
# La NPU (etnaviv/renderD129) no hace OpenGL; si es la GPU de render por defecto
# rompe la aceleracion (apps a llvmpipe, Chromium sin WebGL). Cargar on-demand:
#   sudo modprobe etnaviv   (para Teflon/NN)   /   sudo modprobe -r etnaviv
blacklist etnaviv
```

- **Root Cause:** When `etnaviv` auto-loads during system boot, it claims `/dev/dri/card0`. Because the VIP9000 is an NPU core (lacking a 3D desktop graphics pipeline), desktop applications querying `card0` for OpenGL fail and fall back to software rendering (`llvmpipe`), impacting desktop 3D acceleration.
- **The Solution:** Load `etnaviv` **on demand** using `NPU_enable.sh enable` when executing NPU workloads, and unload it via `NPU_enable.sh disable` when pure desktop GPU focus is desired.
- **Alternative for persistent desktop sessions:** If `etnaviv` is loaded, desktop applications can explicitly use the Mali-G57 GPU by setting `MESA_LOADER_DRIVER_OVERRIDE=panfrost`.

---

## 3. Command Guide (`NPU_enable.sh`)

The script `~/NPU_enable.sh` provides unified lifecycle management for the NPU subsystem:

### 1. Enable the NPU
```bash
sudo ~/NPU_enable.sh enable
```
**Actions performed:**
1. Verifies root privileges.
2. Unloads any conflicting legacy modules (e.g. `vipcore`).
3. Cleans any blocking install shims in `/etc/modprobe.d/blacklist-etnaviv.conf`.
4. Loads the `etnaviv` kernel module.
5. Verifies creation of `/dev/dri/renderD129`.
6. Sets group ownership and mode (`0660`, group `render`).
7. Checks that the invoking user is in the `render` group.
8. Reads initial hardware power management telemetry.

### 2. Disable the NPU
```bash
sudo ~/NPU_enable.sh disable
```
**Actions performed:**
1. Checks for running processes accessing `/dev/dri/renderD129` (via `fuser`).
2. Unloads `etnaviv` (`modprobe -r etnaviv`).
3. Restores standard modprobe blacklist configuration.
4. Confirms removal of `/dev/dri/renderD129`, returning DRM subsystem to base state (Mali-G57 / Panfrost only).

### 3. Check Status
```bash
~/NPU_enable.sh status
```
*Does not require sudo.*
Displays a complete diagnostic report:
- Kernel driver load state (`etnaviv`, `vipcore`).
- Device node presence and permissions (`/dev/dri/renderD129`).
- User group membership (`render`).
- Hardware power telemetry (`runtime_status`, `runtime_active_time`).
- Teflon delegate library locations (`libteflon.so`).
- Python LiteRT environment availability (`~/venv_npu`).

### 4. Test Hardware Inference
```bash
~/NPU_enable.sh test
```
*Does not require sudo.*
Executes an end-to-end hardware smoke-test:
1. Validates access to `/dev/dri/renderD129`.
2. Loads the Mesa Teflon delegate into LiteRT.
3. Allocates and executes tensors on the VIP9000 hardware core.
4. Measures and verifies the delta in `/sys/devices/platform/soc/7122000.npu/power/runtime_active_time`.

---

## 4. Hardware Telemetry & Verification

The Allwinner T527 kernel driver implements runtime power management for the NPU. The core is automatically power-gated when idle and clocked up during active tensor execution.

### Sysfs Telemetry Nodes
- **Active Time Counter:**
  ```bash
  cat /sys/devices/platform/soc/7122000.npu/power/runtime_active_time
  ```
  *Increments only when hardware inference instructions are executing on the VIP9000 core.*
- **Runtime Power Status:**
  ```bash
  cat /sys/devices/platform/soc/7122000.npu/power/runtime_status
  # Returns: "active" during inference, "suspended" when idle
  ```

### Live Monitoring with `opi-mon`
The system monitor utility `opi-mon` hooks directly into the sysfs telemetry node:
```bash
opi-mon
```
`opi-mon` displays live CPU, GPU (Mali-G57), VPU (Cedar), and NPU (VIP9000) utilization percentages and temperatures side-by-side.

---

## 5. Software Stack & Production Applications

### Component Architecture
```
+-------------------------------------------------------------+
| Applications: MobileNet SSD / PaddleOCR / Face Clustering   |
+-------------------------------------------------------------+
| Google LiteRT (ai_edge_litert) / TFLite Runtime             |
+-------------------------------------------------------------+
| Mesa Teflon Delegate: libteflon.so (HWDB: VIP9000 0x9003)   |
+-------------------------------------------------------------+
| Linux DRM Driver: etnaviv (/dev/dri/renderD129)            |
+-------------------------------------------------------------+
| Allwinner T527 VIP9000 Silicon (npu@7122000)                |
+-------------------------------------------------------------+
```

### Production Projects on Orange Pi 4A
1. **Object Detection (MobileNet SSD):**
   - Location: `~/opi4a-npu-mobilenet/`
   - Benchmark: `~/opi4a-npu-mobilenet/run_telemetry_10x.sh`
2. **Optical Character Recognition (PP-OCRv4):**
   - Location: `~/opi4a-npu-ocr/`
   - Tools: `npu-ocr-pdf`, `pdf_ocr.py`
3. **Teflon Delegate Libraries:**
   - System path: `/usr/lib/teflon/libteflon.so`
   - Local path: `/usr/local/lib/libteflon.so`
   - Project path: `~/opi4a-npu-ocr/lib/libteflon.so`

---

## 6. Permissions & Troubleshooting

### Granting User Permissions
If a non-root user cannot access `/dev/dri/renderD129`:
```bash
sudo usermod -aG render $USER
```
Log out and log back in (or run `newgrp render`) to refresh group credentials.

### Unload Failure (`device or resource busy`)
If `sudo ~/NPU_enable.sh disable` warns that the device is busy:
```bash
fuser -v /dev/dri/renderD129
```
Identify the process ID holding the render node and terminate it before unloading `etnaviv`.

---

---

---

## 7. DMA Command Stall Resolution & Hardware Architecture (Milestones 14–16)

### The Hardware Reality
The VeriSilicon VIP9000 (`vip9000nano-di`, `model: 0x9000`, `revision: 0x9003`) is an NPU accelerator consisting solely of:
- A Front-End (`FE`) command streamer
- Neural Network (`NN`) multi-cores (6 active cores)
- Tensor Processing (`TP`) cores (2 active cores)
- It **completely lacks a 3D Pixel Engine (`PE`)**, rasterizer, or color/depth buffers.

### Root Cause of the "DMA Command Stalls"
Stock Mesa Teflon and upstream mainline `etnaviv` drivers were written primarily for Vivante 3D GPUs (GC7000, GC2000). Consequently:
1. **Userspace Mesa Teflon (`src/gallium/drivers/etnaviv/etnaviv_ml.c`):**
   - `emit_multivip_sync()` unconditionally emitted `VIV_FE_STALL_HEADER_OP_STALL` (`0x48000000`) instructions waiting for token `0x30000701` (where recipient `0x07` is `SYNC_RECIPIENT_PE`).
   - `init_npu()` emitted `CMD_SEM(FE, PE)` and `CMD_STALL(FE, PE)`.
   - `init_npu()` performed a split submit via `pctx->flush()`, pushing an unaligned 136-byte header that raced with the main inference command buffer on the ring buffer waitlink.
2. **Kernel DRM Driver (`drivers/gpu/drm/etnaviv/etnaviv_buffer.c`):**
   - In `etnaviv_buffer_queue()`, MMU maintenance (`need_flush`) and pipe switches unconditionally emitted `CMD_SEM(FE, PE)` and `CMD_STALL(FE, PE)` into the ring buffer.
   - The ring return block after command buffer execution emitted `VIVS_GL_EVENT_FROM_PE` and requested cache flushes for Depth and Color buffers (`0x00000c23`).
- Because the Pixel Engine does not exist on the NPU, the FE halted indefinitely waiting for PE idle/token signals (`DEBUG=0x00000800` / `0x00000816`), triggering the 1000 ms kernel hang recovery watchdog (`recover hung GPU!`).

### Applied Code Patches
1. **Kernel (`etnaviv_buffer.c`):**
   - Guarded MMUv2 flush and pipe switch PE stalls with `if (gpu->identity.model != 0x9000)`.
   - In the return target for `0x9000`: changed cache flush from `0x00000c23` (depth/color) to `VIVS_GL_FLUSH_CACHE_SHADER_L1` (`0x20`).
   - Replaced `VIVS_GL_EVENT_FROM_PE` with `VIVS_GL_EVENT_FROM_FE`.
   - Reserved exactly 4 64-bit words (`return_dwords = 4`) for `0x9000`, preventing FE prefetch overruns into uninitialized ring memory.
2. **Mesa Teflon (`etnaviv_ml.c`):**
   - Gated all stall instructions behind `ETNA_ENABLE_STALL` (default OFF).
   - Removed split submit from `init_npu()` so that initialization states batch directly into the unified command stream.
   - Gated 3D-specific registers (`VIVS_PA_SYSTEM_MODE` and `VIVS_GL_API_MODE`) behind `if (info && info->model != 0x9000)`.

---

## 8. Empirical Benchmarks: CPU vs. VIP9000 Hardware Inference

### A. Chemical Engineering Steam Tables (`~/NPU-IAPWS/`)
- Model: `iapws_fc16_int8.tflite` (4 chained dense layers: 16 -> 64 -> 64 -> 32 -> 16).
- **Exact Analytical IAPWS-97:** **1.62 ms** (616.9 evals/sec).
- **CPU Neural Surrogate (LiteRT XNNPACK):** **0.032 ms** (31,178 evals/sec, **50.5x faster**, < 0.5% thermodynamic MAPE).
- **Hardware NPU Single Inference:** **0.89 ms – 1.17 ms** hardware execution on silicon with `etnaviv_irq: intr 0x1` and zero GPU hangs.

### B. Computer Vision MobileNet V1 (`~/opi4a-npu-mobilenet/`)
- Model: `mobilenet_v1_1.0_224_quant.tflite` (224x224 input, 1001 classes).
- **CPU XNNPACK (4 Threads):** **36.91 ms** (27.1 FPS, Top-1: 92.15% "military uniform").
- **VIP9000 Hardware NPU Execution:** Hardware active time verified via sysfs telemetry (`+6,356 us` active delta).

---

## 9. NPU Telemetry, Runtime PM Autosuspend, and `opi-mon` Integration

### The 100% Load Telemetry Bug
Previously, monitoring tools like `opi-mon` reported `NPU 100%` load continuously even when no inference was running. This occurred due to three compound issues:
1. **Upstream `idle_mask` Bug in `etnaviv_gpu.c`:** The driver tested register `VIVS_HI_IDLE_STATE` against `idle_mask & ~(FE | MC)`. Because VIP9000 lacks Shader (`SH`, bit 3 = 0x8) and Tensor Processor (`TP`, bit 18 = 0x40000) blocks, the hardware reported `0x7ffbbff6`. The driver failed autosuspend with `-EBUSY` (`GPU not yet idle, mask: 0x7ffbbff6`).
2. **PE Stalls in `etnaviv_buffer_end()`:** When attempting to autosuspend, `etnaviv_buffer_end()` emitted `CMD_STALL(FE, PE)`, stalling the Front-End and triggering `timed out waiting for idle: idle=0x7ffbfff6`.
3. **Flawed Fallback in `opi-mon`:** `/usr/local/bin/opi-mon` contained a fallback: `if [ "$npu_load" -eq 0 ] && [ "$npu_stat" = "active" ]; then npu_load=100; fi`. Because autosuspend failed, `runtime_status` remained permanently `active`, and `runtime_active_time` accumulated 1000 ms/sec while completely idle.

### The Fix
1. **Kernel Driver (`etnaviv_gpu.c`):** Excluded `SH` (bit 3), `TP` (bit 18), and `FE` (bit 0) from `gpu->idle_mask` before the HWDB early return for `model == 0x9000`.
2. **Kernel Buffer (`etnaviv_buffer.c`):** Set `flush = 0` in `etnaviv_buffer_end()` for `model == 0x9000`, eliminating all PE stalls during buffer close and autosuspend.
3. **Telemetry Monitor (`/usr/local/bin/opi-mon`):** Removed the hardcoded `npu_stat == "active" -> npu_load=100` fallback and scaled dynamic duty cycle against `interval_ms`.

### Verified Operational Telemetry
- **Idle State:** `runtime_status: suspended`, `runtime_active_time` delta = `0 ms`, `opi-mon` reports **`0%`**.
- **Active State:** Wakes on inference, executes forward pass, `opi-mon` reports proportional load up to **`100%`**.
- **Autosuspend:** Automatically returns to `suspended` 200 ms after inference completes with zero kernel warnings or hung recoveries.
