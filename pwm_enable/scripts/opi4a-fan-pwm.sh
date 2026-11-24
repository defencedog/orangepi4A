#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="/etc/default/opi4a-fan-pwm"

PWM_DEV_PATTERN="2000c00.pwm"
PWM_CHANNEL=8
PERIOD_NS=50000
POLARITY="normal"
POLL_SEC=2
HYSTERESIS_C=3
KICK_DUTY_NS=30000
KICK_SEC=2

TEMP_LOW_C=55
TEMP_MID_C=65
TEMP_HIGH_C=73
TEMP_MAX_C=80

DUTY_LOW_NS=20000
DUTY_MID_NS=30000
DUTY_HIGH_NS=40000
DUTY_MAX_NS=50000
VERBOSE=0

if [[ -r "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

find_pwmchip() {
    local chip resolved
    for chip in /sys/class/pwm/pwmchip*; do
        [[ -e "$chip" ]] || continue
        resolved="$(readlink -f "$chip")"
        if [[ "$resolved" == *"$PWM_DEV_PATTERN"* ]]; then
            echo "$chip"
            return 0
        fi
    done
    return 1
}

read_max_temp() {
    local zone raw temp_mc max_mc=0 max_type="unknown" ztype
    for zone in /sys/class/thermal/thermal_zone*; do
        [[ -r "$zone/temp" ]] || continue
        raw="$(cat "$zone/temp" 2>/dev/null || true)"
        [[ "$raw" =~ ^-?[0-9]+$ ]] || continue
        temp_mc="$raw"
        if (( temp_mc > max_mc )); then
            max_mc="$temp_mc"
            ztype="$(cat "$zone/type" 2>/dev/null || basename "$zone")"
            max_type="$ztype"
        fi
    done
    echo "$max_mc $max_type"
}

PWM_CHIP="$(find_pwmchip || true)"
if [[ -z "$PWM_CHIP" ]]; then
    echo "[ERR] No pwmchip matching '$PWM_DEV_PATTERN' found under /sys/class/pwm" >&2
    exit 1
fi

PWM_CH_PATH="${PWM_CHIP}/pwm${PWM_CHANNEL}"
EXPORTED_BY_US=0
CLEANED_UP=0

cleanup() {
    if [[ "$CLEANED_UP" -eq 1 ]]; then
        return 0
    fi
    CLEANED_UP=1
    if [[ -d "$PWM_CH_PATH" ]]; then
        echo 0 > "${PWM_CH_PATH}/duty_cycle" 2>/dev/null || true
        echo 0 > "${PWM_CH_PATH}/enable" 2>/dev/null || true
        if [[ "$EXPORTED_BY_US" -eq 1 ]]; then
            echo "$PWM_CHANNEL" > "${PWM_CHIP}/unexport" 2>/dev/null || true
        fi
    fi
    echo "[INFO] Fan PWM stopped and cleaned up."
}
on_signal() {
    cleanup
    exit 0
}
trap cleanup EXIT
trap on_signal INT TERM

if [[ ! -d "$PWM_CH_PATH" ]]; then
    echo "$PWM_CHANNEL" > "${PWM_CHIP}/export"
    EXPORTED_BY_US=1
    for _ in $(seq 1 20); do
        [[ -w "${PWM_CH_PATH}/period" ]] && break
        sleep 0.05
    done
fi

echo 0 > "${PWM_CH_PATH}/enable" 2>/dev/null || true
echo "$PERIOD_NS" > "${PWM_CH_PATH}/period"
echo "$POLARITY" > "${PWM_CH_PATH}/polarity"
echo 0 > "${PWM_CH_PATH}/duty_cycle"
echo 1 > "${PWM_CH_PATH}/enable"

echo "[INFO] Started opi4a-fan-pwm on ${PWM_CH_PATH} (period=${PERIOD_NS}ns, polarity=${POLARITY})"

current_tier=0
current_duty=0

while true; do
    read -r max_mc max_zone < <(read_max_temp)
    temp_c=$(( max_mc / 1000 ))

    # Compute target tier with hysteresis on step-down
    target_tier="$current_tier"
    if (( temp_c >= TEMP_MAX_C )); then
        target_tier=4
    elif (( temp_c >= TEMP_HIGH_C )); then
        if (( current_tier < 4 )) || (( temp_c < TEMP_MAX_C - HYSTERESIS_C )); then
            target_tier=3
        fi
    elif (( temp_c >= TEMP_MID_C )); then
        if (( current_tier < 3 )) || (( temp_c < TEMP_HIGH_C - HYSTERESIS_C )); then
            target_tier=2
        fi
    elif (( temp_c >= TEMP_LOW_C )); then
        if (( current_tier < 2 )) || (( temp_c < TEMP_MID_C - HYSTERESIS_C )); then
            target_tier=1
        fi
    else
        if (( current_tier == 0 )) || (( temp_c < TEMP_LOW_C - HYSTERESIS_C )); then
            target_tier=0
        fi
    fi

    case "$target_tier" in
        0) target_duty=0 ;;
        1) target_duty="$DUTY_LOW_NS" ;;
        2) target_duty="$DUTY_MID_NS" ;;
        3) target_duty="$DUTY_HIGH_NS" ;;
        4) target_duty="$DUTY_MAX_NS" ;;
    esac

    if (( target_duty != current_duty )); then
        if (( current_duty == 0 && target_duty > 0 && target_duty < KICK_DUTY_NS )); then
            echo "[INFO] Max temp ${temp_c}C (${max_zone}): kick-start at $(( KICK_DUTY_NS * 100 / PERIOD_NS ))% for ${KICK_SEC}s"
            echo "$KICK_DUTY_NS" > "${PWM_CH_PATH}/duty_cycle"
            sleep "$KICK_SEC"
        fi
        echo "$target_duty" > "${PWM_CH_PATH}/duty_cycle"
        pct=$(( target_duty * 100 / PERIOD_NS ))
        echo "[INFO] Max temp ${temp_c}C (${max_zone}) -> tier=${target_tier}, duty=${target_duty}/${PERIOD_NS}ns (${pct}%)"
        current_duty="$target_duty"
        current_tier="$target_tier"
    elif [[ "$VERBOSE" -eq 1 ]]; then
        pct=$(( current_duty * 100 / PERIOD_NS ))
        echo "[DBG] Max temp ${temp_c}C (${max_zone}) -> tier=${current_tier}, duty=${pct}%"
    fi

    sleep "$POLL_SEC" &
    wait $! || true
done
