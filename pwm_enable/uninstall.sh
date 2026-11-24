#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] Please run with sudo: sudo ./uninstall.sh" >&2
    exit 1
fi

DTB_PATH="/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb"
KVER="$(uname -r)"

systemctl disable --now opi4a-fan-pwm.service 2>/dev/null || true
rm -f /etc/systemd/system/opi4a-fan-pwm.service
rm -f /usr/local/bin/opi4a-fan-pwm.sh
rm -f /etc/modules-load.d/pwm-sun55i-t527.conf
rmmod pwm_sun55i_t527 2>/dev/null || true
rm -f "/lib/modules/${KVER}/extra/pwm-sun55i-t527.ko"
depmod -a
systemctl daemon-reload

if [[ -f "${DTB_PATH}.bak.pre_pwm" ]]; then
    cp -a "${DTB_PATH}.bak.pre_pwm" "$DTB_PATH"
    echo "[OK] Restored ${DTB_PATH} from ${DTB_PATH}.bak.pre_pwm (reboot to apply)."
fi
echo "[OK] Uninstalled pwm-sun55i-t527 and opi4a-fan-pwm.service."
