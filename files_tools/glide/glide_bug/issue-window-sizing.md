<!--
Suggested GitHub issue title:
Window grows to the video's native size and spills off-screen in windowed mode (Wayland)
-->

## Summary

In windowed mode Glide resizes its window to the video's **native pixel size**
when a file is opened. On a display smaller than the video (e.g. 1280×720 with
a 1080p file) the window becomes larger than the screen. On Wayland a client
cannot move its own toplevel, so the window keeps its top-left anchor and its
right/bottom part ends up off-screen; the user has to drag it back every time.
Fullscreen (`F`) is not affected.

## Environment

- Glide **0.6.9**, upstream commit `d6ed2e8`, built from source
  (`--features wayland,dmabuf`)
- GTK **4.22.4**, libadwaita **1.9.1**, GStreamer **1.28.2**
- KDE Plasma 6 / KWin, **Wayland** session
- Display **1280×720**, scale 1
- Tested on aarch64 (OrangePi 4A); the code involved is architecture-independent
- Also reproduced with GTK 4.14 / libadwaita 1.5 (noble sysroot used to build it)

## Steps to reproduce

1. Use a Wayland session with a display smaller than the test video
   (1280×720 here).
2. Launch Glide and open a 720p or 1080p video, e.g.
   `bigbuckbunny-1080p.mp4` (1920×1080).
3. Let it play in **windowed** mode (do not press `F`).

## Actual behaviour

- The initial window is centred.
- As soon as the video dimensions are known, the window is enlarged to the
  video's native size (plus the header bar), anchored at its **top-left**
  corner.
- A 1080p video on this 1280×720 desktop therefore extends past the right edge;
  about half of the window is off-screen until it is dragged left.

## Expected behaviour

The window should stay fully visible and centred. Two reasonable behaviours:

1. the window is not resized to the video and the video is scaled
   (letterboxed) into the existing window, or
2. if the window is resized, it is re-centred / clamped to the work area so a
   part never goes off-screen.

## Root cause

`UIContext::resize_video_renderer()` (`src/ui_context.rs:515` in v0.6.9):

```rust
pub fn resize_video_renderer(&self, width: u32, height: u32) {
    self.video_renderer.set_size_request(width as i32, height as i32);
}
```

It is called from `VideoPlayer::video_dimensions_changed()` (`src/main.rs:656`)
on every `PlayMessage::VideoDimensionsChanged`. Setting the `GtkPicture`'s
**size request** to the video resolution sets its minimum size, so the parent
`GtkWindow` is forced to grow.

The window has already been mapped at this point (`connect_open` calls
`app.activate()`, which calls `present()`, before the file is loaded), so this
is a resize of an existing toplevel, not an initial placement. On Wayland
`xdg-shell` intentionally has no API to position a toplevel, so the compositor
keeps the top-left anchor and the client cannot re-centre it.

Clamping the requested size to the monitor is **not sufficient**: the window may
have been centred at `x = (1280 - 640) / 2 = 320`, so even a width clamped to
1280 would put the right edge at 1600.

## Proposed fix

Do not derive the window size from the video. Give the window a sensible
monitor-relative default size before it is presented, and let the `GtkPicture`
scale the video with `content-fit = contain`:

- `UIContext::new()`: set `window.set_default_size(...)` to ~90 % of the monitor
  geometry (before `present()`; the compositor centres the initial placement).
- `resize_video_renderer()`: clear the picture size request and enable
  `hexpand`/`vexpand` + `content-fit = contain` instead of resizing the window.

This makes windowed playback behave like other Wayland-native players: the
window size is independent of the video's native resolution, and it never moves
or overflows. `F` fullscreen is unchanged.

The 90 % / minimum 640×360 default is only a suggestion — any screen-fitting
default (or a remembered window size) works.

<details>
<summary>Patch (applies to <code>d6ed2e8</code> / v0.6.9)</summary>

```diff
diff --git a/src/ui_context.rs b/src/ui_context.rs
index 075484f..b540b70 100644
--- a/src/ui_context.rs
+++ b/src/ui_context.rs
@@ -134,6 +134,19 @@ impl UIContext {
 
         let window: adw::ApplicationWindow = builder.object("application-window").unwrap();
 
+        // Give the window a monitor-relative default size. The video is scaled
+        // into the window instead of growing it (see resize_video_renderer),
+        // so the initial compositor placement (centred) is kept forever.
+        if let Some(monitor) = gdk::Display::default()
+            .and_then(|display| display.monitors().item(0))
+            .and_then(|obj| obj.downcast::<gdk::Monitor>().ok())
+        {
+            let geo = monitor.geometry();
+            let width = ((geo.width() as f64) * 0.9).round() as i32;
+            let height = ((geo.height() as f64) * 0.9).round() as i32;
+            window.set_default_size(width.max(640), height.max(360));
+        }
+
         let track_synchronization_window: adw::ApplicationWindow = builder.object("synchronization-window").unwrap();
 
         let action = gio::SimpleAction::new("close", None);
@@ -512,8 +525,16 @@ impl UIContext {
         self.video_renderer.set_paintable(Some(paintable));
     }
 
-    pub fn resize_video_renderer(&self, width: u32, height: u32) {
-        self.video_renderer.set_size_request(width as i32, height as i32);
+    pub fn resize_video_renderer(&self, _width: u32, _height: u32) {
+        // Do not resize the window to the video's native resolution. On
+        // Wayland a client cannot reposition its toplevel, so growing the
+        // window anchors it at the top-left and can push it off-screen (e.g.
+        // 1080p on a 1280x720 desktop). Keep the window size and let the
+        // GtkPicture scale the video to fit (`content-fit = contain`).
+        self.video_renderer.set_size_request(-1, -1);
+        self.video_renderer.set_hexpand(true);
+        self.video_renderer.set_vexpand(true);
+        self.video_renderer.set_content_fit(gtk::ContentFit::Contain);
     }
 
     pub fn set_window_title(&self, title: &str) {
```

</details>

## Alternatives considered

- **Clamp the size request to the monitor.** Not enough on Wayland (see above):
  a non-zero top-left anchor still pushes the right edge off-screen.
- **Hide → resize → show.** Forces the compositor to re-place the window, but
  causes a visible flicker, can lose focus/fullscreen state, and is surprising
  for a playback resize.
- **Maximise when the video does not fit.** Guarantees on-screen, but silently
  changes the window state; users may not want maximised playback.
- **Compositor-specific positioning (KWin scripting, X11
  `_NET_MOVERESIZE_WINDOW`).** Not portable across Wayland compositors.

## Testing

Tested on aarch64 / KDE Wayland / 1280×720:

- 720p and 1080p HEVC both play in a centred **1152×648** window
  (90 % of the monitor) with black pillarbox bars; the window does not move or
  overflow while playing.
- `F` fullscreen still works.
- `git apply --check` of the attached patch against a pristine `d6ed2e8` tree
  passes.