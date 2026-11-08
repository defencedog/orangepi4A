# Glide media player — aarch64 `.deb` built on `prox`, VPU-patched

**Date:** 2026-11-07 · **Upstream:** <https://github.com/philn/glide>
**Version:** 0.6.9 (HEAD `d6ed2e8`) · **Artifact:** `glide_0.6.9_arm64.deb`

---

## 1. Summary

Glide is a Rust + GTK4 + libadwaita + GStreamer media player. It was
cross-compiled on `prox` (x86_64) for `aarch64`, packaged as a `.deb`, and
installed on the OrangePi 4A. It decodes **H.264, HEVC and VP9 on the cedar
VPU** (hardware), with no runtime overrides needed beyond the patch below.

| Item | Value |
| --- | --- |
| `.deb` | `files_tools/glide/glide_0.6.9_arm64.deb` |
| Size | 2 197 638 bytes (2.20 MB) |
| SHA-256 | `2e40d45036f34f3385936690e9535575c92957f7bc7bfd133d859a81dae712a9` |
| Arch | `arm64` |
| Max GLIBC required | 2.39 (board has 2.43) |
| Install | `sudo apt install ./glide_0.6.9_arm64.deb` |

---

## 2. Why it was not a plain `apt`/native build on `prox`

`prox` is **Ubuntu 22.04 (jammy)** and its arm64 repos only have:

- GTK **4.6.9** (Glide needs **≥ 4.14**)
- libadwaita **1.1.7** (needs **≥ 1.5**)

So the jammy multiarch libs are too old. Two options were considered and the
first was used:

1. **Cross-compile against an arm64 Ubuntu 24.04 (noble) sysroot** — fast,
   native x86 codegen.
2. Native build inside an emulated arm64 docker container — reliable but slow.

### Sysroot

An arm64 noble rootfs was created with Docker (+ QEMU binfmt, already enabled
on `prox`) and exported to `/root/sysroots/glide-noble`:

```bash
docker run -d --name glide-arm64 --platform=linux/arm64 ubuntu:24.04 sleep infinity
docker exec glide-arm64 bash -c '
  apt-get update &&
  apt-get install -y --no-install-recommends \
    build-essential pkg-config git curl ca-certificates gettext \
    libgtk-4-dev libadwaita-1-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
    libsqlite3-dev libssl-dev libglib2.0-dev libjson-glib-dev'
docker export glide-arm64 | tar -C /root/sysroots/glide-noble -xf -
```

Sysroot toolchain versions: **GTK 4.14.5, libadwaita 1.5.0, GStreamer 1.24.2**.

### Cross environment — `/root/builds/glide-cross-env.sh`

```bash
SYSROOT=/root/sysroots/glide-noble
export PKG_CONFIG_ALLOW_CROSS=1
export PKG_CONFIG_SYSROOT_DIR="$SYSROOT"
export PKG_CONFIG_LIBDIR="$SYSROOT/usr/lib/aarch64-linux-gnu/pkgconfig:$SYSROOT/usr/share/pkgconfig"
export PKG_CONFIG_PATH=
export CC_aarch64_unknown_linux_gnu=clang
export CXX_aarch64_unknown_linux_gnu=clang++
export AR_aarch64_unknown_linux_gnu=/usr/lib/llvm-18/bin/llvm-ar
export CFLAGS_aarch64_unknown_linux_gnu="--target=aarch64-linux-gnu --sysroot=$SYSROOT"
export CXXFLAGS_aarch64_unknown_linux_gnu="--target=aarch64-linux-gnu --sysroot=$SYSROOT"
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=clang
export RUSTFLAGS="-C link-arg=--target=aarch64-linux-gnu -C link-arg=--sysroot=$SYSROOT -C link-arg=-fuse-ld=lld -C link-arg=-B$SYSROOT/usr/lib/gcc/aarch64-linux-gnu/13"
export PATH="/root/.cargo/bin:/usr/lib/llvm-18/bin:$PATH"
```

> Important: use **rustup's** cargo (`/root/.cargo/bin/cargo`, 1.98) — the
> jammy `/usr/bin/cargo` (1.75) rejects `Cargo.lock` v4.

### Build

```bash
source /root/builds/glide-cross-env.sh
cd /root/builds/glide
cargo build --release --target aarch64-unknown-linux-gnu --features wayland,dmabuf
```

