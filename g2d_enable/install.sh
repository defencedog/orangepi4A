#!/usr/bin/env bash
set -euo pipefail

echo "================================================================"
echo "  Orange Pi 4A (Allwinner T527) — G2D 2D Accelerator Installer"
echo "================================================================"

if [[ $EUID -ne 0 ]]; then
   echo "[ERR] Please run this installer with sudo: sudo ./install.sh" >&2
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DTB_PATH="/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb"

# 1. Backup and install Device Tree Blob
echo "[1/5] Installing G2D-enabled Device Tree Blob..."
if [[ -f "$DTB_PATH" && ! -f "${DTB_PATH}.bak" ]]; then
    cp "$DTB_PATH" "${DTB_PATH}.bak"
    echo "      Backed up original DTB to ${DTB_PATH}.bak"
fi
cp "$SCRIPT_DIR/dtb/sun55i-t527-orangepi-4a-audio.dtb" "$DTB_PATH"

# 2. Install sunxi_g2d.ko kernel module
echo "[2/5] Installing sunxi_g2d.ko kernel module..."
"$SCRIPT_DIR/kernel/install_kmod.sh"

# 3. Install module autoload and udev rules
echo "[3/5] Installing /etc/modules-load.d/g2d.conf and udev rules..."
cp "$SCRIPT_DIR/config/g2d.conf" /etc/modules-load.d/g2d.conf
cp "$SCRIPT_DIR/config/99-g2d.rules" /etc/udev/rules.d/99-g2d.rules
udevadm control --reload-rules || true
udevadm trigger || true

# 4. Load or reload sunxi_g2d module
echo "[4/5] Loading sunxi_g2d kernel module..."
if lsmod | grep -q "^sunxi_g2d"; then
    rmmod sunxi_g2d
fi
modprobe sunxi_g2d
chmod 666 /dev/g2d /dev/dma_heap/system 2>/dev/null || true

# 5. Verify /dev/g2d
echo "[5/5] Verifying /dev/g2d and IOMMU attachment..."
ls -l /dev/g2d
dmesg | grep -i g2d | tail -n 5 || true

echo
echo "================================================================"
echo "[SUCCESS] Allwinner T527 G2D 2D Accelerator Enabled!"
echo "================================================================"
echo "Run verification and benchmarks:"
echo "  ./run_samples.sh"
echo "================================================================"
