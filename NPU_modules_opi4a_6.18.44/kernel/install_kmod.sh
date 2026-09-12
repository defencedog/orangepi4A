#!/usr/bin/env bash
set -e

if [[ $EUID -ne 0 ]]; then
   echo "[ERR] This script must be run as root (sudo)" >&2
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER="$(uname -r)"
DEST_DIR="/lib/modules/$KVER/kernel/drivers/gpu/drm/etnaviv"

echo "[*] Installing patched etnaviv.ko for kernel $KVER..."
mkdir -p "$DEST_DIR"
cp "$SCRIPT_DIR/etnaviv.ko" "$DEST_DIR/etnaviv.ko"
chmod 0644 "$DEST_DIR/etnaviv.ko"

echo "[*] Updating module dependencies (depmod -a)..."
depmod -a

echo "[OK] Kernel module etnaviv.ko installed successfully."