First build 3 m 40 s; incremental (only the `glide` crate) 14 s.
Feature choice: `wayland,dmabuf` (the board is KDE Wayland); `x11egl/x11glx`
were intentionally not enabled, but `build.rs` links `libX11` unconditionally,
so `libx11` must be in the sysroot.

---

## 3. VPU patch (source changes)

The repo is cloned at `prox:/root/builds/glide` and patched in place. The
changes are committed on `main` (`f28c819` cedar ranks, `669354a` window
sizing). The VPU patch touches two files:

### `src/main.rs` — prefer cedar before `gst::init()`

Glide uses `gst_play::Play` (playbin3) with default auto-plugging. Most cedar
OMX decoders already default to `primary+1 (257)`, but the patch explicitly
lists **all 10** and, crucially, **merges with (and overrides)** any inherited
`GST_PLUGIN_FEATURE_RANK`. This is what makes it robust against a hostile
system-wide value (see §4).

Before `gst::init()`:

```rust
// OrangePi 4A: prefer the cedar (gst-omx) hardware decoders over software.
// Merge with any pre-existing GST_PLUGIN_FEATURE_RANK (e.g. /etc/environment)
// so our cedar ranks always win over conflicting entries.
{
    const CEDAR_RANKS: [(&str, &str); 10] = [
        ("omxh264dec", "257"), ("omxhevcvideodec", "257"),
        ("omxvp9videodec", "257"), ("omxvp8videodec", "257"),
        ("omxavsvideodec", "257"), ("omxmpeg4videodec", "257"),
        ("omxmpeg2videodec", "257"), ("omxmpeg1videodec", "257"),
        ("omxh263videodec", "257"), ("omxmjpegvideodec", "257"),
    ];
    let existing = std::env::var("GST_PLUGIN_FEATURE_RANK").unwrap_or_default();
    let mut parts: Vec<String> = CEDAR_RANKS
        .iter()
        .map(|(name, rank)| format!("{}:{}", name, rank))
        .collect();
    parts.extend(
        existing.split(',').filter(|e| !e.is_empty()).filter(|e| {
            let name = e.split(':').next().unwrap_or("");
            !CEDAR_RANKS.iter().any(|(cedar, _)| *cedar == name)
        }).map(|e| e.to_string()),
    );
    std::env::set_var("GST_PLUGIN_FEATURE_RANK", parts.join(","));
}
```

### `data/net.base_art.Glide.desktop` — same rank for menu launches

```
Exec=env GST_PLUGIN_FEATURE_RANK=omxh264dec:257,omxhevcvideodec:257,... glide %U
```

### No system plugin needed

Glide calls `gstgtk4::plugin_register_static()` itself, so the `gtk4paintablesink`
element is **statically linked into the binary**. `gstreamer1.0-gtk4` is *not*
required at runtime (the `.deb` only has it as an optional Recommends).

---

## 4. The stale `/etc/environment` VP9 override (found & fixed)

`/etc/environment` line 4 (added 2026-09-08 during earlier VPU work) read:

```
GST_PLUGIN_FEATURE_RANK=omxvp9videodec:0,vp9dec:0,avdec_vp9:0
```

This forces **every** VP9 decoder to rank `NONE (0)`, so `decodebin3` reports
*"No suitable plugins found"* and **VP9 does not play in any GStreamer app**.

The distro defaults are already cedar-friendly:

| decoder | default rank |
| --- | --- |
| `omxvp9videodec` | `primary + 1 (257)` |
| `vp9dec` | `primary (256)` |
| `avdec_vp9` | `marginal (64)` |

**Fix applied 2026-11-07:** the line was deleted (backup kept at
`/etc/environment.bak.20261107-060032`). After removal, `omxvp9videodec` is
back to `257` and `playbin3` plays VP9 on cedar. Glide's merge patch means it
would work even if the line came back.

---

## 5. Validation on the OrangePi 4A

Board: GStreamer **1.28.2**, GTK **4.22.4**, libadwaita **1.9.1**, glibc **2.43**.

