#!/usr/bin/env bash
set -euo pipefail

echo "================================================================"
echo "  Orange Pi 4A (Allwinner T527) — Hardware PWM8 (Pin 7) Setup"
echo "================================================================"

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] Please run this installer with sudo: sudo ./install.sh" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DTB_PATH="/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb"

echo "[1/5] Backing up and installing PWM8 + G2D Device Tree Blob..."
if [[ -f "$DTB_PATH" && ! -f "${DTB_PATH}.bak.pre_pwm" ]]; then
    cp -a "$DTB_PATH" "${DTB_PATH}.bak.pre_pwm"
    echo "      Backed up previous DTB to ${DTB_PATH}.bak.pre_pwm"
fi
install -m 0644 "${SCRIPT_DIR}/dtb/sun55i-t527-orangepi-4a-audio.dtb" "$DTB_PATH"

echo "[2/5] Installing pwm-sun55i-t527.ko kernel module..."
"${SCRIPT_DIR}/kernel/install_kmod.sh"

echo "[3/5] Installing /etc/modules-load.d/pwm-sun55i-t527.conf..."
install -m 0644 "${SCRIPT_DIR}/config/pwm-sun55i-t527.conf" /etc/modules-load.d/pwm-sun55i-t527.conf

echo "[4/5] Installing fan control script and systemd service..."
install -m 0755 "${SCRIPT_DIR}/scripts/opi4a-fan-pwm.sh" /usr/local/bin/opi4a-fan-pwm.sh
if [[ ! -f /etc/default/opi4a-fan-pwm ]]; then
    install -m 0644 "${SCRIPT_DIR}/config/opi4a-fan-pwm.conf" /etc/default/opi4a-fan-pwm
fi
install -m 0644 "${SCRIPT_DIR}/config/opi4a-fan-pwm.service" /etc/systemd/system/opi4a-fan-pwm.service
systemctl daemon-reload
systemctl enable opi4a-fan-pwm.service

echo "[5/5] Loading module (reboot required if DTB was not active yet)..."
modprobe pwm-sun55i-t527 || true
if [[ -d /sys/class/pwm/pwmchip0 ]]; then
    systemctl restart opi4a-fan-pwm.service
    echo "[SUCCESS] Hardware PWM active and opi4a-fan-pwm.service started!"
else
    echo "[INFO] DTB updated in /boot. Reboot to activate pwm@2000c00, then run:"
    echo "       sudo ./scripts/test_pwm_pin7.sh"
fi
