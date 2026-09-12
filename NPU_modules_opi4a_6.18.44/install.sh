#!/usr/bin/env bash
set -e

echo "================================================================"
echo "  Orange Pi 4A (Allwinner T527) — NPU Subsystem Installer"
echo "================================================================"

if [[ $EUID -ne 0 ]]; then
   echo "[ERR] Please run this installer with sudo: sudo ./install.sh" >&2
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_USER="${SUDO_USER:-$USER}"

# 1. Kernel Module Installation
echo "[1/6] Installing patched etnaviv.ko..."
"$SCRIPT_DIR/kernel/install_kmod.sh"

# 2. Mesa Teflon Library Installation
echo "[2/6] Installing patched libteflon.so..."
"$SCRIPT_DIR/lib/install_lib.sh"

# 3. Udev and Blacklist Configurations
echo "[3/6] Configuring udev rules and modprobe blacklist..."
cp "$SCRIPT_DIR/config/99-etnaviv-npu.rules" /etc/udev/rules.d/
cp "$SCRIPT_DIR/config/blacklist-etnaviv.conf" /etc/modprobe.d/
udevadm control --reload-rules || true
udevadm trigger || true

# 4. User Group Permissions
echo "[4/6] Ensuring '$REAL_USER' is in 'render' and 'video' groups..."
usermod -aG render,video "$REAL_USER"

# 5. Helper CLI Tools
echo "[5/6] Installing management scripts and telemetry tools..."
cp "$SCRIPT_DIR/NPU_enable.sh" /usr/local/bin/NPU_enable.sh
chmod +x /usr/local/bin/NPU_enable.sh
ln -sf /usr/local/bin/NPU_enable.sh /usr/local/bin/npu

cp "$SCRIPT_DIR/opi-mon" /usr/local/bin/opi-mon
chmod +x /usr/local/bin/opi-mon

# 6. Activation
echo "[6/6] Activating NPU DRM driver..."
/usr/local/bin/NPU_enable.sh enable

echo
echo "================================================================"
echo "[SUCCESS] Allwinner T527 VIP9000 NPU Stack Installed!"
echo "================================================================"
echo "Quick Verification Commands:"
echo "  - Check status   : npu status"
echo "  - Run smoke test : python3 $SCRIPT_DIR/smoke_test/test_npu_smoke.py"
echo "  - View telemetry : opi-mon"
echo "================================================================"
