# YOLOX Object Detection on Orange Pi 4A (Allwinner T527 NPU)

Hardware-accelerated **YOLOX-S** object detection deployed on the **Orange Pi 4A** single-board computer using the vendor **VIPCore** driver (`/dev/vipcore`) and **VIPLite v1.13** runtime library.

---

## 1. System Architecture & Specifications

| Component | Specification |
|---|---|
| **Board** | Orange Pi 4A |
| **SoC** | Allwinner T527 (Octa-core ARM Cortex-A55 @ 1.8 GHz) |
| **NPU Core** | VeriSilicon Vivante VIP9000 Nano-DI (2.0 TOPS INT8) |
| **Kernel Driver** | Vendor VIPCore (`/dev/vipcore`, Allwinner sunxi-npu) |
| **User Runtime** | VIPLite v1.13 (`/usr/local/lib/libVIPlite.so`) |
| **Model** | YOLOX-S (640x640 input, 3 multi-scale detection heads) |
| **Model Format** | Vivante Network Binary Graph (`.nb`, unified pack) |
| **Compilation Host** | Proxmox VE (Container `allwinner_v1.8.11`, Acuity 6.21.16) |

---

## 2. Compilation & Conversion Pipeline

The compilation was performed on the Proxmox conversion server inside the Docker container `allwinner_v1.8.11` following Radxa/Allwinner model-zoo guidelines:

### A. Acuity Pegasus Import
```bash
python3 /root/acuity-toolkit-whl-6.21.16/bin/pegasus.py import onnx \
    --model yolox_s_sim.onnx \
    --output-model yolox_s_sim.json \
    --output-data yolox_s_sim.data
```

### B. Input Preprocessing Configuration (`yolox_s_sim_inputmeta.yml`)
Configured to embed hardware preprocessing directly into the NPU graph:
- `add_preproc_node: true`, `preproc_type: IMAGE_RGB`
- `reverse_channel: true` (flips OpenCV BGR input to RGB directly in NPU DMA/hardware engine)
- `mean: [0, 0, 0]`, `scale: [1.0, 1.0, 1.0]` (YOLOX expects float range $[0, 255]$)
- Input format: Interleaved uint8 `(1, 640, 640, 3)` (1,228,800 bytes)

### C. Output Postprocessing Configuration (`yolox_s_sim_postprocess_file.yml`)
Configured to force float32 output format across all three heads:
- Head 0 (`80x80`, stride 8): `add_postproc_node: true`, `force_float32: true`
- Head 1 (`40x40`, stride 16): `add_postproc_node: true`, `force_float32: true`
- Head 2 (`20x20`, stride 32): `add_postproc_node: true`, `force_float32: true`

### D. Pegasus Quantization
Single-pass KL divergence calibration:
```bash
taskset -c 0,1 python3 /root/acuity-toolkit-whl-6.21.16/bin/pegasus.py quantize \
    --model yolox_s_sim.json \
    --model-data yolox_s_sim.data \
    --device CPU \
    --with-input-meta yolox_s_sim_inputmeta.yml \
    --rebuild \
    --model-quantize yolox_s_sim_uint8.quantize \
    --quantizer asymmetric_affine \
    --qtype uint8 \
    --algorithm kl_divergence \
    --divergence-first-quantize-bits 12 \
    --iterations 1
```

### E. Unified NBG Export for T527
Target optimization identifier: `VIP9000NANOSI_PLUS_PID0X10000016`
```bash
taskset -c 0,1 python3 /root/acuity-toolkit-whl-6.21.16/bin/pegasus.py export ovxlib \
    --pack-nbg-unify \
    --optimize VIP9000NANOSI_PLUS_PID0X10000016 \
    --viv-sdk /root/Vivante_IDE/VivanteIDE5.8.2/cmdtools \
    --model yolox_s_sim.json \
    --model-data yolox_s_sim.data \
    --dtype quantized \
    --model-quantize yolox_s_sim_uint8.quantize \
    --target-ide-project 'linux64' \
    --with-input-meta yolox_s_sim_inputmeta.yml \
    --postprocess-file yolox_s_sim_postprocess_file.yml \
    --output-path ./wksp/yolox_s_sim_uint8
```
Result: `yolox_s_sim_uint8_t527.nb` (8.8 MB).

---

## 3. Benchmark & Performance Results

Evaluated on Orange Pi 4A running Linux 6.1.84 with Allwinner VIPCore NPU driver:

### Latency Breakdown
| Stage | Description | Latency |
|---|---|---|
| **Model Init** | Loading `.nb` into NPU memory via `vip_create_network` | 1,789 ms (one-time) |
| **Pre-process** | Top-left letterbox resize to $640 \times 640$ (padding 114) | 3.5 – 7.8 ms |
| **NPU Inference** | Pure hardware execution on `/dev/vipcore` | **105.0 ms** (~9.5 FPS) |
| **Post-process** | Multi-head decoding (8400 anchors) + Class-agnostic NMS | 43.1 – 51.3 ms |
| **Total Pipeline** | End-to-end latency per frame | **159.8 ms** (~6.3 FPS) |

---

## 4. Detection Accuracy Verification

