# Falkon → Clapper (Cedar VPU)

Falkon 25.12.3 GreaseMonkey userscript plus a `clapper://` URL handler that
sends YouTube `/watch` and `/shorts` pages to **one** Clapper window for
hardware decode on the Allwinner cedar VPU (`/dev/cedar_dev`). It is the Falkon
equivalent of the existing FreeTube/Flow → Clapper integrations.

The YouTube tab stays open. Clapper reuses its active window and replaces the
current video; no new Clapper process or window is created per handoff.

## 1. Platform: OS and kernel

| Item | Tested value |
|---|---|
| Board | Orange Pi 4A (Allwinner T527) |
| OS | Ubuntu 26.04 LTS (Resolute Raccoon), aarch64 |
| Desktop | AurealNix Kubuntu 0.4.1 / KDE Plasma 6 (Wayland), KWin 6.6.6 |
| Kernel | `6.18.44-g61025ec85b88` |
| Cedar driver | `sunxi_ve` 1.0.0, `/dev/cedar_dev` (`crw-rw---- root video`) |
| Falkon / Clapper | 25.12.3 (Qt 6) / 0.8.0-3 |
| GStreamer / gst-omx / libcedarc | 1.28.2 / 1.20.1 (vendor) / 1.0 |
| yt-dlp | 2026.10.26 + Node.js 22 |

Validated only on this platform. Other 6.18.44 Orange Pi 4A images with the same
cedar/GStreamer/Clapper stack should work, but the versions matter. The older
Ubuntu 22.04 / kernel 5.15 setup in the parent `GPU_VPU` README uses a different
stack; do not mix the two.

## 2. Prerequisites: packages and VPU drivers

This project is the browser handoff only. Clapper must already play YouTube
videos on cedar before installing it.

| Layer | Requirement |
|---|---|
| Kernel | Allwinner `sunxi_ve` cedar driver exposing `/dev/cedar_dev`; user in `video` group. |
| VPU userspace | `libcedarc` 1.0 (`libOmxCore.so`, `libOmxVdec.so`, `libVE.so`, codec plugins). |
| GStreamer | 1.28.2 with `gstreamer1.0-tools`, `-plugins-base`, `-good`, `-bad`, `-ugly`, `-libav`. |
| OMX bridge | Vendor `gst-omx` 1.20.1 (`/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so`). Do **not** install generic `*-omx-generic*` packages. |
| Player | `clapper` 0.8.0 + `clapper-enhancers` (Ubuntu 26.04 `universe`). |
| YouTube | `yt-dlp` 2026.10.26+ with Node.js 22 and Clapper's patched single-avc1 720p DASH enhancer. |
| Browser / utilities | `falkon` 25.12.3 with **GreaseMonkey**; `python3`, `xdg-utils`; optional `qdbus6`/KWin 6 for auto-raise. |

```bash
sudo apt update
sudo apt install falkon clapper clapper-enhancers \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  xdg-utils python3 python3-pip nodejs

python3 -m pip install --user -U yt-dlp   # or: pipx install yt-dlp
```

> If `pip` refuses with `externally-managed-environment`, use `pipx` or a
> virtual environment instead.

