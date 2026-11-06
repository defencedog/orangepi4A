#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/samples"

PYTHON_BIN="${PYTHON_BIN:-/home/ukhan/venv_npu/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi
export PYTHONDONTWRITEBYTECODE=1

echo "================================================================"
echo "  Allwinner T527 G2D Benchmark & Verification Suite (C + Python)"
echo "================================================================"
echo

echo "--- [C Test 1/5] 1920x1080 Hardware 90-Degree Rotation (G2D_ROT) ---"
./g2d_rotation
echo

echo "--- [C Test 2/5] 1920x1080 Solid Color Fill (RED) ---"
./g2d_color_fill
echo

echo "--- [C Test 3/5] 1920x1080 Format Conversion (ARGB8888 -> YUV420 NV21) ---"
./g2d_format_conversion
echo

echo "--- [C Test 4/5] 4096x4096 -> 1920x1080 Downscaling ---"
./g2d_scaler_or_down_sampling
echo

echo "--- [C Test 5/5] Real Dummy Image Pipeline (assets/dummy_input.ppm) ---"
./g2d_image_demo assets/dummy_input.ppm assets/output
echo

echo "================================================================"
echo "  Python Zero-Copy DMA-BUF + NumPy G2D Verification Suite"
echo "  Python Interpreter: $PYTHON_BIN"
echo "================================================================"
echo

echo "--- [Python Test 1/5] 1920x1080 Hardware Rotation & Mirror ---"
"$PYTHON_BIN" python/g2d_rotation_or_mirror.py
echo

echo "--- [Python Test 2/5] 1920x1080 Solid & ROI Color Fill ---"
"$PYTHON_BIN" python/g2d_color_fill.py
echo

echo "--- [Python Test 3/5] 1920x1080 Format Conversion (ARGB8888 -> YUV420 NV21) ---"
"$PYTHON_BIN" python/g2d_format_conversion.py
echo

echo "--- [Python Test 4/5] 4096x4096 -> 1920x1080 Downscaling ---"
"$PYTHON_BIN" python/g2d_scaler_or_down_sampling.py
echo

echo "--- [Python Test 5/5] Real Image Pipeline (assets/dummy_input.jpg) ---"
"$PYTHON_BIN" python/g2d_image_demo.py assets/dummy_input.jpg assets/output_python
echo

echo "[OK] All 5 C tests and all 5 Python G2D verification tests completed successfully!"
