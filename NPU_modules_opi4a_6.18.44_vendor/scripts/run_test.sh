#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export LD_LIBRARY_PATH="${BASE_DIR}/lib:${LD_LIBRARY_PATH:-}"

if [ ! -e /dev/vipcore ]; then
    echo "[!] /dev/vipcore not found. Attempting to load driver..."
    "${SCRIPT_DIR}/load_vipcore.sh"
fi

cd "${BASE_DIR}/sample"
echo "[+] Running vpm_run on sample T527 NBG model..."
"${BASE_DIR}/bin/vpm_run" -s sample.txt -l 1
