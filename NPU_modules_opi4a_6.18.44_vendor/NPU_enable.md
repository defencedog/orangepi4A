# Orange Pi 4A (Allwinner T527) — Unified NPU Management & Dual-Driver Guide

**Quick Reference (`npu` CLI):**
- Check complete status & telemetry: `npu status`
- Switch to Mainline Teflon / Etnaviv (`/dev/dri/renderD129`): `sudo npu teflon`
- Switch to Vendor VIPCore / VIPLite (`/dev/vipcore`): `sudo npu vipcore`
- Disable / power-gate NPU (clean idle state): `sudo npu disable`
- Run hardware inference smoke-test: `npu test` (auto-detects active driver)

> [!TIP]
> **Unified Aliases:** The unified command `npu` is installed in `/usr/local/bin/npu`. All legacy commands and symlinks (`/usr/local/bin/npu-switch`, `~/NPU_enable.sh`, and `~/NPU_switch_driver.sh`) point to this single canonical tool.

---

## 1. Executive Summary & Dual Production Architecture

The Orange Pi 4A features an integrated **VeriSilicon Vivante VIP9000nano-di** Neural Processing Unit (`ChipID: 0x9000`, `Revision: 0x9003`, `ProductID: 0x5090009`, `CustomerID: 0x10000016`) mapped to Device Tree node `npu@7122000`.

On mainline Linux **6.18.44-g61025ec85b88**, the Orange Pi 4A supports **two distinct, fully verified production NPU stacks**:

| Feature / Metric | Mainline Teflon Stack (`etnaviv`) | Vendor VIPLite Stack (`vipcore`) |
| :--- | :--- | :--- |
| **Status** | **PRODUCTION READY (Upstream)** | **PRODUCTION READY (Native Vendor)** |
| **Kernel Driver** | `etnaviv.ko` (Linux DRM Subsystem) | `vipcore.ko` (Allwinner BSP v1.13 ported to 6.18) |
| **Device Node** | `/dev/dri/renderD129` (mode `0660`, `render`) | `/dev/vipcore` (mode `0666`) |
| **Userspace Runtime** | Patched Mesa Teflon (`/usr/local/lib/libteflon.so`) | Vendor VIPLite (`/usr/local/lib/libVIPlite.so`, `libVIPuser.so`) |
| **Headers** | Standard TFLite / LiteRT C API | `/usr/local/include/vip_lite.h`, `vip_lite_common.h` |
| **Framework Support** | Google LiteRT (`ai_edge_litert`), TFLite | VeriSilicon TIM-VX, `vpm_run`, C/C++ VIPLite API |
| **Model Format** | Standard Quantized FlatBuffers (`.tflite`) | Native Network Binary Graph (`.nb`) |
| **Model Compiler** | Standard TensorFlow Lite Converter / AI Edge | ACUITY Toolkit (Docker container on Proxmox / x86_64) |
| **Inference Latency** | ~30.5 ms (`conv2d.tflite`, 80x80x16) | **12.97 ms** (~77 FPS, `network_binary.nb`, 224x224x3) |
| **Telemetry & Health** | Monitored via sysfs & live in `opi-mon` | Power-gated automatically via runtime PM |

---

## 2. Coexistence & Mutual Exclusivity Architecture

### 2.1 Userspace Coexistence: 100% Conflict-Free
The userspace shared libraries and header files for both stacks permanently coexist in `/usr/local/`:
- **Mainline Teflon**: `/usr/local/lib/libteflon.so` exports `tflite_plugin_create_delegate` and links against `libdrm.so.2` and `libc.so.6`.
- **Vendor VIPLite**: `/usr/local/lib/libVIPlite.so` and `libVIPuser.so` export strictly namespaced C symbols (`vip_*` and `gcvip_*`).
- Both are registered with the dynamic linker cache (`sudo ldconfig`). Any application can link against `-lVIPlite` or load `libteflon.so` without collision or requiring custom `LD_LIBRARY_PATH`.

### 2.2 Kernel Space Mutual Exclusivity
Both `etnaviv.ko` and `vipcore.ko` declare `.compatible = "vivante,gc"` in their Device Tree match tables for `/soc/npu@7122000`:
1. The Linux platform driver core allows only **one** active driver binding per platform device at any given moment (`dev->driver`).
2. Whichever driver binds first claims exclusive ownership of:
   - MMIO register space (`0x07122000 - 0x07123000`)
   - Interrupt vector (`IRQ 496`)
   - CCU NPU generic power domain (`PD_NPU`)
   - CCU clocks (`bus`, `reg`, `core`) and reset controller (`RST_BUS_NPU`).
3. **Desktop & Media Isolation on Allwinner T527**:
   - The desktop 3D GPU is **ARM Mali-G57 MC1**, driven exclusively by **`panfrost`** (`/dev/dri/card0`, `/dev/dri/renderD128`).
   - The display and HDMI are driven by **Allwinner DE3.5** (`sunxi-de`).
   - Video decoding is driven by **Allwinner Cedar** (`cedrus`).
   - **`etnaviv` and `vipcore` have zero connection to desktop graphics, Wayland/KDE, 3D gaming, or video decoding.**
   - Switching between `etnaviv` and `vipcore` takes **under 1 second** and is completely transparent to the desktop GUI.

