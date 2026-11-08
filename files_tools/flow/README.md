# Flow-Desktop (0.1.0-beta3) — VPU Clapper Integration for Orange Pi 4A

**Target Board:** Orange Pi 4A (Allwinner T527 / `sun55iw3`, `aarch64`)  
**Package Artifact:** `Flow_0.1.0-beta3_arm64.deb` (18.68 MB)  
**Upstream:** [Flow-Desktop](https://github.com/aedev/flow) (Tauri 2 + React)  
**Media Backend:** Clapper Media Player via GStreamer (`gst-omx` / `/dev/cedar_dev`)  

---

## 1. Overview

**Flow-Desktop** is a privacy-first desktop client for YouTube. 

On single-board computers like the Orange Pi 4A, WebKitGTK's internal media pipeline cannot properly drive the Allwinner OpenMAX (`gst-omx`) video decoding pipeline, resulting in web process crashes (`web_process_terminated window=main reason=Crashed`). 

This customized build integrates **Clapper** (which is readily available in Ubuntu repos) as the dedicated video playback engine. When clicking a video, Flow launches Clapper to decode the stream on the Allwinner **Cedar VPU** (`/dev/cedar_dev`), achieving smooth 720p/1080p playback without overloading the CPU.

---

## 2. Directory Contents

| Item | Description |
| :--- | :--- |
| **[`Flow_0.1.0-beta3_arm64.deb`](./Flow_0.1.0-beta3_arm64.deb)** | Prebuilt binary package for ARM64 with Clapper external-player integration enabled. |
| **[`FLOW-VPU-CLAPPER-INTEGRATION.md`](./FLOW-VPU-CLAPPER-INTEGRATION.md)** | Technical specification of the Rust Tauri commands, React settings schema, and IPC wiring. |
| **[`patch-flow-clapper.py`](./patch-flow-clapper.py)** | Idempotent Python patching script that modifies the Flow-Desktop source tree to hook into Clapper. |
| **[`patch-flow-vpu.py`](./patch-flow-vpu.py)** | Helper script for VPU rank configuration. |
| **[`flow-vpu-test.sh`](./flow-vpu-test.sh)** | Automated test runner that seeds onboarding, starts the background bridge, and verifies VPU playback. |

---

## 3. Configuring Clapper for Hardware VPU Acceleration

Clapper handles video playback for Flow. To ensure Clapper prioritizes the Allwinner Cedar hardware decoders:

1. **Install Clapper and Enhancers (if not already installed):**
   ```bash
   sudo apt update
   sudo apt install -y clapper clapper-enhancers gir1.2-clapper-0.0
   ```

2. **Enable OMX Decoders in Clapper:**
   - Launch **Clapper** from your application menu or terminal (`clapper`).
   - Open **Preferences** (`Ctrl+,` or menu icon).
   - Navigate to: **Tweaks > Plugin Ranking**.
   - Scroll down to the **`omx`** section (`omxh264dec`, `omxhevcvideodec`, `omxvp9videodec`, `omxmpeg4videodec`).
   - Enable all OMX plugins (they will show a rank of `257`, prioritizing them over software decoders).
   - Restart Clapper.

---

## 4. Real-Time VPU Telemetry in `opi-mon`

When a video is playing in Clapper via Flow, hardware acceleration can be directly verified using **`opi-mon`**:

```bash
opi-mon
```

```text
 Orange Pi 4A (T527)
 01:24:21 · Up: 2d 1h · Load: 2.53
─────────────────────────────────────
 CPU  31% [███░░░░░░░] 33.8°C  1.34GHz
 NPU OFF  [░░░░░░░░░░] 31.9°C  OFFLINE
 GPU 100% [██████████] 31.9°C   696MHz
 VPU 100% [██████████]     0/s  cedar
 G2D   0% [░░░░░░░░░░]     0/s  sunxi
 RAM  77% [███████░░░] 2.9/3.7G  845M free
 SWP  90% [█████████░] 1.8/1.9G
─────────────────────────────────────
 [Ctrl+C] Exit  ·  Refresh: 1s
```

- **`VPU 100% [██████████] cedar`**: Verifies that the Allwinner Cedar core (`/dev/cedar_dev`) is actively decoding the stream.
- **`cedar_dev` Interrupts**: Can also be verified with `grep cedar /proc/interrupts` (`IRQ 488`).

---

## 5. Installation & Usage

### Install Package

```bash
sudo dpkg -i Flow_0.1.0-beta3_arm64.deb
```

### Launching Flow

Launch **Flow** from your application menu or command line:
```bash
flow-desktop
```

### Player Settings
Inside Flow:
- Navigate to **Settings > Player**.
- Verify that **"Play videos in Clapper (VPU)"** is toggled ON.
- Clicking any video will automatically spawn Clapper with hardware VPU decoding.
