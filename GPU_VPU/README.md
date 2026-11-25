# Ensure GPU & VPU Support
```
OS: Ubuntu 22.04.5 LTS aarch64 
Host: sun55iw3 
Kernel: 5.15.147-sun55iw3 
Uptime: 5 hours, 2 mins 
Packages: 2737 (dpkg), 25 (flatpak) 
Shell: bash 5.1.16 
Resolution: 1920x1080 
DE: GNOME 42.9 (Wayland) 
Theme: Yaru-dark [GTK2/3] 
Icons: Yaru [GTK2/3] 
Terminal: gnome-terminal 
CPU: Cortex-A55 (8) @ 1.416GHz 
GPU: Mali-G57 (Panfrost) 
Memory: 2818MiB / 3840MiB 
```
## Hardware VPU Drivers Check
```
$ sudo dmesg | grep cedar
[ 9138.577451] sunxi:VE:[INFO]: 912 enable_cedar_hw_clk(): 
[ 9138.578305] sunxi:VE:[INFO]: 954 disable_cedar_hw_clk(): 
[ 9138.578478] sunxi:VE:[INFO]: 912 enable_cedar_hw_clk(): 
[ 9291.838428] sunxi:VE:[INFO]: 954 disable_cedar_hw_clk(): 
[ 9444.989250] sunxi:VE:[INFO]: 912 enable_cedar_hw_clk(): 
[ 9444.990216] sunxi:VE:[INFO]: 954 disable_cedar_hw_clk(): 
[ 9444.990394] sunxi:VE:[INFO]: 912 enable_cedar_hw_clk(): 
[13326.578046] sunxi:VE:[WARN]: 2217 cedardev_release(): release lost-lock...
```
## Github Links
- GPU VPU configuration files, must be present in your OS https://github.com/orangepi-xunlong/orangepi-build/tree/next/external/packages/bsp/t527/etc
- **IMPORTANT** Prebuilt *.deb files for GPU & VPU https://github.com/orangepi-xunlong/rk-rootfs-build/tree/t527_packages/jammy
For VPU the most important packages are `gstreamer1.0-omx.deb` & `libcedarc_1.0_arm64.deb` refer to this discussion https://github.com/orangepi-xunlong/orangepi-build/issues/244
## VPU Codecs Support
HDR files are not supported as well as HEVC 10bit

Required packages ~`sudo apt-get install gstreamer1.0 gstreamer1.0-tools`~ You can install additional codecs `sudo apt install gstreamer1.0-plugins-{base,good,bad}` but **never** install `*-omx-generic*` packages
```
$ gst-inspect-1.0 | grep omx
libav:  avenc_h264_omx: libav OpenMAX IL H.264 video encoder encoder
libav:  avenc_mpeg4_omx: libav OpenMAX IL MPEG-4 video encoder encoder
omx:  omxavsvideodec: OpenMAX AVS Video Decoder
omx:  omxh263videodec: OpenMAX H.263 Video Decoder
omx:  omxh264dec: OpenMAX H.264 Video Decoder
omx:  omxhevcvideodec: OpenMAX H.265 Video Decoder
omx:  omxmjpegvideodec: OpenMAX MJPEG Video Decoder
omx:  omxmpeg1videodec: OpenMAX MPEG1 Video Decoder
omx:  omxmpeg2videodec: OpenMAX MPEG2 Video Decoder
omx:  omxmpeg4videodec: OpenMAX MPEG4 Video Decoder
omx:  omxvp8videodec: OpenMAX VP8 Video Decoder
omx:  omxvp9videodec: OpenMAX VP9 Video Decoder
```
## Gstreamer HW-accelerated Video Players
Video information can be retrieved via `gst-discoverer-1.0 <video>`
- Command line player with very absolutely no GUI is `gst123` More about its usage [read here](https://www.systutorials.com/docs/linux/man/1-gst123/)
- Clapper a headache to build can be installed via this [ppa](https://launchpad.net/~liujianfeng1994/+archive/ubuntu/rockchip-multimedia/)
At its launch navigate _Preferences>Tweaks>Plugin Ranking_ Scroll down to _omx_ & enable all; a default ranking of 257 will be shown. Restart Clapper

> **Ubuntu 26.04 / kernel 6.18.44:** the Clapper PPA above is the 22.04 / 5.15 route. On the current 26.04 image, install `clapper` from the `universe` archive and follow [`falkon_clapper/README.md`](./falkon_clapper/README.md) for the Falkon → Clapper single-window Cedar handoff, including the `omxavsvideodec` plugin-ranking step.
- `totem` is another good choice, available in default repos
- Currently unable to build [Glide](https://github.com/philn/glide/issues/134)
- `parole` player gave me _Segmentation fault_ when installed from official repos. I was able to build & run it via
```
git clone https://gitlab.xfce.org/apps/parole
cd parole
sudo apt install libdbus-glib-1-dev libxfce4ui-2-dev librga-dev libtagc0-dev libnotify-dev
meson setup build --reconfigure
meson compile -C build
meson install -C build
```
Navigate to _Preferences>Display_ & choose _X11/XShm/Xv_ After restart of `parole` it uses HW-acceleration but video windows is separated from main GUI?? It has no wayland support yet I believe

If video player is using hardware acceleration you can check it by `sudo journalctl -f | grep cedar`

## Falkon → Clapper single-window VPU handoff (Ubuntu 26.04 / kernel 6.18.44)

[`falkon_clapper/`](./falkon_clapper) contains a Falkon 25.12.3 GreaseMonkey
userscript plus a `clapper://` handler that sends YouTube `/watch` and `/shorts`
pages to **one** Clapper window for Cedar VPU playback.

- Validated on **Ubuntu 26.04 LTS (Resolute Raccoon) aarch64**, Kubuntu/Plasma 6,
  kernel **`6.18.44-g61025ec85b88`**, with Clapper 0.8.0, GStreamer 1.28.2,
  vendor `gst-omx` 1.20.1, `libcedarc` 1.0, and Falkon 25.12.3.
- Requires the 26.04 Clapper/GStreamer/gst-omx/libcedarc stack; it does **not**
  use the jammy (22.04) debs listed above.
- Clapper must have the VPU decoder selected via
  _Preferences → Tweaks → Plugin ranking_, and Falkon's **GreaseMonkey**
  extension must be enabled. Both are covered in
  [`falkon_clapper/README.md`](./falkon_clapper/README.md), which also lists the
  exact packages, `/dev/cedar_dev` checks, install/verify steps, and the
  single-instance design (`clapper <watch-url>` with no `--new-window`).

The YouTube tab stays open; Clapper reuses its active window and replaces the
current video instead of starting a second player.