---

## 3. The Unified `npu` CLI Command Reference

The unified management utility `npu` (located at `/usr/local/bin/npu`) provides one-touch control:

### 3.1 Check Subsystem Status
```bash
npu status
```
*Does not require sudo.* Output reports:
- Active driver pipeline (`TEFLON`, `VIPCORE`, or `NONE`)
- Loaded kernel modules (`etnaviv`, `vipcore`)
- Device nodes and permissions (`/dev/dri/renderD129`, `/dev/vipcore`)
- User group permissions (`render` group membership)
- Hardware power management & active inference telemetry
- Installed userspace libraries (`libteflon.so`, `libVIPlite.so`, `libVIPuser.so`)
- Model runner (`vpm_run`) and Python LiteRT virtual environment availability

### 3.2 Switch to Mainline Teflon (`etnaviv`)
```bash
sudo npu teflon
# Or: sudo npu enable teflon
```
**Actions performed:**
1. Unloads active `vipcore` module if loaded.
2. Loads `etnaviv` DRM driver.
3. Confirms creation of `/dev/dri/renderD129` (mode `0660`, group `render`).
4. Verifies ready state for Google LiteRT / TFLite models.

### 3.3 Switch to Vendor VIPCore (`vipcore`)
```bash
sudo npu vipcore
# Or: sudo npu enable vipcore
```
**Actions performed:**
1. Unloads active `etnaviv` driver if loaded.
2. Inserts patched `vipcore.ko`.
3. Confirms creation of `/dev/vipcore` (mode `0666`).
4. Verifies ready state for NBG compiled models and `vpm_run`.

### 3.4 Disable All NPU Drivers (Clean Idle State)
```bash
sudo npu disable
```
**Actions performed:**
1. Unloads whichever driver is currently active.
2. Restores default modprobe configuration.
3. Leaves the VIP9000 NPU completely power-gated and clock-disabled.

### 3.5 Run Hardware Inference Smoke-Test
```bash
npu test
```
*Auto-detects the active driver and executes the appropriate hardware test:*
- **When Teflon is active**: Executes LiteRT + Teflon smoke-test, allocating tensors on the VIP9000 core, and confirms hardware execution via sysfs `runtime_active_time` delta.
- **When VIPCore is active**: Executes `vpm_run` against the pre-compiled T527 NBG model in `~/NPU_modules_opi4a_6.18.44_vendor/sample/` and reports cycle count and latency.
- **Explicit stack test**: You can force a specific stack test via `npu test teflon` or `npu test vipcore`.

---

## 4. Hardware Telemetry & Live Monitoring

The Allwinner T527 implements runtime power management for the NPU. The core is automatically power-gated when idle and clocked up during active tensor execution.

### 4.1 Sysfs Telemetry Nodes
- **Active Execution Counter:**
  ```bash
  cat /sys/devices/platform/soc/7122000.npu/power/runtime_active_time
  ```
  *Increments only when hardware inference instructions execute on the VIP9000 core.*
- **Runtime Power State:**
  ```bash
  cat /sys/devices/platform/soc/7122000.npu/power/runtime_status
  # Returns: "active" during inference, "suspended" when idle
  ```

### 4.2 Live Monitoring with `opi-mon`
The system monitor utility `opi-mon` displays live CPU, GPU (Mali-G57), VPU (Cedar), and NPU (VIP9000) utilization percentages and temperatures side-by-side:
```bash
opi-mon
```

---

## 5. Software Stack & Production Applications

```
+---------------------------------------------------------------------------------+
|                       Applications on Orange Pi 4A                             |
|    LiteRT / Python Apps (OCR, Face Clustering)    |    Native C/C++ NBG Apps    |
+---------------------------------------------------+-----------------------------+
|    Google LiteRT (ai_edge_litert) / TFLite        |    vpm_run / Custom C Apps  |
+---------------------------------------------------+-----------------------------+
|    Mesa Teflon: /usr/local/lib/libteflon.so       |    /usr/local/lib/libVIPlite|
+---------------------------------------------------+-----------------------------+
|    DRM Driver: etnaviv (/dev/dri/renderD129)      |    Driver: /dev/vipcore     |
+---------------------------------------------------+-----------------------------+
|                     Allwinner T527 VIP9000 Silicon (npu@7122000)                |
+---------------------------------------------------------------------------------+
```

### Production Projects on Orange Pi 4A:
1. **Optical Character Recognition (PP-OCRv4 via Teflon):**
   - Location: `~/opi4a-npu-ocr/`
   - Tools: `npu-ocr-pdf`, `pdf_ocr.py`
2. **Object Detection (MobileNet SSD via Teflon):**
   - Location: `~/opi4a-npu-mobilenet/`
3. **Vendor Model Execution (vpm_run via VIPCore):**
   - Location: `~/NPU_modules_opi4a_6.18.44_vendor/`
   - Runner: `/usr/local/bin/vpm_run`
   - Latency: **12.97 ms** (~77 FPS) on native NBG models.
