#!/usr/bin/env python3
"""Apply the Flow-Desktop cedar/VPU patches on the build host."""
from pathlib import Path
import sys

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/builds/Flow-Desktop")


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}:\n{old[:300]}")
    if text.count(old) != 1:
        raise SystemExit(f"pattern is not unique in {path} ({text.count(old)} matches)")
    path.write_text(text.replace(old, new, 1))
    print(f"patched {path}")


video = repo / "src/lib/useVideoStream.ts"
schema = repo / "src/lib/settings/schema.ts"
quality_tab = repo / "src/components/settings/tabs/QualityTab.tsx"
main_rs = repo / "src-tauri/src/main.rs"
desktop = repo / "src-tauri/linux/flow.desktop"

# 1. Remove the now-unused MSE capability probe.
replace(
    video,
    '''const browserSupportsDash = (info: StreamInfo) =>
  typeof MediaSource !== "undefined" &&
  typeof MediaSource.isTypeSupported === "function" &&
  info.variants.some((variant) => !!variant.mimeType && MediaSource.isTypeSupported(variant.mimeType)) &&
  info.audioTracks.some((track) => !!track.mimeType && MediaSource.isTypeSupported(track.mimeType));

''',
    "",
)

# 2. Prefer progressive direct playback for VOD; MSE paths fail with cedar OMX.
replace(
    video,
    '''const computeAvailableSourceModes = (info: StreamInfo): SourceMode[] => {
  const modes: SourceMode[] = [];
  const isLive = !!info.isLive;

  if (isLive && info.hlsManifestUrl) modes.push("hls");
  if (info.dashManifestUrl && browserSupportsDash(info)) modes.push("dash-native");
  if (!isLive) {
    const canUseAdaptive = (info.audioTracks || []).some((track) => !!track.localUrl);
    const hasDirect =
      (info.variants || []).some((v) => v.isPlayable && (v.hasAudio || canUseAdaptive)) || !!info.localUrl;
    if (hasDirect) modes.push("direct");
    if (info.sabr?.available && info.sabr?.manifestUrl) modes.push("sabr-dash");
  }
  if (info.hlsManifestUrl && !modes.includes("hls")) modes.push("hls");
  if (isLive && info.dashManifestUrl && !modes.includes("dash-native")) modes.push("dash-native");
  return modes;
};''',
    '''const computeAvailableSourceModes = (info: StreamInfo): SourceMode[] => {
  const modes: SourceMode[] = [];
  const isLive = !!info.isLive;

  if (isLive && info.hlsManifestUrl) modes.push("hls");
  if (!isLive) {
    // Flow-VPU: progressive direct playback is the only VOD path that reaches
    // cedar's omxh264dec. WebKit's MSE pipeline fails against this OMX
    // component with OMX_ErrorNotImplemented, so dash-native and SABR-DASH are
    // deliberately not offered in this build.
    const canUseAdaptive = (info.audioTracks || []).some((track) => !!track.localUrl);
    const hasDirect =
      (info.variants || []).some((v) => v.isPlayable && (v.hasAudio || canUseAdaptive)) || !!info.localUrl;
    if (hasDirect) modes.push("direct");
  }
  if (info.hlsManifestUrl && !modes.includes("hls")) modes.push("hls");
  if (isLive && info.dashManifestUrl && !modes.includes("dash-native")) modes.push("dash-native");
  return modes;
};''',
)

# 3. Default quality 720p (the target board's reliable cedar ceiling).
replace(
    schema,
    'str(SETTINGS.DEFAULT_QUALITY_WIFI, "quality", "1080p", "wired", QUALITY_VALUES),',
    'str(SETTINGS.DEFAULT_QUALITY_WIFI, "quality", "720p", "wired", QUALITY_VALUES),',
)
replace(
    video,
    's.values[SETTINGS.DEFAULT_QUALITY_WIFI] ?? "1080p"',
    's.values[SETTINGS.DEFAULT_QUALITY_WIFI] ?? "720p"',
)
replace(
    quality_tab,
    "usePreference(SETTINGS.DEFAULT_QUALITY_WIFI, '1080p')",
    "usePreference(SETTINGS.DEFAULT_QUALITY_WIFI, '720p')",
)

# 4. Set the GStreamer rank before WebKit/GStreamer initialize.
replace(
    main_rs,
    '''fn main() {
    flow_desktop_lib::run()
}''',
    '''fn main() {
    #[cfg(target_os = "linux")]
    {
        // Prefer cedar's OMX decoders over software decoders for every
        // GStreamer pipeline WebKit creates. The packaged .desktop file
        // exports the same ranking, but this also covers terminal launches.
        unsafe {
            std::env::set_var(
                "GST_PLUGIN_FEATURE_RANK",
                "omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257",
            );
        }
    }
    flow_desktop_lib::run()
}''',
)

# 5. Export the same ranking for desktop launches.
replace(
    desktop,
    "Exec={{exec}}",
    "Exec=env GST_PLUGIN_FEATURE_RANK=omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257 {{exec}}",
)

# 6. Local packaging override.
override = repo / "src-tauri/tauri.vpu.conf.json"
override.write_text(
    '''{
  "$schema": "https://schema.tauri.app/config/2",
  "bundle": {
    "createUpdaterArtifacts": false,
    "targets": ["deb"],
    "linux": {
      "deb": {
        "depends": [
          "gstreamer1.0-plugins-base",
          "gstreamer1.0-plugins-good",
          "gstreamer1.0-plugins-bad",
          "gstreamer1.0-libav",
          "gstreamer1.0-gl",
          "libcedarc"
        ]
      }
    }
  }
}
'''
)
print(f"wrote {override}")
print("all Flow-VPU patches applied")