`libcedarc` and the Allwinner `gst-omx` plugin are **not** in the Ubuntu
archive. Install the matching vendor files for your image. The parent
`GPU_VPU/jammy_VPU_GPU_debs_T527.zip` is the 22.04 bundle and is not a drop-in
for 26.04; the validated 26.04 image already has the equivalent files. The 720p
single-avc1 DASH enhancer is part of the existing Clapper VPU setup (see the
repo's `files_tools/freetube` and `files_tools/flow` notes); this project does
not modify Clapper, yt-dlp, GStreamer, or cedar.

Verify the stack:

```bash
ls -l /dev/cedar_dev
groups | grep -w video
gst-inspect-1.0 omxh264dec | grep -E 'Rank|Long-name|Klass'
# Rank primary + 1 (257)
# Long-name OpenMAX H.264 Video Decoder
# Klass Codec/Decoder/Video/Hardware
```

If `/dev/cedar_dev` is missing, fix the kernel/cedar driver first. If access is
denied, run `sudo usermod -aG video "$USER"` and log out/in.

## 3. Clapper: select the VPU decoder

Open **Clapper → Preferences → Tweaks → GStreamer → Plugin ranking** and add
the override used on the validated system:

- Plugin: `omx`
- Plugin feature: `omxavsvideodec`
- Rank: `257` (`primary + 1`)
- Click **Add override**, then restart Clapper.

```bash
gsettings get com.github.rafostar.Clapper plugin-feature-ranks
# 'omxavsvideodec:257'
```

The actual YouTube H.264 decoder is `omxh264dec`; in this stack it already has
rank `257` (`primary + 1`). If your Clapper build lists it lower, add
`omxh264dec` at rank `257` as well. `omxavsvideodec:257` is the override present
on the validated machine.

Quick VPU check while Clapper is playing:

```bash
ls -l /proc/$(pgrep -x clapper)/fd | grep cedar
grep -i cedar /proc/interrupts
```

The first command should show `/dev/cedar_dev`; the IRQ counter should advance
during playback.

## 4. Falkon: enable GreaseMonkey

The installer enables Falkon's built-in extension automatically. Manually:

1. Open **Falkon → Settings → Configure Falkon… → Extensions** (some builds
   label it **Preferences → Extensions**).
2. Enable **GreaseMonkey** and restart Falkon.
3. Install `youtube-clapper.user.js` from the GreaseMonkey manager, or let
   `install.sh` copy it to
   `~/.config/falkon/profiles/default/extensions/greasemonkey/`.

The installer also adds `clapper` to `AutomaticallyOpenProtocols`, so a handoff
does not show the “External Protocol Request” dialog.

```bash
grep -n 'AllowedPlugins' ~/.config/falkon/profiles/default/settings.ini
# AllowedPlugins=internal:adblock, lib:GreaseMonkey.so

grep -A2 '^\[GreaseMonkey\]' \
  ~/.config/falkon/profiles/default/extensions/extensions.ini
# enabled=true
```

## Install

```bash
git clone https://github.com/defencedog/orangepi4A.git
cd orangepi4A/GPU_VPU/falkon_clapper
./install.sh --restart-falkon
```

Falkon must be closed. `--restart-falkon` waits for its session autosave,
restarts it, and restores the tabs. Without the flag, close Falkon yourself and
run `./install.sh`. The installer registers `x-scheme-handler/clapper`, installs
the userscript, enables GreaseMonkey and `clapper://` auto-open, backs up the
Falkon config, and saves the original values in
`~/.local/state/falkon-clapper/state.env`.

## How it works

```text
YouTube /watch or /shorts
  → GreaseMonkey userscript (auto countdown, ▶ Clapper button, or Alt+P)
  → clapper://play?v=<11-char-id>
  → Falkon external-protocol path → xdg-open
  → ~/.local/bin/clapper-yt-handler (validates id; builds youtube.com/watch URL)
  → /usr/bin/clapper https://www.youtube.com/watch?v=<id>
  → yt-dlp enhancer → GStreamer → omxh264dec → /dev/cedar_dev
```

The handler deliberately does **not** pass `--new-window`. Clapper 0.8.0 is a
GApplication: the first handoff starts one window; later handoffs reuse the
active window and select the new media. `--enqueue` is not used because it
queues without switching playback. On KDE, the handler uses a small KWin script
to bring the reused window forward; this is best-effort and skipped on non-KDE
sessions.

The userscript provides auto mode (1.5 s cancellable countdown), a floating
**▶ Clapper (VPU)** button, `Alt+P`, and a persisted auto ON/OFF toggle. It runs
only on `www.youtube.com` / `m.youtube.com` top frames, handles `/watch` and
`/shorts`, waits for background tabs to become visible, pauses the HTML5 player,
and offers **Play in browser**.

## Verify

```bash
~/.local/bin/clapper-yt-handler --dry-run 'clapper://play?v=jNQXAC9IVRw'
# /usr/bin/clapper https://www.youtube.com/watch?v=jNQXAC9IVRw

xdg-open 'clapper://play?v=jNQXAC9IVRw'
pgrep -c -x clapper        # 1
```

Open two videos in Falkon. Expected: one Clapper process and one window; the
second video replaces the first; the window comes to the front on KDE; both ids
appear in `~/.cache/clapper-yt-handler.log`. The primary process command line
still shows the first launch URL; that is normal.

Validated 2026-11-25: two/three handoffs kept `pgrep -c -x clapper` at 1 and the
KWin window count at 1; MPRIS `xesam:url` changed to the new video in the same
instance; the Falkon handoff was confirmed by the user.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing happens on YouTube | Is GreaseMonkey enabled and the userscript listed? Check `AllowedPlugins` and `[GreaseMonkey] enabled=true`; restart Falkon. |
| “External Protocol Request” dialog | `clapper` is missing from `AutomaticallyOpenProtocols`; add it or set `AutomaticallyOpenProtocols=..., clapper`. |
| Clapper does not open | Test `xdg-open 'clapper://play?v=...'`; check `xdg-mime query default x-scheme-handler/clapper` and `~/.cache/clapper-yt-handler.log`. |
| A second Clapper window appears | The installed handler is stale or `--new-window` was used. The dry-run output must not contain `--new-window`; rerun `./install.sh`. |
| No VPU decode | Verify `omxh264dec` rank 257, the Clapper override, `/dev/cedar_dev`, and `video` group membership. |
| Window stays behind Falkon | KWin scripting is unavailable; bring it forward manually. Playback still uses one instance. |

Logs: `~/.cache/clapper-yt-handler.log`, `~/.cache/falkon-clapper-launch.log`,
`~/.cache/falkon-clapper/raise-clapper.js`, and
`~/.local/state/falkon-clapper/state.env`.

## Uninstall

```bash
cd orangepi4A/GPU_VPU/falkon_clapper
./uninstall.sh --restart-falkon
```

Removes the handler, desktop entry, userscript, KWin helper cache, and
`clapper` scheme association; restores the original `AllowedPlugins`,
`AutomaticallyOpenProtocols`, and `[GreaseMonkey] enabled` values. It does not
touch Clapper/yt-dlp/GStreamer/cedar.

## Security and limits

- The handler accepts only `clapper://` URLs with a valid 11-character id and
  launches only `/usr/bin/clapper` with a `youtube.com/watch` URL.
- No localhost daemon or listening port; the scheme is user-local.
- YouTube Music, embedded players, and live streams are not special-cased.
- Manual extra Clapper windows (Clapper's own new-window action) are outside
  the integration's control.
- Auto-raise depends on KDE KWin scripting; other desktops still get
  single-instance playback but may not raise the window.

## Files

| File | Purpose |
|---|---|
| `clapper-yt-handler` | `clapper://` → `clapper <watch-url>` handler; single-instance and KWin raise. |
| `clapper-yt-handler.desktop` | `x-scheme-handler/clapper` desktop entry. |
| `youtube-clapper.user.js` | Falkon GreaseMonkey userscript. |
| `falkon_ini.py` | Line-preserving Falkon INI editor used by installer/uninstaller. |
| `install.sh` / `uninstall.sh` | Idempotent install/removal with config backups. |

Parent GPU/VPU notes: [`../README.md`](../README.md).
