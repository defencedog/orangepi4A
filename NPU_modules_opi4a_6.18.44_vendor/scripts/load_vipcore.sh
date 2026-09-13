#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "============================================================"
echo "  Allwinner T527 VIPCore Driver Loader (Linux 6.18.44)"
echo "============================================================"

# 1. Check and unload etnaviv if active
if lsmod | grep -q etnaviv; then
    echo "[!] Mainline etnaviv module detected. Unloading etnaviv..."
    sudo modprobe -r etnaviv || {
        echo "[-] Failed to unload etnaviv. Forcing unbind..."
        if [ -e /sys/bus/platform/drivers/etnaviv/7122000.npu ]; then
            echo 7122000.npu | sudo tee /sys/bus/platform/drivers/etnaviv/unbind >/dev/null
        fi
        sudo modprobe -r etnaviv
    }
fi

# 2. Check if vipcore is already loaded
if lsmod | grep -q vipcore; then
    echo "[*] vipcore module is already loaded."
else
    echo "[+] Inserting vipcore.ko..."
    sudo insmod "${BASE_DIR}/kernel/vipcore.ko"
fi

# 3. Wait for device node
sleep 1
if [ -e /dev/vipcore ]; then
    echo "[+] /dev/vipcore node confirmed active:"
    sudo chmod 666 /dev/vipcore
    ls -la /dev/vipcore
    echo "[+] VIPCore initialization successful!"
else
    echo "[-] ERROR: /dev/vipcore did not appear. Check dmesg:"
    dmesg | tail -n 20
    exit 1
fi
