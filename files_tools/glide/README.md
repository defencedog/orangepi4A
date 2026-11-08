# Glide Media Player (0.60+VPU) for Orange Pi 4A (ARM64)

**Target Architecture:** `arm64` / `aarch64` (Orange Pi 4A, Allwinner T527, Ubuntu 24.04 / 26.04)  
**Upstream Project:** [philn/glide](https://github.com/philn/glide) (Version 0.6.9, commit `d6ed2e8`)  
**Package Artifact:** `glide_0.6.9_arm64.deb` (2.20 MB)  
**Technology Stack:** Rust + GTK4 + libadwaita + GStreamer (`playbin3`) + Cedar VPU  

---

## 1. Overview

**Glide** is a modern, lightweight, high-performance media player written in Rust utilizing GTK4 and GStreamer. 

This build is specifically optimized and packaged for the **Orange Pi 4A (Allwinner T527)**:
- **Cedar VPU Hardware Decoding:** Decodes **H.264**, **HEVC / H.265**, and **VP9** (Profile 0) directly on the Allwinner Cedar hardware video engine (`/dev/cedar_dev`), achieving smooth playback with minimal CPU load.
- **Embedded GTK4 Sink:** Statically links the `gtk4paintablesink` element directly into the binary, eliminating the need to install external GStreamer GTK4 plugins.
- **Decoder Ranking Override:** Seamlessly merges cedar decoder ranks (`omxh264dec`, `omxhevcvideodec`, `omxvp9videodec` @ rank 257) ahead of software decoders.

---

## 2. Directory Contents

| Item | Description |
| :--- | :--- |
| **[`glide_0.6.9_arm64.deb`](./glide_0.6.9_arm64.deb)** | Prebuilt binary package containing `/usr/bin/glide`, desktop menu launcher, and icons. |
| **[`GLIDE-VPU.md`](./GLIDE-VPU.md)** | Comprehensive technical guide covering VPU ranking, cross-compilation environment, and codec validation. |
| **[`glide_bug/`](./glide_bug/)** | Self-contained bug report and patch resolving the Wayland window-sizing issue: |
| ├── `0001-window-keep-screen-relative-and-centred.patch` | Git patch fixing window dimensions and positioning under Wayland. |
| ├── `issue-window-sizing.md` | Upstream-ready issue description. |
| └── `README.md` | Submission guide and technical context for the bug fix. |

---

## 3. Resolved Bug: Wayland Window Sizing & Centring (`glide_bug/`)

In upstream Glide 0.6.9, windowed playback called `set_size_request(video_w, video_h)` on every dimension change. On single-board computers running a 1280×720 or 1080p desktop session under Wayland (such as KDE Plasma Wayland on the Orange Pi 4A):
- The window expanded to the video's full native dimensions (e.g. 1080p or 4K), pushing controls and half the video off-screen.
- Wayland security architecture prevents client applications from arbitrarily repositioning their top-level windows.

### The Fix Applied in this Release
1. **Screen-Relative Geometry:** `UIContext::new` automatically bounds the window to 90% of the active monitor's dimensions (minimum 640×360), allowing the Wayland compositor to centre the initial window placement.
2. **Aspect Ratio Preservation (`contain`):** Video rendering uses `hexpand`/`vexpand` with `content-fit = contain`. The video is cleanly letterboxed or pillarboxed inside the fixed-size window without overflowing the screen.
3. **Fullscreen Toggle:** Pressing `F` smoothly toggles native fullscreen playback.

The full patch and upstream submission report are preserved in [`glide_bug/`](./glide_bug/).

---

## 4. Real-Time VPU Telemetry in `opi-mon`

When playing H.264 or HEVC/H.265 videos in Glide, hardware decoding is actively monitored by the Orange Pi 4A hardware monitor (**`opi-mon`**):

```bash
# Launch telemetry dashboard in another terminal
opi-mon
```

### Telemetry Dashboard During Playback

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

- **`VPU 100%` (cedar):** Indicates the Allwinner Cedar VPU core is active and hardware-accelerating video decoding.
- **`GPU 100%` (Mali-G57):** Reflects Wayland GTK4 paintable surface compositing.
- **Hardware Interrupts:** Hardware completion events can be verified in `/proc/interrupts` under `IRQ 488 (cedar_dev)`.

---

## 5. Installation

Install the `.deb` package using `apt` (which automatically resolves standard desktop dependencies):

```bash
sudo apt update
sudo apt install -y ./glide_0.6.9_arm64.deb
```

### Runtime Dependencies
- `libgtk-4-1` (≥ 4.14)
- `libadwaita-1-0` (≥ 1.5)
- `libgstreamer1.0-0` (≥ 1.24)
- `libgstplay-1.0-0` (`gstreamer1.0-plugins-bad`)
- `libgstgl-1.0-0` (`gstreamer1.0-gl`)

---

## 6. Usage & Video Verification

### Launching Glide

- **From Desktop Application Menu:** Search for **Glide** under Multimedia.
- **From Command Line:**
  ```bash
  glide path/to/video.mp4
  ```

### Verifying with Sample Videos (`~/Videos`)

Sample test clips (HEVC Main, 30 fps) are available on the device in `~/Videos/`:

```bash
# 720p HEVC Hardware Playback
glide ~/Videos/hevc-bigbuckbunny-720p.mp4

# 1080p HEVC Hardware Playback
glide ~/Videos/hevc-bigbuckbunny-1080p.mp4

# 1080p H.264 Playback
glide ~/Videos/test.mp4
```

During playback, you will observe `cedarc <VeInitialize>` in the terminal logs and real-time activity on the `VPU` row in `opi-mon`.
