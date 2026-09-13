#!/bin/bash
# YOLOX-S Hardware NPU Object Detection Demo Runner for Orange Pi 4A (Allwinner T527)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/home/ukhan/venv_npu/bin/python3"

MODEL="${SCRIPT_DIR}/models/yolox_s_sim_uint8_t527.nb"
INPUT="${1:-${SCRIPT_DIR}/samples/bus.jpg}"
OUTPUT="${2:-${SCRIPT_DIR}/output/output_yolox.jpg}"
SCORE_THR="${3:-0.35}"
LOOPS="${4:-10}"

# Verify VIPCore hardware device is active
if [ ! -e /dev/vipcore ]; then
    echo "[!] /dev/vipcore not found. Activating VIPCore driver..."
    echo asad | sudo -S npu vipcore
fi

export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

echo "[*] Running YOLOX-S NPU Detection on Orange Pi 4A..."
$VENV_PYTHON "${SCRIPT_DIR}/yolox_infer.py" \
    -m "$MODEL" \
    -i "$INPUT" \
    -o "$OUTPUT" \
    -s "$SCORE_THR" \
    -l "$LOOPS"

echo "[✓] Finished. Result saved to: $OUTPUT"
