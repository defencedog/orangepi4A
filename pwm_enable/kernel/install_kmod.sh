#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] Run with sudo: sudo $0" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER="$(uname -r)"
DEST_DIR="/lib/modules/${KVER}/extra"

mkdir -p "$DEST_DIR"
install -m 0644 "${SCRIPT_DIR}/pwm-sun55i-t527.ko" "${DEST_DIR}/pwm-sun55i-t527.ko"
depmod -a
echo "[OK] Installed ${DEST_DIR}/pwm-sun55i-t527.ko"
