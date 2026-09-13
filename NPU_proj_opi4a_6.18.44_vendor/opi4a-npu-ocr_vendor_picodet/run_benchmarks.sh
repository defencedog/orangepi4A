#!/usr/bin/env bash
# ==============================================================================
# Benchmark Suite: Two-Stage Layout-Guided OCR on Orange Pi 4A (Allwinner T527)
#
# Hardware: VeriSilicon VIP9000 2.0 TOPS NPU (/dev/vipcore) + 8x Cortex-A55
# Models:
#   1. 1600x1600 Pipeline: picodet_layout_1600.nb + ppocrv6_det_1600.nb @ 200 DPI
#   2. 2048x2048 Pipeline: picodet_layout_2048.nb + ppocrv6_det_2048.nb @ 200 DPI
#   3. Dynamic Recognizer: en_pp_ocrv4_rec_dynamic.mnn (Dynamic Aspect Ratio)
#
# Benchmark Targets:
#   - samples/sample-compressor.pdf
#   - samples/sample-steam.pdf
#   - samples/PublicWaterMassMailing.pdf
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/home/ukhan/venv_npu/bin/python3"

echo "=============================================================================="
echo " Starting Two-Stage Layout-Guided Hardware OCR Benchmarks (VIP9000 NPU)"
echo "=============================================================================="

# Test 1: Sample Compressor (1600x1600 @ 200 DPI)
echo -e "\n>>> [1/6] Running sample-compressor.pdf (1600x1600 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/sample-compressor.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_1600.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_1600.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/compressor_1600_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

# Test 2: Sample Compressor (2048x2048 @ 200 DPI)
echo -e "\n>>> [2/6] Running sample-compressor.pdf (2048x2048 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/sample-compressor.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_2048.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_2048.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/compressor_2048_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

# Test 3: Sample Steam (1600x1600 @ 200 DPI)
echo -e "\n>>> [3/6] Running sample-steam.pdf (1600x1600 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/sample-steam.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_1600.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_1600.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/steam_1600_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

# Test 4: Sample Steam (2048x2048 @ 200 DPI)
echo -e "\n>>> [4/6] Running sample-steam.pdf (2048x2048 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/sample-steam.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_2048.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_2048.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/steam_2048_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

# Test 5: PublicWaterMassMailing (1600x1600 @ 200 DPI)
echo -e "\n>>> [5/6] Running PublicWaterMassMailing.pdf (1600x1600 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/PublicWaterMassMailing.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_1600.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_1600.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/water_1600_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

# Test 6: PublicWaterMassMailing (2048x2048 @ 200 DPI)
echo -e "\n>>> [6/6] Running PublicWaterMassMailing.pdf (2048x2048 @ 200 DPI)..."
$VENV_PYTHON "$SCRIPT_DIR/pdf_ocr.py" "$SCRIPT_DIR/samples/PublicWaterMassMailing.pdf" \
    --dpi 200 \
    --layout-model "$SCRIPT_DIR/models/picodet_layout_2048.nb" \
    --det-model "$SCRIPT_DIR/models/ppocrv6_det_2048.nb" \
    --max-pages 1 \
    --out-dir "$SCRIPT_DIR/benchmarks/water_2048_200dpi" \
    --layout-score-thresh 0.20 --vis --json --md

echo "=============================================================================="
echo " All Two-Stage OCR Benchmarks Finished Successfully!"
echo "=============================================================================="
