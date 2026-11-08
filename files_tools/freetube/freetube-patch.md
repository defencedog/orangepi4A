# FreeTube hardware-accelerated playback on OrangePi 4A (cedar VPU)

Goal: make FreeTube play YouTube videos using the Allwinner **cedar** VPU
(`/dev/cedar_dev`).

Why the external-player route: on this board Chromium/Electron has **no
hardware video decode** (no VA-API driver for cedar, no `/dev/video*`), so
FreeTube's built-in shaka player decodes in software (100%+ CPU at 1080p).
Clapper + GStreamer **does** have a working cedar path via gst-omx
(`omxh264dec` → libcedarc → `/dev/cedar_dev`).

Resulting pipeline:

```
FreeTube (click a video)
  -> spawns: clapper https://www.youtube.com/watch?v=<id>
     -> clapper yt-dlp enhancer
        -> yt-dlp (2026.08.19, default client chain = visionos)
        -> ClapperYoutubeIE override adds DASH init/index ranges
        -> clapper_yt_dlp_dash.py builds a manifest with ONE H.264 rep
     -> GStreamer: dashdemux -> omxh264dec -> /dev/cedar_dev   (HW decode)

Host: OrangePi 4A, Ubuntu (aarch64), KDE Plasma Wayland, user `ukhan`.

> **2026-11-07 — FreeTube upgraded 0.25.3 → 0.26.0** (arm64 `.deb`, sha256
> `a1e28c998b64fe682184a864610959425f63a0e8db87d4c290fb0c127aee5093`,
> Electron 44.10.0). This integration is unchanged: the stock
> `external-player-map.json` still lists Clapper, `settings.db` survived the
> upgrade, and the spawn path (`clapper https://www.youtube.com/watch?v=<id>`)
> was re-verified.

---

## Changes (each with backup + revert)

### Change 1 - FreeTube: use the external player
File: `~/.config/FreeTube/settings.db`  (NDJSON; edit only while FreeTube is closed)
Backup: `~/.config/FreeTube/settings.db.bak-20261016`
Added/appended line:
```json
{"_id":"defaultViewingMode","value":"external_player"}
```
Other relevant existing keys: `externalPlayer = "clapper"`.
Optional: `{"_id":"externalPlayerIgnoreWarnings","value":true}` to silence the
"external player may not support all features" notice (the player is launched
either way).

Revert:
```bash
# FreeTube must be closed
cp ~/.config/FreeTube/settings.db.bak-20261016 ~/.config/FreeTube/settings.db
```

### Change 2 - install Clapper GObject typelib
```bash
sudo apt-get install -y gir1.2-clapper-0.0
```
(required so `gi` consumers can load the `Clapper` namespace.)
Revert: `sudo apt-get remove -y gir1.2-clapper-0.0`

### Change 3 - yt-dlp upgraded (system-wide, user site)
```bash
pip3 install --break-system-packages -U yt-dlp
pip3 install --break-system-packages yt-dlp-ejs
```
Result: yt-dlp **2026.08.19** at `~/.local/lib/python3.14/site-packages/yt_dlp`
(shadows the apt 2026.03.17). Clapper runs as `ukhan`, so it picks this up.
`yt-dlp-ejs 0.8.0` provides the JS runtime bits; Node is present
(`/usr/bin/node` v22.22.1).

Note: with 2026.08.19 the default client chain now uses the **visionos**
client, which returns uncapped DASH formats without a JS runtime. The old
`android_vr` client was abandoned because it hard-caps every URL at
~the first 60 s of the video (403 beyond), which caused playback to stall at
t=60 s.

Revert:
```bash
pip3 uninstall --break-system-packages -y yt-dlp yt-dlp-ejs
```

### Change 4 - clapper yt-dlp plugin options
File: `/usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp.py`
(owned by package `clapper-enhancers` 0.8.0-3)
Backups: `clapper_yt_dlp.py.bak-20261016` (stock), `clapper_yt_dlp.py.bak-20261016b`

Changes in `YTDL_OPTS`:
* `'player_client': ['ios']`  ->  `['default']`   (use the working visionos chain)
* added `'js_runtimes': {'node': {}},` (note: must be a dict in 2026.08+)

```python
    'ignoreconfig': True,
    'js_runtimes': {'node': {}},
    # ...
    'extractor_args': {
        'youtube': {
            'skip': ['translated_subs'],
            'player_client': ['default']
        }
    }
```
Revert: `sudo cp /usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp.py.bak-20261016 <that file>`

