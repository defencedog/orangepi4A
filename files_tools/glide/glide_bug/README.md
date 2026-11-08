# Glide GUI bug report — ready to submit

Self-contained bug report + patch for upstream
[`philn/glide`](https://github.com/philn/glide): windowed playback grows the
window to the video's native size and spills off-screen on Wayland.

## Contents

| File | Purpose |
| --- | --- |
| `issue-window-sizing.md` | Ready-to-paste GitHub issue body (suggested title is in an HTML comment at the top). |
| `0001-window-keep-screen-relative-and-centred.patch` | `git format-patch` commit. Contains **only** the window-sizing fix. |

## How to submit

### Web UI

1. Open <https://github.com/philn/glide/issues/new>.
2. Title:
   **Window grows to the video's native size and spills off-screen in windowed mode (Wayland)**
3. Paste the contents of `issue-window-sizing.md` as the body.
4. Attach `0001-window-keep-screen-relative-and-centred.patch` (drag it into the
   comment box) — the diff is also embedded in the issue under `<details>`.

### `gh` CLI

```bash
cd glide_bug
gh issue create \
  --repo philn/glide \
  --title "Window grows to the video's native size and spills off-screen in windowed mode (Wayland)" \
  --body-file issue-window-sizing.md
```

## Base revision

- Upstream: `philn/glide` **v0.6.9**, commit **`d6ed2e8`**
- Verified with `git apply --check` against a pristine `d6ed2e8` tree:
  applies cleanly.
- Patch stat: `src/ui_context.rs | 25 +++++++++++++++++++++++--` (1 file,
  +23 −2).

## Notes

- The patch deliberately contains **only** the GUI/window fix. It excludes the
  board-specific cedar/GStreamer decoder ranking changes used on the OrangePi
  4A, so it is suitable for upstream review as-is.
- The fix was built and tested on aarch64 (OrangePi 4A), KDE Plasma 6 Wayland,
  1280×720, with 720p and 1080p HEVC clips.
- If the maintainer prefers to keep “resize window to video”, the issue lists
  the alternatives and why they are not portable on Wayland.