| Codec | Glide behaviour | Evidence |
| --- | --- | --- |
| H.264 (`~/Videos/test.mp4`, 1080p) | ✅ cedar | process holds `/dev/cedar_dev`; `omx_vdec` 1920×1080; 39 `omx_vdec` lines; `cedarc VeInitialize` |
| HEVC (640×360 test) | ✅ cedar | process holds `/dev/cedar_dev`; element `omxh265dec-omxhevcvideodec0`; 307 cedarc lines |
| VP9 (640×360, profile 0) | ✅ cedar | process holds `/dev/cedar_dev`; 39 `omx_vdec` lines (this required the merge patch + `/etc/environment` fix) |

Control experiment (playbin3, clean env): VP9 with the cedar rank → cedar
(47 log hits); without the rank boost → not cedar. HEVC already wins by default
(257 vs `avdec_h265` 256).

Note: cedar VP9 only supports **Profile 0 (8-bit 4:2:0)**. A profile-3/12-bit
4:4:4 test clip is correctly rejected ("no suitable plugins") — that is a codec
limitation, not a Glide bug.

### Window sizing & centring on the 1280×720 Wayland desktop

Glide 0.6.9 called `video_renderer.set_size_request(video_w, video_h)` on every
`VideoDimensionsChanged`. On this board's **1280×720 KDE Wayland** session a
720p/1080p video therefore grew the window to the video's native size. A Wayland
client cannot reposition its toplevel, so the growth was anchored at the
top-left: the window expanded rightwards and half of it went off-screen (only
fullscreen, `F`, was usable).

Fix (commit `669354a`, `/root/builds/patch-glide-window.py`):

- `UIContext::new` sets a **monitor-relative default size** (90 % of the monitor
  geometry, minimum 640×360) before the window is presented. KWin centres this
  initial placement.
- `resize_video_renderer` no longer touches the window: it clears the picture
  size request and sets `hexpand`/`vexpand` + `content-fit = contain`. The video
  is letterboxed inside the fixed-size window, so the window never moves or
  overflows.

Verified on the board: 720p and 1080p HEVC both play in a centred 1152×648
window (black pillarbox bars), and `F` fullscreen still works. This matches how
other Wayland-savvy players behave: the window is not resized to the video's
native resolution.

### Test media (`~/Videos`)

Real HEVC/H.265 samples downloaded 2026-11-07 from `test-videos.co.uk`
(all **HEVC Main**, `yuv420p`, 30 fps, 10 s):

| File | Resolution | Size |
| --- | --- | --- |
| `hevc-bigbuckbunny-720p.mp4` | 1280×720 | 5.2 MB |
| `hevc-jellyfish-720p.mp4` | 1280×720 | 1.1 MB |
| `hevc-bigbuckbunny-1080p.mp4` | 1920×1080 | 2.1 MB |
| `hevc-jellyfish-1080p.mp4` | 1920×1080 | 2.1 MB |

Verified: `glide ~/Videos/hevc-bigbuckbunny-720p.mp4` decodes via
`omxh265dec-omxhevcvideodec0` on cedar (`/dev/cedar_dev` held).

---

## 6. Packaging

`/root/builds/glide-make-deb.sh` assembles the tree and calls
`dpkg-deb --build --root-owner-group`:

```
usr/bin/glide
usr/share/applications/net.base_art.Glide.desktop
usr/share/icons/hicolor/scalable/apps/{net.base_art.Glide,net.base_art.Glide-symbolic}.svg
usr/share/metainfo/net.base_art.Glide.metainfo.xml
usr/share/locale/{et,fr,nl}/LC_MESSAGES/glide.mo
DEBIAN/{control,postinst}
```

Runtime deps (all present on the board): `libgtk-4-1`, `libadwaita-1-0`,
`libgstreamer1.0-0`, `libgstplay-1.0` (`gstreamer1.0-plugins-bad`),
`libgstgl` (`gstreamer1.0-gl`), plus `libc6`.

---

## 7. Reproduce

```bash
# on prox
git clone https://github.com/philn/glide.git /root/builds/glide
python3 /root/builds/patch-glide-vpu.py          # main.rs + desktop patch
source /root/builds/glide-cross-env.sh
cd /root/builds/glide
cargo build --release --target aarch64-unknown-linux-gnu --features wayland,dmabuf
bash /root/builds/glide-make-deb.sh

# on the OrangePi
scp prox:/root/builds/glide_0.6.9_arm64.deb .
sudo apt install ./glide_0.6.9_arm64.deb
glide ~/Videos/test.mp4
```