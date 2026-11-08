# Flow-Desktop → Clapper (cedar VPU) integration

This documents the source-code changes and the launch/runtime wiring that make
Flow-Desktop hand video playback to **Clapper**, decoding on the Allwinner
**cedar** VPU (`/dev/cedar_dev`) instead of crashing in WebKitGTK.

- Target: OrangePi 4A (aarch64), Ubuntu Jammy, WebKitGTK 2.52.6, GStreamer 1.28.2.
- App: Flow-Desktop `0.1.0-beta3` (Tauri 2 + React), installed as a `.deb`.
- Build host: this machine (`prox`), working tree `/root/builds/Flow-Desktop`.
- Patch script: `/root/builds/patch-flow-clapper.py` (idempotent).

## 1. Why

Flow's two native WebKit playback paths fail against this board's OMX/cedar
component:

- **MSE** (`dash-native` / `sabr-dash`): `Allocated buffers for avc port 1:
  Not implemented (0x80001006)`.
- **Progressive `<video>`**: cedar initializes at 1280x720, then the web process
  dies: `web_process_terminated window=main reason=Crashed recovery=Quit`, and
  Flow exits.

This is a WebKitGTK ↔ `gst-omx` incompatibility below Flow's code, so it cannot
be fixed by stream selection. The proven workaround (already used by FreeTube on
this board) is to let **Clapper** decode a single H.264 720p stream on cedar.

## 2. Preconditions (runtime, on the OrangePi)

- `clapper` in `PATH` (`/usr/bin/clapper`), with the patched yt-dlp enhancer that
  caps streams to a single H.264 720p representation (see `freetube-patch.md`).
- `libcedarc` + the manually installed `gst-omx` plugin
  (`/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so`).
- `~/.local/bin/yt-dlp` (patched) visible to the user running Flow, because the
  Clapper child process inherits Flow's environment.

## 3. Source changes (Clapper integration)

All file paths are under `/root/builds/Flow-Desktop`.

### 3.1 `src-tauri/src/commands/external.rs` — new backend command

Import change:

```rust
use crate::security::validation::{validate_external_url, validate_video_id};
```

New command appended to the file:

```rust
/// Opens a YouTube video in an external player so decoding runs on the SoC's
/// hardware decoder instead of WebKit.
///
/// WebKit's media pipeline cannot drive this board's OMX/cedar decoder:
/// starting playback aborts the web process (`web_process_terminated
/// reason=Crashed`). Handing the watch URL to Clapper keeps decoding on the
/// VPU. `FLOW_EXTERNAL_PLAYER` overrides the program (default `clapper`).
#[tauri::command]
pub fn play_external(video_id: String) -> Result<(), ErrorResponse> {
    validate_video_id(&video_id).map_err(ErrorResponse::from)?;

    let program =
        std::env::var("FLOW_EXTERNAL_PLAYER").unwrap_or_else(|_| "clapper".to_string());
    let url = format!("https://www.youtube.com/watch?v={video_id}");

    let mut child = std::process::Command::new(&program)
        .arg(&url)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|error| ErrorResponse::from(AppError::Internal(format!("Could not launch {program}: {error}"))))?;

    // Reap the child once it exits so it cannot linger as a zombie; the player
    // itself must keep running after this command returns.
    std::thread::spawn(move || {
        let _ = child.wait();
    });

    Ok(())
}
```

Notes:
- The URL is built from a validated 11-char id (`security::validation::validate_video_id`).
- `FLOW_EXTERNAL_PLAYER` overrides the program (default `clapper`); e.g. set it
  to test with `mpv`, or to an absolute path.
- The child is detached and reaped on a thread; Flow does not block.

### 3.2 `src-tauri/src/lib.rs` — register the command

```rust
use commands::external::{open_external, play_external};
```

and in the `invoke_handler` list, next to `open_external,`:

```rust
            play_external,
```

### 3.3 `src/lib/settings/schema.ts` — one setting, default on

Key in `SETTINGS`:

```ts
  EXTERNAL_PLAYER_ENABLED: "external_player_enabled",
```

Scope in `SETTING_SCOPES` (must exist or TypeScript `satisfies Record<...>`
fails):

```ts
  [SETTINGS.EXTERNAL_PLAYER_ENABLED]: "profile",
```

Definition in `SETTING_DEFINITIONS`:

```ts
  bool(SETTINGS.EXTERNAL_PLAYER_ENABLED, "player", true, "wired"),
```

### 3.4 `src/components/settings/tabs/PlayerTab.tsx` — toggle UI

```ts
  const [externalPlayer, setExternalPlayer] = useBoolPref(SETTINGS.EXTERNAL_PLAYER_ENABLED, true);
```

```tsx
        <SettingItem title={getString('settings_external_player')} description={getString('settings_external_player_desc')}>
          <ToggleSwitch checked={externalPlayer} onChange={setExternalPlayer} />
        </SettingItem>
