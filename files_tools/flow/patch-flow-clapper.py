#!/usr/bin/env python3
"""Add a VPU (cedar) external-player path to Flow-Desktop.

WebKit's media pipeline cannot drive this board's OMX/cedar decoder: starting
playback aborts the web process (``web_process_terminated reason=Crashed``).
This patch adds a ``play_external`` Tauri command that hands the watch URL to
Clapper (whose single-H.264-720p cedar pipeline is proven on the Orange Pi) and
makes the watch player use it by default.

Idempotent: re-running on an already patched tree is a no-op.

Usage: python3 patch-flow-clapper.py [/path/to/Flow-Desktop]
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/root/builds/Flow-Desktop")


def _read(rel: str) -> str:
    return (REPO / rel).read_text()


def _write(rel: str, text: str) -> None:
    (REPO / rel).write_text(text)


def replace_once(rel: str, old: str, new: str, marker: str | None = None) -> None:
    """Replace `old` with `new` exactly once. Skip when `marker` is present."""
    text = _read(rel)
    if marker and marker in text:
        print(f"skip    {rel}")
        return
    found = text.count(old)
    if found != 1:
        raise SystemExit(
            f"ERROR {rel}: expected exactly 1 match, found {found}\n--- old ---\n{old}"
        )
    _write(rel, text.replace(old, new, 1))
    print(f"patched {rel}")


# ---------------------------------------------------------------------------
# 1. Rust: the play_external command.
# ---------------------------------------------------------------------------
replace_once(
    "src-tauri/src/commands/external.rs",
    "use crate::security::validation::validate_external_url;",
    "use crate::security::validation::{validate_external_url, validate_video_id};",
    marker="validate_video_id",
)

PLAY_EXTERNAL_RUST = '''

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
'''

external_rs = _read("src-tauri/src/commands/external.rs")
if "pub fn play_external" in external_rs:
    print("skip    src-tauri/src/commands/external.rs (play_external)")
else:
    _write("src-tauri/src/commands/external.rs", external_rs.rstrip() + PLAY_EXTERNAL_RUST)
    print("patched src-tauri/src/commands/external.rs (play_external)")

# ---------------------------------------------------------------------------
# 2. Rust: register the command.
# ---------------------------------------------------------------------------
replace_once(
    "src-tauri/src/lib.rs",
    "use commands::external::open_external;",
    "use commands::external::{open_external, play_external};",
    marker="play_external",
)
replace_once(
    "src-tauri/src/lib.rs",
    "            open_external,\n",
    "            open_external,\n            play_external,\n",
    marker="            play_external,\n",
)

# ---------------------------------------------------------------------------
# 3. Settings schema: one profile setting, enabled by default.
# ---------------------------------------------------------------------------
replace_once(
    "src/lib/settings/schema.ts",
    '  AUTOPLAY_ENABLED: "autoplay_enabled",\n',
    '  AUTOPLAY_ENABLED: "autoplay_enabled",\n  EXTERNAL_PLAYER_ENABLED: "external_player_enabled",\n',
    marker="EXTERNAL_PLAYER_ENABLED",
)
replace_once(
    "src/lib/settings/schema.ts",
    '  [SETTINGS.AUTOPLAY_ENABLED]: "profile",\n',
    '  [SETTINGS.AUTOPLAY_ENABLED]: "profile",\n  [SETTINGS.EXTERNAL_PLAYER_ENABLED]: "profile",\n',
    marker="[SETTINGS.EXTERNAL_PLAYER_ENABLED]",
)
replace_once(
    "src/lib/settings/schema.ts",
    '  bool(SETTINGS.AUTOPLAY_ENABLED, "player", true, "wired"),\n',
    '  bool(SETTINGS.AUTOPLAY_ENABLED, "player", true, "wired"),\n'
    '  bool(SETTINGS.EXTERNAL_PLAYER_ENABLED, "player", true, "wired"),\n',
    marker="bool(SETTINGS.EXTERNAL_PLAYER_ENABLED",
)

# ---------------------------------------------------------------------------
# 4. Strings.
# ---------------------------------------------------------------------------
NEW_STRINGS = (
    '  "topbar_forward": "Forward",\n'
    '  "settings_external_player": "Play videos in Clapper (VPU)",\n'
    '  "settings_external_player_desc": "Open every video in Clapper so decoding runs on the cedar VPU. This also avoids a crash in WebKit\'s built-in player on this device.",\n'
    '  "player_external_placeholder_title": "Playing in Clapper (VPU)",\n'
    '  "player_external_reopen": "Open in Clapper again",\n'
    '  "player_external_open_browser": "Open on YouTube"\n'
    "}"
)
replace_once(
    "src/lib/i18n/strings.json",
    '  "topbar_forward": "Forward"\n}',
    NEW_STRINGS,
    marker="settings_external_player",
)

# ---------------------------------------------------------------------------
# 5. Settings UI toggle.
# ---------------------------------------------------------------------------
replace_once(
    "src/components/settings/tabs/PlayerTab.tsx",
    "  const [autoplay, setAutoplay] = useBoolPref(SETTINGS.AUTOPLAY_ENABLED, true);\n",
    "  const [autoplay, setAutoplay] = useBoolPref(SETTINGS.AUTOPLAY_ENABLED, true);\n"
    "  const [externalPlayer, setExternalPlayer] = useBoolPref(SETTINGS.EXTERNAL_PLAYER_ENABLED, true);\n",
    marker="setExternalPlayer",
)
replace_once(
    "src/components/settings/tabs/PlayerTab.tsx",
    "        <SettingItem title={getString('settings_autoplay')} description={getString('settings_autoplay_desc')}>\n"
    "          <ToggleSwitch checked={autoplay} onChange={setAutoplay} />\n"
    "        </SettingItem>\n",
    "        <SettingItem title={getString('settings_autoplay')} description={getString('settings_autoplay_desc')}>\n"
    "          <ToggleSwitch checked={autoplay} onChange={setAutoplay} />\n"
    "        </SettingItem>\n"
    "        <SettingItem title={getString('settings_external_player')} description={getString('settings_external_player_desc')}>\n"
    "          <ToggleSwitch checked={externalPlayer} onChange={setExternalPlayer} />\n"
    "        </SettingItem>\n",
    marker="settings_external_player",
)

# ---------------------------------------------------------------------------
# 6. FlowPlayerCore: prop, launch effect, placeholder.
# ---------------------------------------------------------------------------
replace_once(
    "src/components/watch/types.ts",
    "export interface FlowPlayerCoreProps {\n"
    "  videoId: string;\n"
    "  videoDetails: VideoDetails | null;\n"
    "  onEnded?: () => void;\n"
    "}\n",
    "export interface FlowPlayerCoreProps {\n"
    "  videoId: string;\n"
    "  videoDetails: VideoDetails | null;\n"
    "  onEnded?: () => void;\n"
    "  /** When true, playback is handed to an external VPU player (Clapper). */\n"
    "  allowExternalPlayer?: boolean;\n"
    "}\n",
    marker="allowExternalPlayer",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    'import { openExternalOrOfferCopy } from "../../lib/openExternal";\n',
    'import { openExternalOrOfferCopy } from "../../lib/openExternal";\n'
    'import { invokeBackend, getBackendErrorMessage } from "../../lib/api/errors";\n',
    marker="getBackendErrorMessage",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    "export function FlowPlayerCore({ videoId, videoDetails, onEnded }: FlowPlayerCoreProps) {",
    "export function FlowPlayerCore({\n"
    "  videoId,\n"
    "  videoDetails,\n"
    "  onEnded,\n"
    "  allowExternalPlayer,\n"
    "}: FlowPlayerCoreProps) {",
    marker="allowExternalPlayer,",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    "  const showToast = useUiStore((s) => s.showToast);\n",
    "  const showToast = useUiStore((s) => s.showToast);\n"
    "  const externalPlayerEnabled =\n"
    "    useAppSettingsStore((s) => s.values[SETTINGS.EXTERNAL_PLAYER_ENABLED] !== \"false\");\n"
    "  const useExternalPlayer = allowExternalPlayer === true && externalPlayerEnabled;\n",
    marker="useExternalPlayer =",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    "  const prefetchedNextForRef = useRef<string | null>(null);\n",
    "  const prefetchedNextForRef = useRef<string | null>(null);\n"
    "  const externalLaunchedForRef = useRef<string | null>(null);\n",
    marker="externalLaunchedForRef",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    "  const handleOpenInBrowser = useCallback(() => {\n"
    "    if (watchUrl) void openExternalOrOfferCopy(watchUrl);\n"
    "  }, [watchUrl]);\n",
    "  const handleOpenInBrowser = useCallback(() => {\n"
    "    if (watchUrl) void openExternalOrOfferCopy(watchUrl);\n"
    "  }, [watchUrl]);\n"
    "\n"
    "  /** Hand this video to the external VPU player (Clapper). WebKit's own\n"
    "   * decoder crashes this board, so the watch surface uses this by default. */\n"
    "  const launchExternalPlayer = useCallback(() => {\n"
    "    if (!videoId) return;\n"
    "    void invokeBackend<void>(\"play_external\", { videoId }).catch((error) => {\n"
    "      showToast({ variant: \"error\", message: getBackendErrorMessage(error) });\n"
    "    });\n"
    "  }, [videoId, showToast]);\n"
    "\n"
    "  useEffect(() => {\n"
    "    if (!useExternalPlayer || !videoId) return;\n"
    "    if (externalLaunchedForRef.current === videoId) return;\n"
    "    externalLaunchedForRef.current = videoId;\n"
    "    launchExternalPlayer();\n"
    "  }, [useExternalPlayer, videoId, launchExternalPlayer]);\n",
    marker="launchExternalPlayer",
)

replace_once(
    "src/components/watch/FlowPlayerCore.tsx",
    "  return (\n    <Player\n      src={stream.streamUrl}",
    "  if (useExternalPlayer) {\n"
    "    return (\n"
    '      <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-black px-6 text-center text-chrome-zinc-100">\n'
    '        <p className="text-sm font-medium sm:text-base">{getString("player_external_placeholder_title")}</p>\n'
    '        <p className="line-clamp-2 max-w-md text-xs text-chrome-zinc-400">{title}</p>\n'
    '        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">\n'
    "          <button\n"
    '            type="button"\n'
    "            onClick={launchExternalPlayer}\n"
    '            className="rounded-full border border-outline-variant px-4 py-1.5 text-xs font-medium text-chrome-zinc-200 transition-colors hover:bg-chrome-white/10"\n'
    "          >\n"
    '            {getString("player_external_reopen")}\n'
    "          </button>\n"
    "          {watchUrl && (\n"
    "            <button\n"
    '              type="button"\n'
    "              onClick={handleOpenInBrowser}\n"
    '              className="rounded-full border border-outline-variant px-4 py-1.5 text-xs font-medium text-chrome-zinc-200 transition-colors hover:bg-chrome-white/10"\n'
    "            >\n"
    '              {getString("player_external_open_browser")}\n'
    "            </button>\n"
    "          )}\n"
    "        </div>\n"
    "      </div>\n"
    "    );\n"
    "  }\n"
    "\n"
    "  return (\n    <Player\n      src={stream.streamUrl}",
    marker="useExternalPlayer) {",
)

# ---------------------------------------------------------------------------
# 7. Main watch surface opts in.
# ---------------------------------------------------------------------------
replace_once(
    "src/components/watch/GlobalVideoPlayer.tsx",
    "<FlowPlayerCore videoId={videoIdForPlayer} videoDetails={cachedDetails} />",
    "<FlowPlayerCore videoId={videoIdForPlayer} videoDetails={cachedDetails} allowExternalPlayer />",
    marker="allowExternalPlayer",
)

print("done")