### Change 5 - ClapperYoutubeIE override made compatible with yt-dlp 2026.08.19
File: `/usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp_overrides.py`
(no backup file; file is small and owned by `clapper-enhancers`)
The stock override called
`super()._extract_formats_and_subtitles(streaming_data, video_id, ...)`, but
yt-dlp 2026.08.19 expects
`(self, video_id, player_responses, player_url, live_status, duration)`.
Without this patch every YouTube extraction failed with
`AttributeError: 'str' object has no attribute 'get'`, so no DASH manifest
could be produced.

Patched signature + deriving `streaming_data` from the player responses:
```python
def _extract_formats_and_subtitles(self, video_id, player_responses, player_url,
                                   live_status=None, duration=None):
    streaming_data = [
        resp["streamingData"] for resp in list(player_responses)
        if isinstance(resp, dict) and isinstance(resp.get("streamingData"), dict)
    ]
    formats, subtitles = super()._extract_formats_and_subtitles(
        video_id, player_responses, player_url,
        live_status=live_status, duration=duration)
    # ... existing code that copies initRange/indexRange into
    #     streaming_options.init_range / index_range, in place.
```

Revert (restores all enhancer files to stock):
```bash
sudo apt-get install --reinstall -y clapper-enhancers
```

### Change 6 - DASH manifest: single H.264 representation (capped at 720p)
File: `/usr/lib/aarch64-linux-gnu/clapper-0.0/enhancers/yt-dlp/clapper_yt_dlp_dash.py`
Backups: `clapper_yt_dlp_dash.py.bak-20261016` (stock) and
`clapper_yt_dlp_dash.py.bak-1080p-20261016` (the earlier 1080p-capped variant)
Reason: the cedar OMX decoder **segfaults** when GStreamer renegotiates the
video format (i.e. when a DASH stream switches representation):
`gst_omx_video_dec_set_format` -> `..._disable` ->
`gst_omx_port_deallocate_buffers_unlocked` -> `__AwOmxVdecFreeBuffer` ->
`__liFreePortBuffer(pBuffer=0x0)` (NULL memcpy). Keeping a single video
representation removes the switch entirely.

The patch filters `info["formats"]` at the top of `generate_manifest(info)`:
* prefer the single best **avc1** format that is DASH-eligible
  (`container` ends with `_dash` and has `streaming_options.init_range` +
  `index_range`), keep all audio (`vcodec == "none"`);
* **capped at 720p** - only avc1 reps with `height <= 720` are considered
  (picks 720p60 = itag 298 when offered, else 720p30 = itag 136); if a video has
  no <=720p avc1 rep it falls back to the best avc1 available;
* fallback: best rep per video codec.

This also guarantees H.264 (cedar decodes avc1; it cannot decode AV1, and its
VP9/HEVC paths are unreliable). Without the `_dash_ok` test the filter used to
pick a duplicate avc1 entry that had no container/ranges, the avc1 adaptation
set was skipped, and the manifest fell back to AV1 4K which cedar can't play.

Revert: `sudo cp .../clapper_yt_dlp_dash.py.bak-20261016 .../clapper_yt_dlp_dash.py`
(or `sudo apt-get install --reinstall -y clapper-enhancers`).

### Change 7 - rebuild script (housekeeping)
The above plugin edits were applied with
`~/opi4a/patch_plugins_final.py` (local copy:
`/data/data/com.termux/files/home/agy_ukhan/opi4a/patch_plugins_final.py`),
which rebuilds `clapper_yt_dlp_dash.py` from its backup and rewrites the two
`YTDL_OPTS` lines in `clapper_yt_dlp.py`, then byte-compiles both.

### Change 8 - opi-mon: add VPU (cedar) telemetry
Files (both kept in sync; the system command is symlinked to the first):
* `/home/ukhan/NPU_modules_opi4a_6.18.44/opi-mon`
* `/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/opi-mon`
Backups: `opi-mon.bak-20261016` (script) and `opi-mon.md.bak-20261016` (docs)
in both directories.

Added a `VPU` row to the dashboard, using the same Runtime-PM style as the
existing `NPU` row:
* Load % = delta of
  `/sys/devices/platform/soc/1c0e000.video-engine/power/runtime_active_time`
  over the refresh interval (clamped 0-100); `runtime_status` is
  `active` while decoding, `suspended` when idle.
* Secondary field = summed `cedar_dev` interrupt rate from `/proc/interrupts`
  (irq/s, a decode-throughput proxy); engine tag `cedar` (no VPU devfreq or
  thermal zone exists on this board).
* New color `BR_CYAN` (`\033[96m`) for the row.

Example while playing a FreeTube video (clapper -> omxh264dec -> cedar):
`VPU 100% [██████████] 32/s  cedar`; idle: `VPU 0% [░░░░░░░░░░] 0/s  cedar`.

