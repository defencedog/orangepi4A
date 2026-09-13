#!/bin/bash
set -euo pipefail

echo "[+] Unloading vipcore module..."
if lsmod | grep -q vipcore; then
    sudo rmmod vipcore
    echo "[+] vipcore unloaded cleanly."
else
    echo "[*] vipcore is not loaded."
fi