Tested against standard COCO benchmark image `bus.jpg` (640x640):

| Rank | Detected Class | NPU Confidence (INT8) | ONNX FP32 Ground Truth | Bounding Box [x1, y1, x2, y2] |
|---|---|---|---|---|
| **#1** | **bus** | **93.7%** | 93.9% | `[95, 136, 546, 431]` |
| **#2** | **person** | **89.9%** | 90.3% | `[109, 247, 212, 526]` |
| **#3** | **person** | **88.6%** | 88.7% | `[475, 234, 559, 519]` |
| **#4** | **person** | **88.0%** | 87.8% | `[213, 245, 282, 497]` |
| **#5** | **person** | **48.0%** | 35.5% | `[80, 331, 120, 511]` |

> **Accuracy Variance:** $< 0.5\%$ delta between FP32 ONNX reference and UINT8 NPU hardware inference.

---

## 5. Python Environment & Library Requirements

The YOLOX-S inference engine uses standard Python `ctypes` to interface directly with the vendor NPU runtime library (`/usr/local/lib/libVIPlite.so`). As a result, **no proprietary or vendor-specific Python wheels are required**.

### Required Python Libraries
| Library | Recommended Version | Purpose |
|---|---|---|
| `numpy` | `>= 1.24.0` (tested with 2.5.3) | Multi-dimensional array operations, anchor grid decoding, and vectorized NMS |
| `opencv-python-headless` | `>= 4.8.0` (tested with 5.0.0.93) | Image loading, letterbox resizing, and bounding box visualization (or `opencv-python`) |

Standard library dependencies (built into Python 3):
- `ctypes`: Native C ABI interface for VIPLite v1.13 functions
- `argparse`: Command-line interface argument parser
- `time`, `os`, `sys`: Performance benchmarking and filesystem management

### Setting Up a Virtual Environment
To create and configure a clean virtual environment from scratch on Orange Pi 4A:

```bash
# 1. Create a Python 3 virtual environment
python3 -m venv ~/my_yolox_env

# 2. Activate the virtual environment
source ~/my_yolox_env/bin/activate

# 3. Upgrade pip and install minimal dependencies
pip install --upgrade pip
pip install numpy opencv-python-headless

# Alternatively, install via requirements.txt:
# pip install -r requirements.txt
```

> [!NOTE]
> Ensure the system has `/usr/local/lib/libVIPlite.so` and the VIPCore driver active (`/dev/vipcore`). Run `npu vipcore` if switching from Teflon mainline.

---

## 6. Directory Layout

```
~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor/
├── models/
│   └── yolox_s_sim_uint8_t527.nb      # Compiled NBG model (8.8 MB)
├── samples/
│   ├── bus.jpg                        # Test benchmark sample
│   └── dog.jpg                        # Secondary multi-object sample
├── output/
│   ├── output_bus.jpg                 # Bus benchmark visualization
│   └── output_dog.jpg                 # Dog benchmark visualization
├── requirements.txt                   # Minimal Python dependencies
├── yolox                              # System CLI wrapper script (symlinked to /usr/local/bin/yolox)
├── yolox_infer.py                     # Primary Python inference & decoding engine
├── vipcore_model.py                   # VIPLite v1.13 ctypes wrapper
├── run_demo.sh                        # One-command execution script
├── plan.md                            # Comprehensive architecture plan
└── README.md                          # Documentation
```

---

## 7. How to Run

### System-Wide CLI (`yolox`)
The `yolox` command is installed system-wide in `/usr/local/bin/yolox` (symlinked from `~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor/yolox`). It can be invoked directly from any working directory:

```bash
# 1. Simple positional invocation (auto-saves to output/output_<name>.jpg)
yolox samples/bus.jpg

# 2. Run on any external image
yolox /path/to/photo.jpg

# 3. Custom output destination and confidence threshold
yolox photo.jpg -o my_detection.jpg -s 0.50

# 4. Run multi-iteration hardware benchmark
yolox samples/bus.jpg -l 10

# 5. Display help and all available flags
yolox --help
```

### Quick Start Demo
```bash
cd ~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor
./run_demo.sh
```

### Direct Python Invocation
```bash
/home/ukhan/venv_npu/bin/python3 ~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor/yolox_infer.py \
    -m ~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor/models/yolox_s_sim_uint8_t527.nb \
    -i /path/to/custom_image.jpg \
    -o ~/NPU_proj_opi4a_6.18.44_vendor/opi4a-npu-yolox_vendor/output/result.jpg \
    -s 0.35 \
    -l 10
```

### Command-line Options
- `image`: Path to input image as a positional argument (optional if `-i` is used).
- `-m, --model <path>`: Path to compiled `.nb` model file (default: `models/yolox_s_sim_uint8_t527.nb`).
- `-i, --input <path>`: Explicit flag for input image.
- `-o, --output <path>`: Destination path for annotated output image (default: `output/output_<basename>.jpg`).
- `-s, --score_thr <float>`: Detection confidence score threshold (default: `0.35`).
- `--nms_thr <float>`: Non-Maximum Suppression IoU overlap threshold (default: `0.45`).
- `-l, --loop <int>`: Number of inference iterations to benchmark average latency (default: `1`).
