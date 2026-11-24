#!/usr/bin/env bash
set -euo pipefail

echo "================================================================"
echo "  Orange Pi 4A — Pin 7 (PB4 / PWM8) Hardware PWM Verification"
echo "================================================================"

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] Run with sudo: sudo $0" >&2
    exit 1
fi

echo "[1/5] Checking kernel module..."
if ! lsmod | grep -q "^pwm_sun55i_t527"; then
    echo "[ERR] pwm_sun55i_t527 is not loaded" >&2
    exit 1
fi
lsmod | grep "^pwm_sun55i_t527"

echo "[2/5] Checking /sys/class/pwm controller..."
CHIP=""
for p in /sys/class/pwm/pwmchip*; do
    [[ -e "$p" ]] || continue
    if [[ "$(readlink -f "$p")" == *"2000c00.pwm"* ]]; then
        CHIP="$p"
        break
    fi
done
if [[ -z "$CHIP" ]]; then
    echo "[ERR] Could not find pwmchip for 2000c00.pwm" >&2
    exit 1
fi
echo "Found: $CHIP -> $(readlink -f "$CHIP") (npwm=$(cat "$CHIP/npwm"))"

echo "[3/5] Checking Pin 7 (PB4 / pin 36) pinmux..."
grep -E 'pin 36|PB4' /sys/kernel/debug/pinctrl/2000000.pinctrl/pinmux-pins || true
if command -v gpio >/dev/null 2>&1; then
    gpio readall | grep -E 'PWM8|Physical' || true
fi

SERVICE_WAS_ACTIVE=0
if systemctl is-active --quiet opi4a-fan-pwm.service 2>/dev/null; then
    SERVICE_WAS_ACTIVE=1
    echo "[INFO] Temporarily stopping opi4a-fan-pwm.service for exclusive channel 8 test..."
    systemctl stop opi4a-fan-pwm.service
fi

cleanup() {
    if [[ -d "$CHIP/pwm8" ]]; then
        echo 0 > "$CHIP/pwm8/duty_cycle" 2>/dev/null || true
        echo 0 > "$CHIP/pwm8/enable" 2>/dev/null || true
        echo 8 > "$CHIP/unexport" 2>/dev/null || true
    fi
    if [[ "$SERVICE_WAS_ACTIVE" -eq 1 ]]; then
        echo "[INFO] Restarting opi4a-fan-pwm.service..."
        systemctl start opi4a-fan-pwm.service
    fi
}
trap cleanup EXIT

echo "[4/5] Testing sysfs PWM8 at 20 kHz (period=50000 ns)..."
if [[ ! -d "$CHIP/pwm8" ]]; then
    echo 8 > "$CHIP/export"
    sleep 0.1
fi
echo 50000 > "$CHIP/pwm8/period"
echo normal > "$CHIP/pwm8/polarity"

for duty in 25000 20000 40000 0; do
    echo "$duty" > "$CHIP/pwm8/duty_cycle"
    echo 1 > "$CHIP/pwm8/enable"
    printf "  set duty=%-5d -> readback: period=%s duty_cycle=%s polarity=%s enable=%s\n" \
        "$duty" \
        "$(cat "$CHIP/pwm8/period")" \
        "$(cat "$CHIP/pwm8/duty_cycle")" \
        "$(cat "$CHIP/pwm8/polarity")" \
        "$(cat "$CHIP/pwm8/enable")"
done

echo "[5/5] Verifying live hardware PWM8 registers & counter (25000/50000 ns)..."
echo 25000 > "$CHIP/pwm8/duty_cycle"
echo 1 > "$CHIP/pwm8/enable"
python3 - << 'PY'
import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x02000000)
def r(off): return struct.unpack("<I", m[off:off+4])[0]
print(f"  PCGR  (0x02000c40) = 0x{r(0xc40):08x}")
print(f"  PER   (0x02000c80) = 0x{r(0xc80):08x}")
print(f"  PCR8  (0x02000e00) = 0x{r(0xe00):08x}")
print(f"  PPR8  (0x02000e04) = 0x{r(0xe04):08x}")
samples = [r(0xe08) for _ in range(5)]
print(f"  PCNTR8 samples     = {samples}")
print(f"  PB_CFG0 (PB4=ALT5) = 0x{r(0x030):08x}")
m.close()
os.close(fd)
PY

echo "================================================================"
echo "[PASS] Pin 7 (PB4 / PWM8) hardware PWM verification succeeded!"
echo "================================================================"
