#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$HOME/venv_npu/bin/python3"
DETECTOR="$ROOT/detect_objects.py"
INPUT="$ROOT/Bus-Station.png"
NPU="/sys/devices/platform/soc/7122000.npu"
ACTIVE="$NPU/power/runtime_active_time"
SUSPENDED="$NPU/power/runtime_suspended_time"
DELEGATE="/usr/local/lib/libteflon.so"
[[ ! -f "$DELEGATE" ]] && DELEGATE="/usr/lib/teflon/libteflon.so"

if [[ ! -x "$PYTHON" ]]; then echo "Python not found: $PYTHON" >&2; exit 1; fi
if [[ ! -f "$DETECTOR" || ! -f "$INPUT" ]]; then echo "Detector or input image not found in $ROOT" >&2; exit 1; fi

EXTRA_ARGS=()
MODE="NPU (libteflon.so)"
if [[ "${1:-}" == "--cpu" ]]; then
    MODE="CPU (XNNPACK)"
else
    if [[ -f "$DELEGATE" ]]; then
        EXTRA_ARGS+=("-e" "$DELEGATE")
    else
        echo "Notice: System delegate ($DELEGATE) not found."
        echo "Please install the NPU stack using ~/NPU_modules_opi4a_6.18.44/install.sh"
        echo "Falling back to CPU."
        MODE="CPU (fallback)"
    fi
fi

read_counter() { [[ -r "$1" ]] && cat "$1" || printf "-"; }

printf "====================================================\\n"
printf " NPU Detection Telemetry (10 runs)\\n"
printf " Target Device : Orange Pi 4A (Allwinner T527 VIP9000)\\n"
printf " Execution Mode: %s\\n" "$MODE"
printf " Input Image   : %s\\n" "$INPUT"
printf "====================================================\\n\\n"
printf "%-4s %-14s %-14s %-16s %-12s\\n" RUN ACTIVE_BEFORE ACTIVE_AFTER ACTIVE_DELTA_MS ELAPSED_MS

for i in $(seq 1 10); do
    before="$(read_counter "$ACTIVE")"
    start_ns="$(date +%s%N)"
    output="$ROOT/bus_station_detected_${i}.jpg"
    "$PYTHON" "$DETECTOR" -i "$INPUT" -o "$output" "${EXTRA_ARGS[@]}" >/dev/null 2>&1
    rc=$?
    end_ns="$(date +%s%N)"
    after="$(read_counter "$ACTIVE")"
    elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
    if [[ "$before" != "-" && "$after" != "-" ]]; then
        delta_ms=$(( after - before ))
    else
        delta_ms="-"
    fi
    printf "%-4s %-14s %-14s %-16s %-12s rc=%s\\n" "$i" "$before" "$after" "$delta_ms" "$elapsed_ms" "$rc"
done

printf "\\nFinal NPU runtime status: "; cat "$NPU/power/runtime_status" 2>/dev/null || printf "unavailable"; printf "\\n"
printf "NPU total active time   : "; read_counter "$ACTIVE"; printf " ms\\n"
printf "NPU total suspended time: "; read_counter "$SUSPENDED"; printf " ms\\n"

if command -v /usr/local/bin/opi-mon >/dev/null 2>&1; then
    printf "\\n--- Live opi-mon Telemetry Snapshot ---\\n"
    /usr/local/bin/opi-mon --once
fi
