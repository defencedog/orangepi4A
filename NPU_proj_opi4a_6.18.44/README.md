# Orange Pi 4A (Allwinner T527) VIP9000 NPU Applications Suite

**Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))  
**Target Hardware:** Orange Pi 4A / Radxa Cubie A5E (Allwinner T527 SoC, Octa-Core Cortex-A55 @ 1.8 GHz)  
**NPU Subsystem:** VeriSilicon VIP9000nano-di (`vivante,gc` rev 9003, 2.0 TOPS INT8)  
**Driver & Runtime:** Mainline Linux `etnaviv` DRM (`/dev/dri/renderD129`) + Mesa Teflon (`libteflon.so`) + Google LiteRT  
**Tested Python Runtime:** **Python 3.14.4** (ARM64 / aarch64, Linux `6.18.44-g61025ec85b88`)  
**Tested on:** [aurealnix-opi4a-ubuntu2604-kubuntu-v0.4.1.img.xz](https://github.com/ut-slayer/orangepi-4a-mainline/releases/tag/v0.4.1)

---

## 1. Overview

This repository provides production-ready, hardware-verified edge AI applications designed to run on the **VeriSilicon VIP9000 NPU** of the **Allwinner T527** Single Board Computer (Orange Pi 4A).

Unlike stock upstream configurations that suffered from DMA command stalls and runtime PM autosuspend failures, these projects utilize the stabilized, open-source **Etnaviv DRM + Mesa Teflon** pathway to achieve rock-solid silicon acceleration with zero hangs and full power autosuspend support.

---

## 2. Projects Included

| Directory | Application / Domain | Model Architecture | Hardware Acceleration | Primary Performance Metric |
| :--- | :--- | :--- | :--- | :--- |
| [`opi4a-npu-iapws/`](./opi4a-npu-iapws/) | **Thermodynamic Steam Tables (IAPWS-97)** | Quantized Fully-Connected Neural Surrogate (INT8) | LiteRT CPU XNNPACK & VIP9000 Silicon NPU | **0.0277 ms** latency (**58.5x faster** than analytical CPU, < 0.5% error) |
| [`opi4a-npu-mobilenet/`](./opi4a-npu-mobilenet/) | **Vision AI (Classification & Detection)** | MobileNet V1 ($224 \times 224$) & SSD MobileNet ($300 \times 300$) INT8 | LiteRT CPU XNNPACK & VIP9000 Silicon NPU | **52.9 FPS** classification, **36.7 FPS** detection, rock-solid NPU telemetry |
| [`opi4a-npu-face-clustering/`](./opi4a-npu-face-clustering/) | **Facial Intelligence & Identity Indexing** | SCRFD-500M Face Detection & MobileFaceNet (512-D) Embeddings | ONNX Runtime CPU + VIP9000 Silicon NPU + SQLite | **16 faces / 15 unique identities** indexed across scenes, 100% persistent SQLite database |

---

## 3. System Prerequisites & NPU Driver Stack

Before running NPU hardware acceleration, ensure the NPU kernel module and Mesa Teflon delegate are installed on your board (available via the companion repository `NPU_modules_opi4a_6.18.44`):

1. **Kernel Driver (`etnaviv.ko`):** Loaded and bound to `7122000.npu`.
2. **Device Node:** `/dev/dri/renderD129` with read/write access for your user (in `render` group).
3. **Mesa Teflon Delegate:** Deployed at `/usr/local/lib/libteflon.so` (or symlinked at `/usr/lib/teflon/libteflon.so`).

Verify driver readiness with:
```bash
npu status
```

---

## 4. Python Environment & Setup

All projects in this repository were developed and benchmarked on **Python 3.14.4** (compatible with Python 3.10 through 3.14+).

### Quickstart Setup

```bash
# Clone repository
git clone https://github.com/defencedog/orangepi4A.git ~/orangepi4A
cd ~/orangepi4A/NPU_proj_opi4a_6.18.44

# Create and activate a Python virtual environment
python3 -m venv ~/venv_npu
source ~/venv_npu/bin/activate

# Install dependencies for Computer Vision project
pip install -r opi4a-npu-mobilenet/requirements.txt

# Install dependencies for Steam Tables project
pip install -r opi4a-npu-iapws/requirements.txt

# Install dependencies for Face Clustering project
pip install -r opi4a-npu-face-clustering/requirements.txt
```

---

## 5. Directory Layout

```text
~/NPU_proj_opi4a_6.18.44/
├── README.md                      # Master repository documentation (this file)
├── opi4a-npu-face-clustering/     # Face Detection, 512-D Embedding & SQLite Clustering
│   ├── README.md                  # Complete facial intelligence documentation
│   ├── requirements.txt           # Python dependencies (onnxruntime, opencv, litert, numpy)
│   ├── cluster_and_index.py       # Core end-to-end ingestion and clustering CLI
│   ├── face_detector.py           # SCRFD-500M detector with VIP9000 NPU integration
│   ├── face_embedder.py           # MobileFaceNet 512-D facial feature embedder
│   ├── query_db.py                # Database query CLI (search by person, scene, thumbnail)
│   ├── database/                  # Relational SQLite schema (people, images, face_instances)
│   ├── faces.db                   # SQLite database indexed with 15 unique individuals
│   ├── images/                    # Source test image scenes (01.jpg – 05.jpg)
│   ├── crops/                     # 112×112 aligned face crops and thumbnails
│   └── models/                    # SCRFD-500M & MobileFaceNet ONNX + NPU TFLite models
├── opi4a-npu-iapws/               # Sub-millisecond Neural Steam Tables (IAPWS-IF97)
│   ├── README.md                  # Detailed thermodynamics documentation & benchmarks
│   ├── requirements.txt           # Python dependencies (iapws, ai-edge-litert, numpy)
│   ├── steam_calc.py              # Interactive / CLI steam property calculator
│   ├── data/                      # Dataset generator & ground-truth thermodynamic grid
│   ├── models/                    # Trained INT8 surrogate models & norm parameters
│   └── benchmarks/                # Accuracy validation & latency benchmarking suite
└── opi4a-npu-mobilenet/           # Vision AI Suite (Classification & Object Detection)
    ├── README.md                  # Vision suite documentation & telemetry reports
    ├── requirements.txt           # Python dependencies (pillow, opencv, litert, numpy)
    ├── classification.py          # MobileNet V1 ImageNet classification script
    ├── detect_objects.py          # SSD MobileNet V1 COCO object detection script
    ├── benchmark.py               # Multi-thread CPU performance benchmark utility
    ├── run_demo.sh                # Automated one-shot demo script
    ├── run_telemetry_10x.sh       # 10-run NPU hardware telemetry benchmark
    └── models/                    # Quantized INT8 vision models & label files
```

---

## 6. Benchmarking Summary on Orange Pi 4A

| Workload | Execution Engine | Threads / Device | Latency | Throughput | Hardware Status |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **IAPWS-97 Steam Tables** | Exact Analytical CPU | 1 Core | 1.6211 ms | 616.9 evals/sec | Ground truth baseline |
| **IAPWS-97 Steam Tables** | Neural Surrogate (CPU) | 1 Core | **0.0277 ms** | **36,104.7 evals/sec** | **58.5x FASTER** (< 0.5% error) |
| **IAPWS-97 Steam Tables** | Hardware NPU | VIP9000 Silicon | **0.89 ms – 1.17 ms** | ~900 evals/sec | Verified on silicon (`+5,357 ms` stress) |
| **MobileNet V1 (224x224)** | CPU XNNPACK | 8 Cores | **18.91 ms** | **52.9 FPS** | Full octa-core saturation |
| **SSD Detection (300x300)** | CPU XNNPACK | 8 Cores | **27.28 ms** | **36.7 FPS** | Full octa-core saturation |
| **SSD Detection (300x300)** | Hardware NPU | VIP9000 Silicon | Hardware Active | 10/10 Passed | Rock-solid (`+4,900 ms` active delta / run) |
| **Face Detection (SCRFD)** | ONNX Runtime CPU | 8 Cores | **180 ms – 450 ms** | Variable | Fast multi-scale anchor pyramid |
| **Face Embedding (512-D)** | ONNX Runtime CPU | 8 Cores | **~10 ms** | ~100 faces/sec | L2-normalized 512-D feature vector |
| **NPU Silicon Duty Cycle** | VIP9000 Silicon | `/dev/dri/renderD129` | **33.1 ms / pass** | ~30 inferences/sec | 1,244 ms active execution registered |
| **Scene Ingestion & Indexing** | Hybrid CPU + NPU | Full Pipeline | **394 ms – 885 ms** | 1.2–2.5 scenes/sec | Decode, detect, embed, cluster & DB write |

---

## 7. Author & Contact

- **Author:** Usama Khan
- **Personal Website:** [cv.ukhan.org](https://cv.ukhan.org)
- **Target Platform:** Orange Pi 4A (Allwinner T527)
- **License:** MIT / Apache 2.0
