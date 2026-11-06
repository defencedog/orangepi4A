#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "[ERR] Please run with sudo: sudo ./install_kmod.sh" >&2
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER="$(uname -r)"
DEST_DIR="/lib/modules/${KVER}/extra"

mkdir -p "$DEST_DIR"
cp "$SCRIPT_DIR/sunxi_g2d.ko" "$DEST_DIR/sunxi_g2d.ko"
depmod -a

echo "[OK] Installed sunxi_g2d.ko to $DEST_DIR/sunxi_g2d.ko"
