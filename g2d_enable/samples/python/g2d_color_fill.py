#!/home/ukhan/venv_npu/bin/python
"""
g2d_color_fill.py - G2D Solid Rectangle Color Fill Benchmark in Python
======================================================================
Python equivalent of `g2d_color_fill.c` using zero-copy DMA-BUF + NumPy
via `sunxi_g2d.py`.
"""

import sys
import time
import numpy as np
from sunxi_g2d import G2DDevice, G2DFormat


def main() -> int:
    width, height = 1920, 1080
    size_bytes = width * height * 4
    fill_color = 0xFFFF0000  # Opaque Red in ARGB8888

    with G2DDevice() as g2d:
        with g2d.alloc_buffer(size_bytes, shape=(height, width), dtype=np.uint32) as dst_buf:
            dst_buf.sync_start()
            dst_buf.array.fill(0)
            dst_buf.sync_end()

            t0 = time.perf_counter()
            g2d.fill_rect(
                dst_buf,
                width=width,
                height=height,
                color_argb=fill_color,
                rect=(0, 0, width, height),
                fmt=G2DFormat.ARGB8888,
            )
            dt_ms = (time.perf_counter() - t0) * 1000.0

            dst_buf.sync_start()
            ok_full = bool(np.all(dst_buf.array == fill_color))
            sample_val = int(dst_buf.array[height // 2, width // 2])
            dst_buf.sync_end()

            mp_s = (width * height) / (dt_ms * 1000.0)
            print(
                f"[G2D_FILLRECT_H] 1920x1080 ARGB8888 fill (0x{fill_color:08X}): "
                f"{dt_ms:6.2f} ms ({mp_s:6.1f} MP/s)"
            )
            print(f"Sample pixel[540, 960] = 0x{sample_val:08X} | exact match: {ok_full}")
            if not ok_full:
                return 1

            # Also test sub-rectangle ROI fill (400x300 box at (200, 150))
            sub_color = 0xFF00FF00  # Opaque Green
            rx, ry, rw, rh = 200, 150, 400, 300
            g2d.fill_rect(
                dst_buf,
                width=width,
                height=height,
                color_argb=sub_color,
                rect=(rx, ry, rw, rh),
                fmt=G2DFormat.ARGB8888,
            )
            dst_buf.sync_start()
            ok_roi = bool(np.all(dst_buf.array[ry : ry + rh, rx : rx + rw] == sub_color))
            ok_outside = bool(dst_buf.array[0, 0] == fill_color)
            dst_buf.sync_end()
            print(f"[G2D_FILLRECT_H] ROI ({rx},{ry},{rw}x{rh}) fill (0x{sub_color:08X}) | exact match: {ok_roi and ok_outside}")
            if not (ok_roi and ok_outside):
                return 1

    print(" Verification successful: All pixels filled accurately!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