```

### 3.5 `src/lib/i18n/strings.json` — new strings

```json
  "settings_external_player": "Play videos in Clapper (VPU)",
  "settings_external_player_desc": "Open every video in Clapper so decoding runs on the cedar VPU. This also avoids a crash in WebKit's built-in player on this device.",
  "player_external_placeholder_title": "Playing in Clapper (VPU)",
  "player_external_reopen": "Open in Clapper again",
  "player_external_open_browser": "Open on YouTube"
```

### 3.6 `src/components/watch/types.ts` — new prop

```ts
export interface FlowPlayerCoreProps {
  videoId: string;
  videoDetails: VideoDetails | null;
  onEnded?: () => void;
  /** When true, playback is handed to an external VPU player (Clapper). */
  allowExternalPlayer?: boolean;
}
```

### 3.7 `src/components/watch/FlowPlayerCore.tsx` — launch + placeholder

Import:

```ts
import { invokeBackend, getBackendErrorMessage } from "../../lib/api/errors";
```

Signature + setting read:

```tsx
export function FlowPlayerCore({
  videoId,
  videoDetails,
  onEnded,
  allowExternalPlayer,
}: FlowPlayerCoreProps) {
  ...
  const showToast = useUiStore((s) => s.showToast);
  const externalPlayerEnabled =
    useAppSettingsStore((s) => s.values[SETTINGS.EXTERNAL_PLAYER_ENABLED] !== "false");
  const useExternalPlayer = allowExternalPlayer === true && externalPlayerEnabled;
```

Ref (with the other refs):

```ts
  const externalLaunchedForRef = useRef<string | null>(null);
```

Launch callback + once-per-video effect (declared after `handleOpenInBrowser`,
before the return):

```tsx
  /** Hand this video to the external VPU player (Clapper). WebKit's own
   * decoder crashes this board, so the watch surface uses this by default. */
  const launchExternalPlayer = useCallback(() => {
    if (!videoId) return;
    void invokeBackend<void>("play_external", { videoId }).catch((error) => {
      showToast({ variant: "error", message: getBackendErrorMessage(error) });
    });
  }, [videoId, showToast]);

  useEffect(() => {
    if (!useExternalPlayer || !videoId) return;
    if (externalLaunchedForRef.current === videoId) return;
    externalLaunchedForRef.current = videoId;
    launchExternalPlayer();
  }, [useExternalPlayer, videoId, launchExternalPlayer]);
```

Early return that replaces `<Player>` (all hooks above it still run, so hook
order is preserved):

```tsx
  if (useExternalPlayer) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-black px-6 text-center text-chrome-zinc-100">
        <p className="text-sm font-medium sm:text-base">{getString("player_external_placeholder_title")}</p>
        <p className="line-clamp-2 max-w-md text-xs text-chrome-zinc-400">{title}</p>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
          <button type="button" onClick={launchExternalPlayer}
            className="rounded-full border border-outline-variant px-4 py-1.5 text-xs font-medium text-chrome-zinc-200 transition-colors hover:bg-chrome-white/10">
            {getString("player_external_reopen")}
          </button>
          {watchUrl && (
            <button type="button" onClick={handleOpenInBrowser}
              className="rounded-full border border-outline-variant px-4 py-1.5 text-xs font-medium text-chrome-zinc-200 transition-colors hover:bg-chrome-white/10">
              {getString("player_external_open_browser")}
            </button>
          )}
        </div>
      </div>
    );
  }
```

### 3.8 `src/components/watch/GlobalVideoPlayer.tsx` — opt in the main surface

```tsx
        <FlowPlayerCore videoId={videoIdForPlayer} videoDetails={cachedDetails} allowExternalPlayer />
```

`PipWindowApp.tsx` is intentionally left unchanged (PiP stays native).

## 4. Interacting VPU patches (pre-existing)

These were applied earlier (`patch-flow-vpu.py`) and are not part of the Clapper
hook itself, but they matter to the runtime environment:

- `src-tauri/src/main.rs` — exports the GStreamer rank for the whole process tree
  (so the Clapper child inherits it too).
- `src-tauri/linux/flow.desktop` — same rank exported when launched from the menu.
- `src/lib/useVideoStream.ts` — VOD offers only the `direct` source mode.
- quality default `720p` in `src/lib/settings/schema.ts` and
  `src/components/settings/tabs/QualityTab.tsx`.

## 5. Launch method and Clapper runtime interface

### 5.1 How Flow must be built and launched

- Flow must be a **production** build (see §6). A dev-mode build tries to load
  `http://localhost:1420` and shows "Could not connect to localhost".
- Installed layout: binary `/usr/bin/flow`, resources `/usr/lib/Flow/sidecar`,
  desktop entry `/usr/share/applications/Flow.desktop`.
- Launch from the menu (**Flow**) or from a shell as the desktop user (`flow`).

### 5.2 Environment Flow exports (inherited by Clapper)

