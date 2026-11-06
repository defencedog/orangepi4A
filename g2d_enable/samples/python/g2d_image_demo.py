#!/home/ukhan/venv_npu/bin/python
"""
g2d_image_demo.py - Real Image Processing Pipeline via Python + G2D (/dev/g2d)
==============================================================================
Loads `../assets/dummy_input.jpg` (512x480) using Pillow (`PIL.Image`) and runs
hardware-accelerated 2D graphics operations via `sunxi_g2d.py`:

  1. 90° Clockwise Rotation (`G2D_ROT_90` -> 480x512)
  2. 180° Rotation (`G2D_ROT_180` -> 512x480)
  3. Horizontal Flip / Mirror (`G2D_ROT_H` -> 512x480)
  4. Solid Color Fill Overlay (`G2D_CMD_FILLRECT_H` HUD banner on image)
  5. 2x Downscaling (`512x480 -> 256x240`)
  6. Color Space Conversion (`ARGB8888 -> YUV420 NV21` + RGB reconstruction)

Saves all output PNG images to `../assets/output_python/`.
"""

import os
import sys
import time
import numpy as np
from PIL import Image
from sunxi_g2d import G2DDevice, G2DFormat


def rgb_to_bgra_bytes(rgb_arr: np.ndarray) -> np.ndarray:
    """
    Convert HxWx3 RGB uint8 array to HxWx4 little-endian ARGB8888 (i.e. BGRA byte order).
    In little-endian `0xAARRGGBB`, byte 0 is B, byte 1 is G, byte 2 is R, byte 3 is A.
    """
    h, w, _ = rgb_arr.shape
    bgra = np.empty((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = rgb_arr[:, :, 2]  # B
    bgra[:, :, 1] = rgb_arr[:, :, 1]  # G
    bgra[:, :, 2] = rgb_arr[:, :, 0]  # R
    bgra[:, :, 3] = 255               # A
    return bgra


def bgra_bytes_to_rgb(bgra_arr: np.ndarray) -> np.ndarray:
    """Convert HxWx4 little-endian ARGB8888 (BGRA bytes) back to HxWx3 RGB uint8."""
    rgb = np.empty((bgra_arr.shape[0], bgra_arr.shape[1], 3), dtype=np.uint8)
    rgb[:, :, 0] = bgra_arr[:, :, 2]  # R
    rgb[:, :, 1] = bgra_arr[:, :, 1]  # G
    rgb[:, :, 2] = bgra_arr[:, :, 0]  # B
    return rgb


def nv21_to_rgb(nv21_flat: np.ndarray, width: int, height: int) -> np.ndarray:
    """Reconstruct HxWx3 RGB uint8 image from a YUV420 NV21 buffer (Y + interleaved V,U)."""
    y_plane = nv21_flat[: width * height].reshape((height, width)).astype(np.int32)
    vu_plane = nv21_flat[width * height :].reshape((height // 2, width // 2, 2)).astype(np.int32)

    v_up = np.repeat(np.repeat(vu_plane[:, :, 0], 2, axis=0), 2, axis=1) - 128
    u_up = np.repeat(np.repeat(vu_plane[:, :, 1], 2, axis=0), 2, axis=1) - 128

    r = np.clip(y_plane + ((359 * v_up) >> 8), 0, 255).astype(np.uint8)
    g = np.clip(y_plane - ((88 * u_up + 183 * v_up) >> 8), 0, 255).astype(np.uint8)
    b = np.clip(y_plane + ((454 * u_up) >> 8), 0, 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(script_dir, "..", "assets", "dummy_input.jpg")
    )
    out_dir = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(script_dir, "..", "assets", "output_python")
    )
    os.makedirs(out_dir, exist_ok=True)

    img = Image.open(input_path).convert("RGB")
    w, h = img.size
    rgb_in = np.asarray(img, dtype=np.uint8)
    print("=================================================================")
    print("  Orange Pi 4A (Allwinner T527) Python G2D Image Pipeline Demo")
    print(f"  Input Image: {input_path} ({w}x{h})")
    print(f"  Output Dir:  {out_dir}")
    print("=================================================================")

    with G2DDevice() as g2d:
        with (
            g2d.alloc_image_buffer(w, h, G2DFormat.ARGB8888) as src_buf,
            g2d.alloc_image_buffer(h, w, G2DFormat.ARGB8888) as rot90_buf,
            g2d.alloc_image_buffer(w, h, G2DFormat.ARGB8888) as same_buf,
            g2d.alloc_image_buffer(w // 2, h // 2, G2DFormat.ARGB8888) as scale_buf,
            g2d.alloc_image_buffer(w, h, G2DFormat.YUV420UVC_U1V1U0V0) as nv21_buf,
        ):
            # Copy input image into zero-copy DMA-BUF
            src_buf.sync_start()
            src_buf.array[:, :, :] = rgb_to_bgra_bytes(rgb_in)
            src_buf.sync_end()

            # 1. 90° Clockwise Rotation (G2D_ROT_90)
            t0 = time.perf_counter()
            g2d.rotate(src_buf, rot90_buf, w, h, angle=90, fmt=G2DFormat.ARGB8888)
            t_rot90 = (time.perf_counter() - t0) * 1000.0
            rot90_buf.sync_start()
            out_rot90 = os.path.join(out_dir, "py_output_rotated_90.png")
            Image.fromarray(bgra_bytes_to_rgb(rot90_buf.array)).save(out_rot90)
            rot90_buf.sync_end()
            print(f"[1/6] G2D_ROT_90 ({w}x{h} -> {h}x{w}):         {t_rot90:6.2f} ms -> {out_rot90}")

            # 2. 180° Rotation (G2D_ROT_180)
            t0 = time.perf_counter()
            g2d.rotate(src_buf, same_buf, w, h, angle=180, fmt=G2DFormat.ARGB8888)
            t_rot180 = (time.perf_counter() - t0) * 1000.0
            same_buf.sync_start()
            out_rot180 = os.path.join(out_dir, "py_output_rotated_180.png")
            Image.fromarray(bgra_bytes_to_rgb(same_buf.array)).save(out_rot180)
            same_buf.sync_end()
            print(f"[2/6] G2D_ROT_180 ({w}x{h} -> {w}x{h}):        {t_rot180:6.2f} ms -> {out_rot180}")

            # 3. Horizontal Mirror / Flip (G2D_ROT_H)
            t0 = time.perf_counter()
            g2d.flip(src_buf, same_buf, w, h, horizontal=True, fmt=G2DFormat.ARGB8888)
            t_flip = (time.perf_counter() - t0) * 1000.0
            same_buf.sync_start()
            out_flip = os.path.join(out_dir, "py_output_flipped_h.png")
            Image.fromarray(bgra_bytes_to_rgb(same_buf.array)).save(out_flip)
            same_buf.sync_end()
            print(f"[3/6] G2D_ROT_H ({w}x{h} -> {w}x{h}):          {t_flip:6.2f} ms -> {out_flip}")

            # 4. Color Fill Overlay (G2D_CMD_FILLRECT_H)
            same_buf.sync_start()
            same_buf.array[:, :, :] = src_buf.array[:, :, :]
            same_buf.sync_end()
            t0 = time.perf_counter()
            g2d.fill_rect(
                same_buf,
                width=w,
                height=h,
                color_argb=0xFF1E90FF,  # DodgerBlue rectangle overlay
                rect=(w // 8, h // 8, w // 4, h // 4),
                fmt=G2DFormat.ARGB8888,
            )
            t_fill = (time.perf_counter() - t0) * 1000.0
            same_buf.sync_start()
            out_fill = os.path.join(out_dir, "py_output_color_fill.png")
            Image.fromarray(bgra_bytes_to_rgb(same_buf.array)).save(out_fill)
            same_buf.sync_end()
            print(f"[4/6] G2D_CMD_FILLRECT_H (ROI box fill):    {t_fill:6.2f} ms -> {out_fill}")

            # 5. 2x Downscale (512x480 -> 256x240)
            t0 = time.perf_counter()
            g2d.scale(src_buf, w, h, scale_buf, w // 2, h // 2, fmt=G2DFormat.ARGB8888)
            t_scale = (time.perf_counter() - t0) * 1000.0
            scale_buf.sync_start()
            out_scale = os.path.join(out_dir, "py_output_scaled_256x240.png")
            Image.fromarray(bgra_bytes_to_rgb(scale_buf.array)).save(out_scale)
            scale_buf.sync_end()
            print(f"[5/6] G2D Downscale ({w}x{h} -> {w//2}x{h//2}):    {t_scale:6.2f} ms -> {out_scale}")

            # 6. Format Conversion (ARGB8888 -> YUV420 NV21)
            t0 = time.perf_counter()
            g2d.convert_format(
                src_buf,
                nv21_buf,
                width=w,
                height=h,
                src_fmt=G2DFormat.ARGB8888,
                dst_fmt=G2DFormat.YUV420UVC_U1V1U0V0,
            )
            t_csc = (time.perf_counter() - t0) * 1000.0
            nv21_buf.sync_start()
            out_nv21 = os.path.join(out_dir, "py_output_nv21_reconstructed.png")
            Image.fromarray(nv21_to_rgb(nv21_buf.array, w, h)).save(out_nv21)
            nv21_buf.sync_end()
            print(f"[6/6] G2D ARGB8888 -> YUV420 NV21:          {t_csc:6.2f} ms -> {out_nv21}")

    print("=================================================================")
    print("  All 6 Python G2D image operations completed & saved!")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
