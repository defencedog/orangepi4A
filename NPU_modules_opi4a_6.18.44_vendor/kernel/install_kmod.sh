#!/bin/bash
set -euo pipefail
KDIR="/lib/modules/$(uname -r)/extra"
echo "[+] Installing vipcore.ko into ${KDIR}..."
sudo mkdir -p "${KDIR}"
sudo cp "$(dirname "$0")/vipcore.ko" "${KDIR}/"
echo "[+] Running depmod -a..."
sudo depmod -a
echo "[+] vipcore.ko installed successfully."
