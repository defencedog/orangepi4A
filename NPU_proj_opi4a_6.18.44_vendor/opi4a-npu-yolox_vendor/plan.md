# Implementation Plan: YOLOX Object Detection Deployment on Orange Pi 4A (Allwinner T527 NPU)

## 1. Overview & Architecture

The objective of this project is to deploy hardware-accelerated **YOLOX-S** object detection on the **Orange Pi 4A** (Allwinner T527 Octa-core Cortex-A55 with Vivante VIP9000 Nano-DI / Pico NPU) using the vendor **VIPCore** driver (`/dev/vipcore`) and **VIPLite v1.13** runtime.

```
+---------------------------------------------------------------------------------------------------+
| 1. Model Compilation (Proxmox Server: 192.168.1.15)                                              |
|    Container: allwinner_v1.8.11 (ubuntu-npu:v1.8.11)                                              |
|                                                                                                   |
|  [yolox_s_sim.onnx] ---> [pegasus import] ---> [.json / .data]                                   |
|                                                      |                                            |
|  [Calibration Images] ---> [pegasus quantize (uint8, KL-div, 12-bit)] ---> [.quantize]            |
|                                                                                  |                |
|  [T527 Target: VIP9000PICO_PID0X9D] ---> [pegasus export ovxlib --pack-nbg-unify]                |
|                                                      |                                            |
|                                                      v                                            |
|                                      [yolox_s_sim_uint8_t527.nb] (~9.1 MB)                        |
+---------------------------------------------------------------------------------------------------+
                                                      |
                                     (SCP via opi3b staging host)
                                                      v
+---------------------------------------------------------------------------------------------------+
| 2. Target Execution (Orange Pi 4A: 192.168.1.17)                                                  |
|    Working Directory: ~/opi4a-npu-yolox_vendor/                                                   |
|                                                                                                   |
|    +-------------------------+      +---------------------------+      +-----------------------+ |
|    |      Pre-process        |      |      NPU Execution        |      |     Post-process      | |
|    | - Input image (BGR)     | ---> | - /dev/vipcore            | ---> | - 3 Multi-scale Heads | |
|    | - Letterbox to 640x640  |      | - /usr/local/lib/         |      |   (Strides: 8, 16, 32)| |
|    | - RGB conversion        |      |   libVIPlite.so           |      | - Vectorized Decoding | |
|    | - Normalization (1/255) |      | - ~73 ms latency (~14 FPS)|      | - Multiclass NMS      | |
|    +-------------------------+      +---------------------------+      | - COCO 80 BBoxes      | |
|                                                                        +-----------------------+ |
|                                                                                    |              |
|                                                                                    v              |
|                                                                        [Annotated Output Image]   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Assessment of Staged Artifacts & Dependencies

### Staged Files:
1. `yolox_s_sim.onnx` (35 MB):
   - **Verified Graph Topology**:
     - Input node: `images` of shape `[1, 3, 640, 640]`, float32.
     - Output nodes:
       - Node `798`: Stride 8 head (`[1, 85, 80, 80]`, 6,400 anchor positions).
       - Node `824`: Stride 16 head (`[1, 85, 40, 40]`, 1,600 anchor positions).
       - Node `850`: Stride 32 head (`[1, 85, 20, 20]`, 400 anchor positions).
       - Total anchor points: $6400 + 1600 + 400 = 8400$.
     - Channel dimension (85): 4 bounding box regression coordinates ($tx, ty, tw, th$) + 1 objectness score ($obj\_conf$) + 80 COCO classification scores ($cls\_conf$).
   - This model has already been pruned and decoupled from post-processing operators, making it directly compilable by Acuity Pegasus without needing `sub_model.py`.

2. `gcc-arm-10.2-2020.11-x86_64-aarch64-none-linux-gnu.tar.xz` (113 MB):
   - **Requirement Status: NOT REQUIRED.**
   - **Technical Rationale**:
     1. The model conversion toolchain (`pegasus`) runs entirely inside the x86_64 Docker container on Proxmox, using the Vivante internal shader/graph compiler to directly produce the `.nb` (Network Binary Graph).
     2. Our primary deployment runner on Orange Pi 4A is Python-based (`yolox_infer.py`) using `ctypes` bindings directly to `/usr/local/lib/libVIPlite.so`, providing superior flexibility and zero binary compilation friction.
     3. If native C++ binaries (`yolox_demo_t527`) are desired, the Orange Pi 4A already possesses native `gcc` (v14/v13), `cmake`, and `opencv` development headers directly on the board. Native compilation on ARM64 eliminates cross-compilation toolchain glibc mismatch issues.

---

## 3. Step-by-Step Execution Plan

### Phase 1: Model Compilation on Proxmox Server (`192.168.1.15`)
1. **Stage Model & Calibrations**:
   - `yolox_s_sim.onnx` has been copied to `/root/docker/acuity_t527/workspace/` (mounted at `/workspace` inside Docker container `allwinner_v1.8.11`).
   - Create workspace directory: `/workspace/examples/yolox/convert_model`.
2. **Acuity ONNX Import**:
   ```bash
   pegasus import onnx \
       --model yolox_s_sim.onnx \
       --output-model yolox_s_sim.json \
       --output-data yolox_s_sim.data
   ```
3. **Generate Input Metadata Configuration (`yolox_s_sim_inputmeta.yml`)**:
   ```yaml
   input_meta:
     - name: images
       shape: [1, 3, 640, 640]
       format: NCHW
       color_format: RGB
       mean: [0, 0, 0]
       scale: [0.0039215686, 0.0039215686, 0.0039215686]
   ```
4. **Calibration Dataset Preparation**:
   - Assemble representative images (`bus.jpg` and standard COCO validation samples) into `calib_yolox/`.
   - Generate `dataset.txt` pointing to the calibration set.
5. **INT8 Quantization**:
   ```bash
   pegasus quantize \
       --model yolox_s_sim.json \
       --model-data yolox_s_sim.data \
       --with-input-meta yolox_s_sim_inputmeta.yml \
       --quantizer asymmetric_affine \
       --qtype uint8 \
       --algorithm kl_divergence \
       --divergence-first-quantize-bits 12
   ```
6. **NBG Compilation for Allwinner T527**:
   ```bash
   pegasus export ovxlib \
       --model yolox_s_sim.json \
       --model-data yolox_s_sim.data \
       --dtype quantized \
       --model-quantize yolox_s_sim_uint8.quantize \
       --target-ide-project 'linux64' \
       --with-input-meta yolox_s_sim_inputmeta.yml \
       --pack-nbg-unify \
       --optimize "VIP9000PICO_PID0X9D" \
       --viv-sdk /workspace/ai-sdk/sdk/viv_sdk \
       --output-path ./wksp/yolox_s_sim_uint8
   ```
   This generates `yolox_s_sim_uint8_t527.nb`.

---

### Phase 2: Staging & Transfer Pipeline
1. In accordance with network isolation rules (no direct SCP between Proxmox and Orange Pi 4A):
   - Retrieve `yolox_s_sim_uint8_t527.nb` and sample assets (`bus.jpg`) from Proxmox to `opi3b` (`/home/ukhan/gemini/opi4a/`).
   - Transfer from `opi3b` to Orange Pi 4A:
     - Model: `~/opi4a-npu-yolox_vendor/models/yolox_s_sim_uint8_t527.nb`
     - Test Sample: `~/opi4a-npu-yolox_vendor/samples/bus.jpg`

---

### Phase 3: Runtime Deployment on Orange Pi 4A (`192.168.1.17`)
1. **Directory Layout on Orange Pi 4A**:
   ```
   ~/opi4a-npu-yolox_vendor/
   ├── models/
   │   └── yolox_s_sim_uint8_t527.nb
   ├── samples/
   │   └── bus.jpg
   ├── output/
   │   └── output_yolox.jpg
   ├── yolox_infer.py              # Primary Python inference & post-processing engine
   ├── vipcore_model.py            # VIPLite ctypes wrapper (libVIPlite.so)
   ├── coco_classes.py             # 80 standard COCO categories
   ├── run_demo.sh                 # End-to-end execution script
   ├── plan.md                     # This plan
   └── README.md                   # Complete documentation
   ```

2. **Inference Engine Architecture (`yolox_infer.py`)**:
   - **Pre-processing**:
     - Letterbox resizing with aspect-ratio preservation and padding to $640 \times 640$.
     - Color conversion (BGR -> RGB).
     - Scale conversion to uint8 tensor adhering to input quantization parameters.
   - **Hardware Execution**:
     - Memory allocation through `vsi_nn_CreateTensor` / `vsi_nn_CopyDataToTensor`.
     - Direct hardware inference invocation via `vipcore` device driver.
   - **Post-processing & Decoding**:
     - Vectorized grid coordinate transformation:
       $$x_c = (x_{\text{reg}} + \text{grid}_x) \times \text{stride}$$
       $$y_c = (y_{\text{reg}} + \text{grid}_y) \times \text{stride}$$
       $$w = \exp(w_{\text{reg}}) \times \text{stride}$$
       $$h = \exp(h_{\text{reg}}) \times \text{stride}$$
     - Confidence calculation: $Score = \text{Objectness} \times \text{ClassScore}$.
     - Multiclass NMS filtering ($IoU \ge 0.45$, Confidence $\ge 0.25$).
     - Invert letterbox scaling back to original image coordinates.
     - Visualization: Render colored bounding boxes and labels; output to `output/output_yolox.jpg`.

3. **Optional Native C++ Demo Build**:
   - If desired, the C++ source files (`main.cpp`, `yolox_preprocess.cpp`, `yolox_postprocess.cpp`) will be compiled natively on Orange Pi 4A:
     ```bash
     g++ -O3 -std=c++14 main.cpp yolox_preprocess.cpp yolox_postprocess.cpp \
         -I/usr/local/include/vpm -L/usr/local/lib -lVIPlite -lVIPuser `pkg-config --cflags --libs opencv4` \
         -o yolox_demo_t527
     ```

---

## 4. Verification & Acceptance Criteria

### Test Case 1: Reference Detection Verification (`bus.jpg`)
Using the reference `bus.jpg` (640x640), the model must detect:
- 1 Bus: Expected confidence $\approx 93\%$, bounding box $\approx [98, 137, 550, 435]$
- 4 Persons: Expected confidences $\approx 89\%, 89\%, 87\%, 58\%$

### Test Case 2: Latency & Performance Benchmark
- Execution latency measured on hardware NPU:
  - Expected pure model runtime: **~73.6 ms** (as documented in Radxa official benchmarks for T527 VIPLite v1.13).
  - Effective throughput: **~13 to 14 FPS**.
- Output artifact verified at `~/opi4a-npu-yolox_vendor/output/output_yolox.jpg`.

---

## 5. Requirements & Preconditions

### Anything Else Needed From the User?
**Nothing further is required from the user.**
- All required credentials (Proxmox SSH, Orange Pi 4A SSH `ukhan:asad`) are already configured.
- The base ONNX model (`yolox_s_sim.onnx`) is already staged.
- The VIPCore driver is currently active on Orange Pi 4A (`/dev/vipcore` mode verified).
- The Proxmox Acuity Docker container (`allwinner_v1.8.11`) is up and running.

Once confirmed, execution will begin immediately.