Revert:
```bash
D=/home/ukhan/NPU_modules_opi4a_6.18.44; V=/home/ukhan/NPU_modules_opi4a_6.18.44_vendor
cp -a $D/opi-mon.bak-20261016 $D/opi-mon
cp -a $V/opi-mon.bak-20261016 $V/opi-mon
cp -a $D/opi-mon.md.bak-20261016 $D/opi-mon.md
cp -a $V/opi-mon.md.bak-20261016 $V/opi-mon.md
```

Notes:
* The VPU telemetry is readable without root (unlike `clk_summary`, which shows
  the `ve` clock at 520 MHz but requires root/debugfs).
* `runtime_active_time` accumulates at ~wall rate while decoding, so the bar is
  effectively a "VPU powered/decoding" indicator (like the NPU row).
* Verified: `status=active`, active_time advancing, `cedar_dev` IRQ ~31-33/s,
  `/dev/cedar_dev` held open by clapper during playback; idle -> `suspended`,
  0/s.

---

## How FreeTube decides to open the external player (important for testing)

Two guards must both pass:

1. Renderer (`preload`): `openInExternalPlayer` only sends the IPC if
   `navigator.userActivation.isActive` - i.e. a **real user gesture**. A
   programmatic navigation to a video URL does **not** open the external
   player; the internal player just starts.
   The watch page hides the manual "open in external player" button when
   `defaultViewingMode === "external_player"` (it is meant to auto-open).
   In a **video list** (search results / trending), clicking a title or
   thumbnail calls the handler that pauses the internal player and opens the
   external one - this is the normal user flow.

2. Main process (`gt`): needs `e.senderFrame.url` to be the app page and
   **`e.sender.isFocused()`** - the FreeTube window must be focused, plus a
   valid 11-char videoId, `externalPlayer` set and present in
   `static/external-player-map.json`.

The command spawned is exactly:
```
clapper https://www.youtube.com/watch?v=<videoId>
```

## Verification

* Manifest probe (with the patched plugin + override):
  `dash.generate_manifest()` -> OK, video reps `['298','139','140']`,
  `maxHeight 720` (itag 298 = avc1 720p60), audio mp4.
  (Was `['299',...]` / 1080p60 before the 720p cap.)
* `clapper <url>` standalone: **150 s** of playback, position advanced in real
  time, `/dev/cedar_dev` held open the whole time, ~20% CPU (software decode
  would be far higher), no errors.
* FreeTube end-to-end (driven over CDP with a real click + focused window):
  FreeTube spawned `clapper https://www.youtube.com/watch?v=h17LanZ4drU`;
  that clapper process held `/dev/cedar_dev` and advanced position
  40 s -> 65 s.
* opi-mon VPU row (see Change 8): first run while playing showed
  `VPU 100% [██████████]    31/s  cedar`; idle (clapper stopped, engine
  `suspended`) showed `VPU 0% [░░░░░░░░░░]     0/s  cedar`. A second playback
  run showed the `2%` -> `100%` transition within the first refresh frames.

## Known limitations

* H.264 only for reliable HW decode (single avc1 rep). VP9/HEVC/AV1 are
  skipped to keep cedar stable.
* Resolution is capped at **720p** (best avc1 rep with `height <= 720`, i.e.
  720p60/itag 298 when available). This is a deliberate quality/robustness
  trade-off on this box; raise the cap (or remove `avc1_capped`) for 1080p.
* Cedar OMX crashes on format renegotiation - do not re-enable multi-rep DASH
  without a GStreamer-side workaround.
* `itag 18` (progressive) and the `android_vr` adaptive URLs are currently
  useless (403 / 60 s cap); the `default` (visionos) chain is what works.
* yt-dlp 2026.08.19 lives in `~/.local` and shadows the distro package; distro
  upgrades won't change what Clapper uses.

## Revert everything

```bash
# close FreeTube first
cp ~/.config/FreeTube/settings.db.bak-20261016 ~/.config/FreeTube/settings.db
sudo apt-get install --reinstall -y clapper-enhancers
pip3 uninstall --break-system-packages -y yt-dlp yt-dlp-ejs
sudo apt-get remove -y gir1.2-clapper-0.0

# revert the opi-mon VPU telemetry (Change 8)
D=/home/ukhan/NPU_modules_opi4a_6.18.44; V=/home/ukhan/NPU_modules_opi4a_6.18.44_vendor
cp -a $D/opi-mon.bak-20261016 $D/opi-mon
cp -a $V/opi-mon.bak-20261016 $V/opi-mon
cp -a $D/opi-mon.md.bak-20261016 $D/opi-mon.md
cp -a $V/opi-mon.md.bak-20261016 $V/opi-mon.md
```
