#!/usr/bin/env bash
set -euo pipefail

# Two-phase PWM fan calibration script for Orange Pi 4A Pin 7 (PB4 / PWM8)
#   Phase 1 (Decrement): 100% spin-up, then step DOWN to find minimum holding duty cycle
#   Phase 2 (Increment): 0% stop pause, then step UP to find minimum startup (kick-start) duty cycle
#
# Usage: sudo ./test_fan_holding.sh [step_seconds] [spinup_seconds] [freq_hz]

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cat << 'EOF'
Usage: sudo ./test_fan_holding.sh [step_seconds] [spinup_seconds] [freq_hz]

Arguments:
  step_seconds    Seconds to hold each duty step (default: 4.0)
  spinup_seconds  Seconds for initial 100% spin-up and 0% stop pause (default: 3.0)
  freq_hz         Hardware PWM frequency in Hz (default: 20000)

Phases:
  1. Decrement: 100% -> 85 -> 75 -> 65 -> 60 -> 55 -> 50 -> 45 -> 40%
  2. Increment:   0% -> 40 -> 45 -> 50 -> 55 -> 60 -> 65 -> 75 -> 85 -> 100%
EOF
    exit 0
fi

STEP_SEC="${1:-4.0}"
SPINUP_SEC="${2:-3.0}"
FREQ_HZ="${3:-20000}"

if ! [[ "$FREQ_HZ" =~ ^[0-9]+$ ]] || (( FREQ_HZ <= 0 || FREQ_HZ > 1000000 )); then
    echo "[ERR] freq_hz must be a positive integer <= 1000000 (got '$FREQ_HZ')" >&2
    exit 1
fi

PERIOD_NS=$(( 1000000000 / FREQ_HZ ))
PWM_DEV_PATTERN="2000c00.pwm"
PWM_CHANNEL=8

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] Run with sudo: sudo $0 [step_seconds] [spinup_seconds] [freq_hz]" >&2
    exit 1
fi

CHIP=""
for p in /sys/class/pwm/pwmchip*; do
    [[ -e "$p" ]] || continue
    if [[ "$(readlink -f "$p")" == *"$PWM_DEV_PATTERN"* ]]; then
        CHIP="$p"
        break
    fi
done

if [[ -z "$CHIP" ]]; then
    echo "[ERR] No pwmchip matching '$PWM_DEV_PATTERN' found under /sys/class/pwm" >&2
    exit 1
fi

WAS_ACTIVE=0
if systemctl is-active --quiet opi4a-fan-pwm.service 2>/dev/null; then
    WAS_ACTIVE=1
    systemctl stop opi4a-fan-pwm.service
fi

CLEANED=0
cleanup() {
    if [[ "$CLEANED" -eq 1 ]]; then
        return 0
    fi
    CLEANED=1
    if [[ -d "${CHIP}/pwm${PWM_CHANNEL}" ]]; then
        echo 0 > "${CHIP}/pwm${PWM_CHANNEL}/duty_cycle" 2>/dev/null || true
        echo 0 > "${CHIP}/pwm${PWM_CHANNEL}/enable" 2>/dev/null || true
        echo "$PWM_CHANNEL" > "${CHIP}/unexport" 2>/dev/null || true
    fi
    if [[ "$WAS_ACTIVE" -eq 1 ]]; then
        systemctl start opi4a-fan-pwm.service
    fi
}
on_signal() {
    cleanup
    exit 0
}
trap cleanup EXIT
trap on_signal INT TERM

if [[ ! -d "${CHIP}/pwm${PWM_CHANNEL}" ]]; then
    echo "$PWM_CHANNEL" > "${CHIP}/export"
    for _ in $(seq 1 20); do
        [[ -w "${CHIP}/pwm${PWM_CHANNEL}/period" ]] && break
        sleep 0.05
    done
fi

CH="${CHIP}/pwm${PWM_CHANNEL}"
echo 0 > "${CH}/enable" 2>/dev/null || true
echo "$PERIOD_NS" > "${CH}/period"
echo normal > "${CH}/polarity"
echo "$PERIOD_NS" > "${CH}/duty_cycle"
echo 1 > "${CH}/enable"

echo "[INFO] Fan Calibration on ${CH} (${FREQ_HZ} Hz, period=${PERIOD_NS} ns)"
echo "=== PHASE 1: DECREMENT (Find Minimum Holding Duty Cycle) ==="
echo ">>> SPIN-UP:   100%  (duty_cycle=${PERIOD_NS} / ${PERIOD_NS} ns) for ${SPINUP_SEC}s"
sleep "$SPINUP_SEC" &
wait $! || true

for pct in 85 75 65 60 55 50 45 40; do
    duty=$(( PERIOD_NS * pct / 100 ))
    echo "$duty" > "${CH}/duty_cycle"
    printf ">>> DECREMENT: %3d%%  (duty_cycle=%s / %s ns) for %ss\n" \
        "$pct" \
        "$(cat "${CH}/duty_cycle")" \
        "$(cat "${CH}/period")" \
        "$STEP_SEC"
    sleep "$STEP_SEC" &
    wait $! || true
done

echo "=== PHASE 2: INCREMENT (Find Minimum Dead-Stop Startup Duty Cycle) ==="
echo 0 > "${CH}/duty_cycle"
echo ">>> STOP PAUSE:  0%  (duty_cycle=0 / ${PERIOD_NS} ns) for ${SPINUP_SEC}s"
sleep "$SPINUP_SEC" &
wait $! || true

for pct in 40 45 50 55 60 65 75 85 100; do
    duty=$(( PERIOD_NS * pct / 100 ))
    echo "$duty" > "${CH}/duty_cycle"
    printf ">>> INCREMENT: %3d%%  (duty_cycle=%s / %s ns) for %ss\n" \
        "$pct" \
        "$(cat "${CH}/duty_cycle")" \
        "$(cat "${CH}/period")" \
        "$STEP_SEC"
    sleep "$STEP_SEC" &
    wait $! || true
done

echo 0 > "${CH}/duty_cycle"
echo "[PASS] Calibration complete (fan stopped at 0%)."
