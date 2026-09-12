#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${HOME}/venv_npu"

if [ -f "${VENV_PATH}/bin/python3" ]; then
    PYTHON="${VENV_PATH}/bin/python3"
else
    PYTHON="python3"
fi

echo "============================================================"
echo " Orange Pi 4A (Allwinner T527) Vision AI Demo Suite"
echo " Python Runtime: $(${PYTHON} --version)"
echo " Working Dir   : ${SCRIPT_DIR}"
echo "============================================================"

echo ""
echo ">>> [1/2] Running MobileNet V1 Image Classification..."
${PYTHON} "${SCRIPT_DIR}/classification.py" -i "${SCRIPT_DIR}/grace_hopper.jpg"

echo ""
echo ">>> [2/2] Running SSD MobileNet V1 Object Detection..."
${PYTHON} "${SCRIPT_DIR}/detect_objects.py" -i "${SCRIPT_DIR}/grace_hopper.jpg" -o "${SCRIPT_DIR}/detected_output.jpg"

echo ""
echo ">>> Demo completed successfully! Annotated image saved to ${SCRIPT_DIR}/detected_output.jpg"
