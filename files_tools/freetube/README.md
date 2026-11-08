# FreeTube (0.26.0) — VPU Clapper Integration for Orange Pi 4A

**Target Board:** Orange Pi 4A (Allwinner T527 / `sun55iw3`, `aarch64`)  
**Package Artifact:** `freetube_0.26.0_beta_arm64.deb` (92.17 MB)  
**Upstream:** [FreeTubeApp/FreeTube](https://github.com/FreeTubeApp/FreeTube) (v0.26.0 Beta, Electron 44)  
**Media Backend:** Clapper Media Player via GStreamer (`gst-omx` / `/dev/cedar_dev`)  

---

## 1. Overview

**FreeTube** is an open-source, privacy-focused YouTube client built with Electron.

On Linux ARM64, Chromium/Electron does not provide native hardware video acceleration for the Allwinner Cedar VPU. Playing 720p/1080p video inside the default Electron web player consumes 100%+ CPU across multiple Cortex-A55 cores, resulting in frame drops and elevated SoC temperatures.

By delegating video playback to **Clapper** (which is readily available in Ubuntu repos), video decoding is offloaded to the Allwinner **Cedar VPU** (`/dev/cedar_dev`), achieving smooth playback with minimal CPU usage.

---

## 2. Directory Contents

| Item | Description |
| :--- | :--- |
| **[`freetube_0.26.0_beta_arm64.deb`](./freetube_0.26.0_beta_arm64.deb)** | Prebuilt FreeTube 0.26.0 package for ARM64 (`aarch64`). |
| **[`freetube-patch.md`](./freetube-patch.md)** | Full technical documentation on stream selection, yt-dlp overrides, and VPU integration. |
| **[`clapper_yt_dlp_dash.py`](./clapper_yt_dlp_dash.py)** | Patched Clapper DASH enhancer restricting stream selection to a single H.264 720p representation (preventing decoder renegotiation crashes). |
| **[`clapper_yt_dlp_overrides.py`](./clapper_yt_dlp_overrides.py)** | Clapper yt-dlp override patch compatible with modern yt-dlp format extraction. |

---

## 3. Configuring Clapper for Hardware VPU Acceleration

Clapper handles the video stream spawned from FreeTube. To enable hardware decoding:

1. **Install Clapper (if needed):**
   ```bash
   sudo apt update
   sudo apt install -y clapper clapper-enhancers gir1.2-clapper-0.0
   ```

2. **Enable OMX Decoders in Clapper Preferences:**
   - Launch **Clapper** (`clapper`).
   - Open **Preferences** (`Ctrl+,`) and navigate to: **Tweaks > Plugin Ranking**.
   - Scroll to the **`omx`** category (`omxh264dec`, `omxhevcvideodec`, `omxvp9videodec`, etc.).
   - Enable all OMX decoders to set their ranking to `257` (prioritized over software decoders).
   - Restart Clapper.

3. **Install the Single-Representation DASH Enhancers (Recommended):**
   To prevent the Cedar driver from crashing when YouTube streams dynamically switch resolutions mid-stream:
   ```bash
   sudo cp clapper_yt_dlp_dash.py /usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp_dash.py
   sudo cp clapper_yt_dlp_overrides.py /usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp_overrides.py
   ```

---

## 4. Real-Time VPU Telemetry in `opi-mon`

When clicking a video in FreeTube, Clapper launches and activates the Allwinner Cedar VPU core. This can be monitored live in **`opi-mon`**:

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

- **`VPU 100% [██████████] cedar`**: Verifies that `/dev/cedar_dev` is actively decoding video frames.

---

## 5. Installation & Configuration

### Step 1: Install FreeTube `.deb`

```bash
sudo dpkg -i freetube_0.26.0_beta_arm64.deb
```

### Step 2: Configure FreeTube to Default to Clapper

While FreeTube is closed, configure it to open videos directly in Clapper:

```bash
# Add external player configuration to FreeTube settings
mkdir -p ~/.config/FreeTube
echo '{"_id":"defaultViewingMode","value":"external_player"}' >> ~/.config/FreeTube/settings.db
echo '{"_id":"externalPlayer","value":"clapper"}' >> ~/.config/FreeTube/settings.db
```

*(Alternatively, open FreeTube Settings > General / External Player, select **Clapper** as the external player, and set the default viewing mode to **External Player**.)*
