#!/bin/bash
set -euo pipefail
LIB_DIR="/usr/local/lib"
INC_DIR="/usr/local/include"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[+] Copying libVIPlite.so and libVIPuser.so to ${LIB_DIR}..."
sudo cp "${SCRIPT_DIR}/libVIPlite.so" "${LIB_DIR}/"
sudo cp "${SCRIPT_DIR}/libVIPuser.so" "${LIB_DIR}/"
sudo mkdir -p "${INC_DIR}"
sudo cp "${SCRIPT_DIR}/../include/"*.h "${INC_DIR}/"
echo "[+] Updating ldconfig..."
sudo ldconfig
echo "[+] VIPLite userspace libraries and headers installed successfully."
