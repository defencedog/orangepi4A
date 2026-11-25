# Fan Calibration Script (`test_fan_holding.sh`)

`test_fan_holding.sh` calibrates a PWM-driven 2-wire DC fan on **Orange Pi 4A Physical Pin 7 (`PB4` / `PWM8`)** by running two sequential sweeps:

1. **Decrement cycle (Minimum Holding Duty):** Spins the fan at `100%` first so the rotor reaches full speed, then steps downward (`85% → 75% → 65% → 60% → 55% → 50% → 45% → 40%`) to reveal the lowest duty cycle that keeps the fan spinning without stalling.
2. **Increment cycle (Minimum Startup / Kick-Start Duty):** Stops the fan at `0%` so the rotor comes to rest, then steps upward (`40% → 45% → 50% → 55% → 60% → 65% → 75% → 85% → 100%`) to reveal the lowest duty cycle that reliably starts the fan from a dead stop.

If `opi4a-fan-pwm.service` is running when you launch the script, it is stopped temporarily for exclusive access to `pwm8` and automatically restarted when the script exits or is interrupted (`Ctrl+C`).

---

## Usage

```bash
sudo ./test_fan_holding.sh [step_seconds] [spinup_seconds] [freq_hz]
```

Show help without root:

```bash
./test_fan_holding.sh --help
```

---

## Arguments

| Position | Name | Default | Description |
| --- | --- | --- | --- |
| `$1` | `step_seconds` | `4.0` | Duration (seconds) to hold each percentage step in both decrement and increment phases. |
| `$2` | `spinup_seconds` | `3.0` | Duration (seconds) for the initial `100%` spin-up (Phase 1) and the `0%` dead-stop pause before Phase 2. |
| `$3` | `freq_hz` | `20000` | PWM switching frequency in Hz (`period = 1,000,000,000 / freq_hz` ns). Valid range: `1` to `1000000`. |

---

## Examples

### 1. Default Calibration (`20 kHz`, `4 s` per step, `3 s` spin-up/pause)
```bash
sudo ./test_fan_holding.sh
```

### 2. Faster Sweep (`2 s` per step, `2 s` spin-up/pause at `20 kHz`)
```bash
sudo ./test_fan_holding.sh 2 2
```

### 3. Test Lower PWM Frequencies (Check Low-RPM Holding vs. Audible Whine)
```bash
# 1 kHz (period = 1,000,000 ns)
sudo ./test_fan_holding.sh 3 2 1000

# 250 Hz (period = 4,000,000 ns)
sudo ./test_fan_holding.sh 3 2 250
```

---

## Interpreting Results for `/etc/default/opi4a-fan-pwm`

1. **`DUTY_LOW_NS` (Minimum Running Speed):** Pick a percentage **at least 5% above** the last step that kept spinning cleanly during **Phase 1 (Decrement)**.
   - Example: if the fan holds down to `55%` and stalls at `50%`, set `DUTY_LOW_NS` to **60%** (`30000` ns at `20 kHz`).
2. **`KICK_DUTY_NS` (Startup Pulse from `0%`):** Pick a percentage **at or above** the step where the fan started reliably from rest during **Phase 2 (Increment)**.
   - Example: if the fan starts reliably at `85%`, set `KICK_DUTY_NS` to **90%** (`45000` ns at `20 kHz`) for `KICK_SEC=2`.
3. **Top Tier (`DUTY_MAX_NS`):** Cap at **95%** (`47500` ns at `20 kHz`) if you want margin below `100%` continuous DC.
