# Orange Pi 4A (Allwinner T527) VIPCore Vendor NPU Applications Suite

**Author:** Usama Khan ([cv.ukhan.org](https://cv.ukhan.org))  
**Target Hardware:** Orange Pi 4A / Radxa Cubie A5E (Allwinner T527 SoC, Octa-Core Cortex-A55 @ 1.8 GHz)  
**NPU Subsystem:** VeriSilicon VIP9000 Nano-DI (2.0 TOPS INT8)  
**Driver & Runtime:** Vendor `sunxi-npu` (`/dev/vipcore`) + VeriSilicon VIPLite v1.13 (`/usr/local/lib/libVIPlite.so`)  
**Tested Python Runtime:** **Python 3.14.4** / 3.12 (ARM64 / aarch64, Linux `6.18.44-g61025ec85b88` / Ubuntu 24.04/26.04)  
**Tested on:** [aurealnix-opi4a-ubuntu2604-kubuntu-v0.4.1.img.xz](https://github.com/ut-slayer/orangepi-4a-mainline/releases/tag/v0.4.1)

---

## 1. Overview

This repository hosts high-performance, industrial-grade deep learning applications utilizing the official **Allwinner / VeriSilicon VIPCore** vendor driver (`/dev/vipcore`) and **VIPLite v1.13** runtime on the **Orange Pi 4A** (Allwinner T527).

While the mainline `etnaviv` + Teflon stack operates under the standard DRM graphics subsystem, the **VIPCore vendor stack** exposes the dedicated VeriSilicon hardware graph execution engine. This unlocks:
- Arbitrary multi-scale, multi-head network binary graphs (`.nb`).
- Embedded hardware input preprocessing (on-the-fly color space conversion, channel swapping, scaling, and zero-point subtraction via NPU DMA).
- High-resolution vision pipelines up to $2048 \times 2048$ with zero-copy memory mapping.
- Native Python `ctypes` bindings without any proprietary Python wheel dependency.

---

## 2. Projects Included

| Directory | Application / Domain | Model Architecture | Hardware Subsystem | Primary Performance Metric | CLI Executable |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [`opi4a-npu-ocr_vendor_picodet/`](./opi4a-npu-ocr_vendor_picodet/) | **Two-Stage Layout-Guided Document OCR** | PicoDet-Layout + PP-OCRv6 DBNet ($1600 \times 1600$ & $2048 \times 2048$) + English PP-OCRv4 CTC Dynamic Recognizer | VIP9000 NPU (`/dev/vipcore`) + 8x ARM Cortex-A55 (MNN Neon FP16) | **575 ms** layout analysis, **2.07 s** text line detection, flawless multi-column reading order, zero CJK hallucination | `npu-ocr-pdf` |
| [`opi4a-npu-yolox_vendor/`](./opi4a-npu-yolox_vendor/) | **YOLOX-S Real-Time Object Detection** | YOLOX-S ($640 \times 640$, 3 multi-scale decoupled heads, 8400 anchors) | VIP9000 NPU (`/dev/vipcore`) | **105.0 ms** hardware NPU latency (**~9.6 FPS** sustained), 5 detections on `bus.jpg` (< 0.5% delta vs FP32 ONNX) | `yolox` |

---

## 3. System Prerequisites & VIPCore NPU Activation

Before running any applications in this suite, ensure the VIPCore kernel driver is active:

```bash
# Check current NPU driver status
npu status

# If currently in mainline Teflon mode, switch to VIPCore vendor mode:
sudo npu vipcore
# (or: sudo npu-switch vipcore)
```

Confirm that the device node exists and has read/write permissions:
```bash
ls -l /dev/vipcore
# crw-rw-rw- 1 root root ... /dev/vipcore
```

And verify the VIPLite library is present:
```bash
ls -l /usr/local/lib/libVIPlite.so
```

---

## 4. Python Environment & Dependencies

Both projects utilize standard Python libraries and connect to `/usr/local/lib/libVIPlite.so` via `ctypes`. No proprietary vendor wheels are needed.

### Setting Up the Virtual Environment

```bash
# 1. Install system dependency for PDF rasterization (required for OCR)
sudo apt update && sudo apt install -y poppler-utils

# 2. Create and activate a Python 3 virtual environment
python3 -m venv ~/venv_npu
source ~/venv_npu/bin/activate

# 3. Install dependencies for all vendor projects
pip install --upgrade pip
pip install numpy opencv-python-headless MNN shapely pyclipper pillow six
```

---

## 5. System-Wide CLI Executables

Both applications are configured with system-wide CLI wrappers installed to `/usr/local/bin`:

### A. Document OCR (`npu-ocr-pdf`)
```bash
# Process a PDF document (balanced 1600x1600 two-stage layout + text detection)
npu-ocr-pdf samples/sample-compressor.pdf

# High-throughput single-column memos/letters (bypasses layout stage for ~10.8s/page)
npu-ocr-pdf samples/PublicWaterMassMailing.pdf --no-layout

# Advanced layout-guided run with Markdown, JSON, and visual overlays
npu-ocr-pdf document.pdf --dpi 200 --vis --md --json
```

### B. Object Detection (`yolox`)
```bash
# Simple positional invocation on any image
yolox samples/bus.jpg

# Custom output destination and score threshold
yolox /path/to/photo.jpg -o detected.jpg -s 0.50

# Benchmark 10 loops for average hardware latency
yolox samples/bus.jpg -l 10
```
