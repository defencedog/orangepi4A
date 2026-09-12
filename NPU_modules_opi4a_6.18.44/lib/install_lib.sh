#!/usr/bin/env bash
set -e

if [[ $EUID -ne 0 ]]; then
   echo "[ERR] This script must be run as root (sudo)" >&2
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[*] Installing patched Mesa Teflon delegate..."
cp "$SCRIPT_DIR/libteflon.so" /usr/local/lib/libteflon.so
chmod 0755 /usr/local/lib/libteflon.so

mkdir -p /usr/lib/teflon
ln -sf /usr/local/lib/libteflon.so /usr/lib/teflon/libteflon.so

echo "[*] Running ldconfig..."
ldconfig

echo "[OK] libteflon.so deployed to /usr/local/lib/ and /usr/lib/teflon/."
