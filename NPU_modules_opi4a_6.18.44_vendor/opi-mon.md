# `opi-mon` — Hardware Telemetry & NPU Load Measurement Guide

`opi-mon` is an ultra-lightweight, 37-column mobile/SSH-optimized terminal dashboard designed specifically for the **Orange Pi 4A (Allwinner T527 Octa-Core SoC)**. It monitors and renders real-time telemetry across CPU, NPU (VeriSilicon VIP9000), GPU (ARM Mali-G57), RAM, and Swap with 1-second refresh intervals.

---

## 1. Live Telemetry Layout

```text
 Orange Pi 4A (T527)
 03:12:40 · Up: 4m · Load: 0.27
─────────────────────────────────────
 CPU  26% [██░░░░░░░░] 40.4°C  1.80GHz
 NPU 100% [██████████] 38.6°C  2 TOPS
 GPU   0% [░░░░░░░░░░] 38.6°C   150MHz
 RAM  38% [███░░░░░░░] 1.4/3.7G 2367M free
 SWP   0% [░░░░░░░░░░] 0.0/1.9G
─────────────────────────────────────
 [Ctrl+C] Exit  ·  Refresh: 1s
```

---

## 2. Dual-Pipeline NPU Telemetry Architecture

The Allwinner T527 NPU can be operated either via the mainline open-source DRM driver (**etnaviv**) or the vendor character device driver (**vipcore**). `opi-mon` automatically detects which driver is active and dynamically selects the appropriate telemetry probe:

```text
                 NPU Driver Auto-Detection in opi-mon
                                  │
                 Is /dev/dri/renderD129 present?
                                ╱   ╲
                              YES    NO
                              ╱        ╲
            [Path A: Etnaviv / Teflon]   Is /dev/vipcore loaded?
            • Probe: runtime_active_time            ╱   ╲
            • Formula: Δt_active / interval       YES    NO
                                                  ╱        ╲
                                [Path B: Vendor VIPCore]   [NPU OFFLINE]
                                • Probe: vipcore_0 IRQs    • Grayed out
                                • Probe: fuser /dev/vipcore• 0% / Power-gated
```

### 2.1 Path A: Mainline Etnaviv / Teflon (DRM Telemetry)
When `etnaviv.ko` is active (`sudo npu teflon`), NPU execution is tracked via Linux Runtime Power Management (Runtime PM):
- **Active Time Counter:** `/sys/devices/platform/soc/7122000.npu/power/runtime_active_time`  
  Accumulates the elapsed milliseconds the VIP9000 execution core spent actively executing command streams.
- **Power State:** `/sys/devices/platform/soc/7122000.npu/power/runtime_status`  
  Reports `suspended` (core clock-gated, 0 W) or `active`.
- **Load Calculation:**
  $$\text{NPU Load (\%)} = \min\left(100, \frac{\Delta t_{\text{active}} \times 100}{\text{INTERVAL} \times 1000}\right)$$

### 2.2 Path B: Vendor VIPCore / VIPLite (Interrupt & Process Telemetry)
When `vipcore.ko` is active (`sudo npu vipcore`), the vendor runtime bypasses DRM Runtime PM and issues direct AHB register submissions via ioctl. Because `runtime_active_time` remains static under this driver, `opi-mon` tracks hardware execution through two complementary hardware probes:
1. **GICv3 Hardware Interrupts:** Tracks interrupts on `vipcore_0` in `/proc/interrupts` (IRQ 491/496). Each neural network execution job triggers completion interrupts.
2. **Device Handle Monitoring:** Verifies active process bindings on `/dev/vipcore` using `fuser`.
- When an inference workload runs on the VIP9000 NPU, `opi-mon` lights up `NPU 100% [██████████] 2 TOPS` in real time.

---

## 3. The 100% Idle Load Bug & How It Was Fixed

In earlier builds under the mainline `etnaviv` driver, users reported that `opi-mon` displayed `NPU 100%` continuously even when no neural network workload was running. This occurred due to three compound bugs:

1. **Kernel Driver `idle_mask` Bug (`etnaviv_gpu.c`):**  
   When attempting to autosuspend, the driver checked hardware register `VIVS_HI_IDLE_STATE` against `gpu->idle_mask`. By default, `idle_mask` checked bits for 3D GPU units (Shader core `SH`, bit 3 = 0x8; Tensor Processor `TP`, bit 18 = 0x40000) that do not exist on the VIP9000 NPU. The hardware read `0x7ffbbff6`, failing the comparison and returning `-EBUSY` (`GPU not yet idle, mask: 0x7ffbbff6`). Consequently, the driver never transitioned to `suspended`.
2. **Continuous Clock Ticking:**  
   Because the NPU never entered `suspended`, the kernel accumulated active time at 1,000 ms/sec while completely idle, tricking monitors into calculating 100% load.
3. **Flawed Fallback in `opi-mon`:**  
   Early versions of `opi-mon` had a hardcoded override:
   ```bash
   # Flawed legacy fallback:
   if [ "$active_delta" -eq 0 ] && [ "$npu_status" = "active" ]; then
       npu_load=100
   fi
   ```

### The Resolution Applied in this Package:
1. **`etnaviv_gpu.c` Patched:** Excluded `SH` (0x8), `TP` (0x40000), and `FE` (0x1) from `gpu->idle_mask` for `model == 0x9000`, allowing the NPU to cleanly autosuspend after 200 ms of inactivity.
2. **`etnaviv_buffer.c` Patched:** Bypassed 3D Pixel Engine (PE) stalls during buffer close on `model == 0x9000`.
3. **`opi-mon` Refactored:** Removed the erroneous `active -> 100%` override and added dual-mode telemetry for both `etnaviv` and `vipcore`.

---

## 4. Usage Commands

```bash
# Run continuous live dashboard (1s refresh)
opi-mon

# Run with customized refresh rate (e.g. every 2 seconds)
opi-mon 2

# Output a single telemetry snapshot and exit (useful in automated test scripts)
opi-mon -1
# or
opi-mon --once
```

---

## 5. File Locations & Symlinks

- **Primary Source:** `/home/ukhan/NPU_modules_opi4a_6.18.44/opi-mon`
- **Vendor Mirror:** `/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/opi-mon`
- **System-Wide Binary:** `/usr/local/bin/opi-mon` (symlinked to `/home/ukhan/NPU_modules_opi4a_6.18.44/opi-mon`)
