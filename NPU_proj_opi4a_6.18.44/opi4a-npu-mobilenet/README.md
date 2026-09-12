# MobileNet & SSD Vision AI Suite for Orange Pi 4A (Allwinner T527 NPU)

**Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))  
**Target Hardware:** Orange Pi 4A (Allwinner T527 SoC, Octa-Core ARM Cortex-A55 @ 1.8 GHz)  
**NPU Subsystem:** VeriSilicon VIP9000nano-di (`vivante,gc` rev 9003, 6x NN multi-cores, 2x TP cores)  
**DRM & Delegate:** Mainline `etnaviv` (`/dev/dri/renderD129`) + Mesa Teflon (`libteflon.so`)  
**Tested Python Runtime:** **Python 3.14.4** (ARM64 / aarch64, Linux `6.18.44-g61025ec85b88`)  
**Project Path:** `~/NPU_proj_opi4a_6.18.44/opi4a-npu-mobilenet`

---

## 1. Overview & Capabilities

Adapted from the [Radxa Zero 2 Pro NPU Example](https://github.com/zifeng-radxa/zero2pro_NPU_example) and optimized specifically for the **Allwinner T527 VIP9000** architecture, this package provides:
1. **Image Classification**: MobileNet V1 INT8 quantized (`mobilenet_v1_1.0_224_quant.tflite`) covering 1,001 ImageNet categories.
2. **Object Detection with Bounding Boxes**: SSD MobileNet V1 COCO quantized (`detect.tflite`) with bounding box coordinate decoding and annotated image rendering.
3. **Mesa Teflon NPU Delegate**: Built-in patched `libteflon.so` with VIP9000 DMA bugfixes and multi-VIP stall removals.
4. **Benchmarking & Telemetry Suite**: Multi-threaded CPU performance scaling analysis and 10-run NPU hardware telemetry verification.

---

## 2. Python Environment & Pip Dependencies

This project was developed and verified on **Python 3.14.4** (compatible with Python 3.10 through 3.14+).

### 2.1 Pip Dependencies
All required packages are specified in `requirements.txt`:
```text
numpy>=1.26.0
pillow>=10.0.0
ai-edge-litert>=1.0.0
opencv-python-headless>=4.8.0
tqdm>=4.66.0
```

### 2.2 Virtual Environment Setup
```bash
# 1. Create a dedicated virtual environment
python3 -m venv ~/venv_npu

# 2. Activate virtual environment
source ~/venv_npu/bin/activate

# 3. Install dependencies
cd ~/NPU_proj_opi4a_6.18.44/opi4a-npu-mobilenet
pip install -r requirements.txt
```

---

## 3. Directory Layout

```text
~/NPU_proj_opi4a_6.18.44/opi4a-npu-mobilenet/
├── classification.py                    # MobileNet V1 Image Classification script
├── detect_objects.py                    # SSD MobileNet V1 Object Detection with bounding boxes
├── benchmark.py                         # Multi-thread CPU performance benchmark utility
├── run_demo.sh                          # One-shot demo runner script
├── run_telemetry_10x.sh                 # 10-run NPU hardware telemetry benchmark
├── grace_hopper.jpg                     # Standard test image (Admiral Grace Hopper)
├── Bus-Station.png                      # Standard multi-object test image
├── requirements.txt                     # Python package requirements
├── README.md                            # Project documentation
└── models/
    ├── mobilenet_v1_1.0_224_quant.tflite # MobileNet V1 224x224 INT8 model (4.1 MB)
    ├── labels_mobilenet_quant_v1_224.txt # ImageNet 1001 class labels
    ├── detect.tflite                     # SSD MobileNet V1 COCO model (4.2 MB)
    └── labelmap_coco.txt                # COCO 90 class labels
```

---

## 4. Usage & Execution Instructions

> [!NOTE]
> **System NPU Stack Prerequisite:**
> Running on the hardware NPU requires the system-wide NPU stack from the companion repository [`~/NPU_modules_opi4a_6.18.44`](file:///home/ukhan/NPU_modules_opi4a_6.18.44). If not already installed, run:
> ```bash
> cd ~/NPU_modules_opi4a_6.18.44 && sudo ./install.sh
> ```
> This configures the `etnaviv.ko` kernel driver, sets up permissions for `/dev/dri/renderD129`, and installs `/usr/local/lib/libteflon.so`.

Activate your virtual environment before running:
```bash
source ~/venv_npu/bin/activate
cd ~/NPU_proj_opi4a_6.18.44/opi4a-npu-mobilenet
```

### 4.1 One-Shot Demo
Runs both image classification and object detection in sequence:
```bash
./run_demo.sh
```

### 4.2 MobileNet V1 Image Classification
Classifies input image into 1,001 ImageNet categories:
```bash
# Option A: Multi-threaded CPU execution (XNNPACK)
python3 classification.py -i grace_hopper.jpg

# Option B: Hardware NPU execution (automatically uses /usr/local/lib/libteflon.so)
python3 classification.py -i grace_hopper.jpg --npu

# Option C: Hardware NPU execution with custom delegate path
python3 classification.py -i grace_hopper.jpg -e /usr/local/lib/libteflon.so
```

### 4.3 SSD MobileNet V1 Object Detection
Detects objects and draws annotated bounding boxes to an output file:
```bash
# Option A: Multi-threaded CPU execution
python3 detect_objects.py -i Bus-Station.png -o bus_station_detected.jpg

# Option B: Hardware NPU execution (automatically uses /usr/local/lib/libteflon.so)
python3 detect_objects.py -i Bus-Station.png -o bus_station_detected.jpg --npu

# Option C: Hardware NPU execution with custom delegate path
python3 detect_objects.py -i Bus-Station.png -o bus_station_detected.jpg -e /usr/local/lib/libteflon.so
```

### 4.4 Multi-Threaded CPU Scaling Benchmark
Measures latency and throughput scaling across 1, 2, 4, and 8 CPU threads:
```bash
python3 benchmark.py
```

### 4.5 10-Run NPU Telemetry Benchmark
Executes 10 consecutive hardware inference runs on the VIP9000 NPU and validates active power telemetry:
```bash
./run_telemetry_10x.sh
```

---

## 5. Benchmark Results on Orange Pi 4A

### 5.1 Multi-Threaded CPU Scaling (`benchmark.py`)
Tested across 20 iterations per configuration on the 8x Cortex-A55 cores:

| Task | Model Resolution | Threads | Latency (ms) | Throughput (FPS) | Scaling Factor |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Classification** | $224 \times 224$ (INT8) | 1 | 114.34 ms | 8.7 FPS | 1.0x (Baseline) |
| **Classification** | $224 \times 224$ (INT8) | 2 | 57.87 ms | 17.3 FPS | 2.0x |
| **Classification** | $224 \times 224$ (INT8) | 4 | 30.07 ms | 33.3 FPS | 3.8x |
| **Classification** | $224 \times 224$ (INT8) | **8** | **18.91 ms** | **52.9 FPS** | **6.1x** |
| **SSD Detection** | $300 \times 300$ (INT8) | 1 | 154.13 ms | 6.5 FPS | 1.0x (Baseline) |
| **SSD Detection** | $300 \times 300$ (INT8) | 2 | 79.31 ms | 12.6 FPS | 1.9x |
| **SSD Detection** | $300 \times 300$ (INT8) | 4 | 41.93 ms | 23.8 FPS | 3.7x |
| **SSD Detection** | $300 \times 300$ (INT8) | **8** | **27.28 ms** | **36.7 FPS** | **5.6x** |

### 5.2 10-Run NPU Hardware Telemetry Benchmark (`run_telemetry_10x.sh`)
Verified across 10 consecutive hardware inference runs on the VIP9000 NPU:

| Run | Active Time Before (ms) | Active Time After (ms) | Hardware Delta (ms) | Elapsed (ms) | Status | Exit Code |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 13,992,384 | 13,997,295 | +4,911 ms | 7,354 ms | active | rc=0 |
| 2 | 13,997,295 | 14,002,175 | +4,880 ms | 7,244 ms | active | rc=0 |
| 3 | 14,002,175 | 14,007,076 | +4,901 ms | 7,262 ms | active | rc=0 |
| 4 | 14,007,076 | 14,011,987 | +4,911 ms | 7,273 ms | active | rc=0 |
| 5 | 14,011,987 | 14,016,902 | +4,915 ms | 7,302 ms | active | rc=0 |
| 6 | 14,016,902 | 14,021,821 | +4,919 ms | 7,270 ms | active | rc=0 |
| 7 | 14,021,821 | 14,026,752 | +4,931 ms | 7,349 ms | active | rc=0 |
| 8 | 14,026,752 | 14,031,619 | +4,867 ms | 7,244 ms | active | rc=0 |
| 9 | 14,031,619 | 14,036,527 | +4,908 ms | 7,257 ms | active | rc=0 |
| 10 | 14,036,527 | 14,041,390 | +4,863 ms | 7,308 ms | active | rc=0 |

- **Reliability:** 10/10 runs completed with exit code 0 (`rc=0`), zero kernel watchdog hangs (`recover hung GPU!`).
- **Silicon Execution:** Verified by consistent **~4,900 ms** sysfs active time increments per run.
- **Power Management:** Automatically transitions to `suspended` state when idle; `opi-mon` reflects dynamic load accurately.

---

## 6. Author & License

- **Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))
- **Based on:** [Radxa Zero 2 Pro NPU Example](https://github.com/zifeng-radxa/zero2pro_NPU_example)
- **License:** Apache 2.0 / MIT License
