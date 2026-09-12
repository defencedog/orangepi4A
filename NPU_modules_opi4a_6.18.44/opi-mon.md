# `opi-mon` — Hardware Telemetry & NPU Load Measurement Guide

`opi-mon` is an ultra-lightweight, 37-column mobile/SSH-optimized terminal monitor designed specifically for the **Orange Pi 4A (Allwinner T527)**. It renders real-time telemetry across CPU, NPU (VeriSilicon VIP9000), GPU (ARM Mali-G57), RAM, and Swap with 1-second refresh intervals.

---

## 1. Live Telemetry Layout

```text
 Orange Pi 4A (T527)
 04:02:37 · Up: 1d 4h · Load: 0.22
─────────────────────────────────────
 CPU   1% [░░░░░░░░░░] 37.2°C  0.48GHz
 NPU   0% [░░░░░░░░░░] 36.7°C  2 TOPS
 GPU  45% [████░░░░░░] 36.7°C   400MHz
 RAM  34% [███░░░░░░░] 1.2/3.7G 2528M free
 SWP  70% [███████░░░] 1.4/1.9G
─────────────────────────────────────
 [Ctrl+C] Exit  ·  Refresh: 1s
```

---

## 2. How NPU Utilization is Measured

Unlike traditional CPUs (which expose tick counters in `/proc/stat`) or devfreq GPUs (which expose load files in `/sys/class/devfreq/`), the VeriSilicon VIP9000 NPU operates as a power-managed accelerator via the Linux DRM `etnaviv` driver.

### 2.1 Sysfs Telemetry Interface
NPU activity is tracked directly by the kernel's Runtime Power Management (Runtime PM) subsystem:
- **Active Time Counter:** `/sys/devices/platform/soc/7122000.npu/power/runtime_active_time`  
  Reports the cumulative time (in milliseconds) the VIP9000 hardware execution units spent awake and processing command streams since boot.
- **Power State:** `/sys/devices/platform/soc/7122000.npu/power/runtime_status`  
  Reports `suspended` (core clock-gated and powered down) or `active` (inference executing).
- **Thermal Sensor:** `/sys/class/thermal/thermal_zone*/temp` (associated with `npu-thermal`).

### 2.2 Mathematical Duty-Cycle Formula
`opi-mon` measures dynamic NPU duty cycle by computing the active time delta over each refresh window:

$$
\Delta t_{\text{active}} = \text{runtime\_active\_time}_t - \text{runtime\_active\_time}_{t - \Delta t}
$$

$$
\text{NPU Load (\%)} = \min\left(100, \frac{\Delta t_{\text{active}} \times 100}{\text{REFRESH\_INTERVAL} \times 1000}\right)
$$

- **When Idle:** The NPU is autosuspended. $\Delta t_{\text{active}} = 0\text{ ms} \implies \text{NPU Load} = \mathbf{0\%}$.
- **Under Partial Load:** (e.g. 50 ms of inference in a 1,000 ms window) $\implies \text{NPU Load} = \mathbf{5\%}$.
- **Under Full Sustained Load:** (e.g. continuous vision or batch inference) $\Delta t_{\text{active}} \approx 1,000\text{ ms} \implies \text{NPU Load} = \mathbf{100\%}$.

---

## 3. The 100% Idle Load Bug & How It Was Fixed

In earlier builds, users reported that `opi-mon` displayed `NPU 100%` continuously even when no neural network workload was running. This occurred due to three compound bugs:

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
3. **`opi-mon` Refactored:** Removed the erroneous `active -> 100%` override. `opi-mon` now strictly tracks true mathematical duty cycle.

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