`src-tauri/linux/flow.desktop`:

```
Exec=env GST_PLUGIN_FEATURE_RANK=omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257 {{exec}} %u
```

`src-tauri/src/main.rs` (covers terminal launches):

```rust
std::env::set_var(
    "GST_PLUGIN_FEATURE_RANK",
    "omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257",
);
```

So cedar's OMX decoders outrank the software decoders for **every** child
GStreamer pipeline, including the one Clapper spawns.

### 5.3 How Flow hands off to Clapper

When a video is opened on the main watch surface:

1. `GlobalVideoPlayer` renders `FlowPlayerCore ... allowExternalPlayer`.
2. `FlowPlayerCore` sees `external_player_enabled` (default on) and calls the
   Tauri command `play_external` with `{ videoId }` (once per video id).
3. `play_external` runs, on the Rust side:

```rust
std::process::Command::new(&program)          // program = $FLOW_EXTERNAL_PLAYER or "clapper"
    .arg(format!("https://www.youtube.com/watch?v={video_id}"))
    .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
    .spawn()
```

4. Clapper resolves the URL through its patched yt-dlp enhancer (single H.264
   720p rep) and plays it on cedar.
5. Flow renders the "Playing in Clapper (VPU)" placeholder and **stays alive**.

Equivalent manual command (same as what Flow spawns):

```bash
GST_PLUGIN_FEATURE_RANK=omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257 \
  clapper https://www.youtube.com/watch?v=<11-char-id>
```

Override the player without rebuilding:

```bash
FLOW_EXTERNAL_PLAYER=/usr/bin/clapper flow
# or, for a quick A/B test:
FLOW_EXTERNAL_PLAYER=/usr/bin/mpv flow
```

## 6. Build and package (on prox)

```bash
cd /root/builds/Flow-Desktop
export PATH=/root/.cargo/bin:/root/tools/arm64-bin:/root/tools/node-v22.22.1-linux-x64/bin:$PATH
export PKG_CONFIG_ALLOW_CROSS=1 PKG_CONFIG=aarch64-linux-gnu-pkg-config
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc
export CC_aarch64_unknown_linux_gnu=aarch64-linux-gnu-gcc CXX_aarch64_unknown_linux_gnu=aarch64-linux-gnu-g++
export AR_aarch64_unknown_linux_gnu=aarch64-linux-gnu-ar STRIP=aarch64-linux-gnu-strip

pnpm build
# custom-protocol is REQUIRED (production/embedded frontend):
( cd src-tauri && cargo build --release --target aarch64-unknown-linux-gnu \
    --features tauri/custom-protocol )

pnpm tauri bundle --config src-tauri/tauri.vpu.conf.json --bundles deb \
  --target aarch64-unknown-linux-gnu
```

Gotchas:

- Without `--features tauri/custom-protocol` the binary is a dev build pointing
  at `http://localhost:1420` → "Could not connect to localhost".
- `tauri bundle` needs `--target aarch64-unknown-linux-gnu`, otherwise it looks
  for the host binary at `target/release/flow`.
- `/usr/local/lib/pkgconfig/ayatana-appindicator3-0.1.pc` must exist; the Tauri
  bundler calls the host `pkg-config` and ignores the cross `PKG_CONFIG`.
- Verify production: `grep -c "rustc-cfg=dev"` should be `0` in the newest
  `src-tauri/target/aarch64-unknown-linux-gnu/release/build/flow-*/output`.

Artifact: `src-tauri/target/aarch64-unknown-linux-gnu/release/bundle/deb/Flow_0.1.0-beta3_arm64.deb`
(≈17.8 MiB). Install:

```bash
sudo apt-get install -y --reinstall /path/to/Flow_0.1.0-beta3_arm64.deb
```

## 7. Verification on the board

1. Launch Flow, click a video.
2. Flow stays open and shows "Playing in Clapper (VPU)".
3. Clapper opens and plays.
4. `opi-mon` shows the VPU/cedar active; or check directly:

```bash
grep cedar /proc/interrupts                 # IRQ counter should advance during playback
cat /sys/devices/platform/soc/1c0e000.video-engine/power/runtime_status   # active
```

Revert to native (crashes on this board) via Settings → Player, or by setting
`external_player_enabled=false` in the profile DB.

## 8. Known limitations

- **Shorts** use `ShortPlayer.tsx` / `ShortVideoSurface`, not `FlowPlayerCore`;
  they still attempt native WebKit playback and can crash the web process.
- **YouTube Music** audio uses its own path and is not routed.
- Watch position/history is not recorded during Clapper playback.
- PiP window playback is intentionally not routed through Clapper.

## 9. Revert

- Disable the setting (Settings → Player, or `external_player_enabled=false`).
- Or revert the source with `git checkout -- <files>` / `git stash`, then
  rebuild and repackage.
- `patch-flow-clapper.py` is idempotent: re-running on a patched tree is a no-op.
