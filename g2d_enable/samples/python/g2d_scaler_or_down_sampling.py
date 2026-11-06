#!/home/ukhan/venv_npu/bin/python
"""
g2d_scaler_or_down_sampling.py - G2D 4K -> 1080p Downscaling Benchmark in Python
================================================================================
Python equivalent of `g2d_scaler_or_down_sampling.c` using zero-copy DMA-BUF + NumPy
via `sunxi_g2d.py`.
"""

import sys
import time
import numpy as np
from sunxi_g2d import G2DDevice, G2DFormat


def main() -> int:
    src_w, src_h = 4096, 4096
    dst_w, dst_h = 1920, 1080
    src_size = src_w * src_h * 4
    dst_size = dst_w * dst_h * 4

    with G2DDevice() as g2d:
        with (
            g2d.alloc_buffer(src_size, shape=(src_h, src_w), dtype=np.uint32) as src_buf,
            g2d.alloc_buffer(dst_size, shape=(dst_h, dst_w), dtype=np.uint32) as dst_buf,
        ):
            # Populate 4096x4096 source buffer with 4 colored quadrants:
            # Top-Left: Red (0xFFFF0000), Top-Right: Green (0xFF00FF00)
            # Bottom-Left: Blue (0xFF0000FF), Bottom-Right: White (0xFFFFFFFF)
            src_buf.sync_start()
            src_buf.array[: src_h // 2, : src_w // 2] = 0xFFFF0000
            src_buf.array[: src_h // 2, src_w // 2 :] = 0xFF00FF00
            src_buf.array[src_h // 2 :, : src_w // 2] = 0xFF0000FF
            src_buf.array[src_h // 2 :, src_w // 2 :] = 0xFFFFFFFF
            src_buf.sync_end()

            dst_buf.sync_start()
            dst_buf.array.fill(0)
            dst_buf.sync_end()

            t0 = time.perf_counter()
            g2d.scale(
                src_buf,
                src_w=src_w,
                src_h=src_h,
                dst_buf=dst_buf,
                dst_w=dst_w,
                dst_h=dst_h,
                fmt=G2DFormat.ARGB8888,
            )
            dt_ms = (time.perf_counter() - t0) * 1000.0

            dst_buf.sync_start()
            tl = int(dst_buf.array[dst_h // 4, dst_w // 4])
            tr = int(dst_buf.array[dst_h // 4, (dst_w * 3) // 4])
            bl = int(dst_buf.array[(dst_h * 3) // 4, dst_w // 4])
            br = int(dst_buf.array[(dst_h * 3) // 4, (dst_w * 3) // 4])
            dst_buf.sync_end()

            src_mp_s = (src_w * src_h) / (dt_ms * 1000.0)
            print(
                f"[G2D_SCALER] 4096x4096 -> 1920x1080 ARGB8888: "
                f"{dt_ms:6.2f} ms ({src_mp_s:6.1f} MP/s input rate)"
            )
            print(
                f"Quadrants: TL=0x{tl:08X}, TR=0x{tr:08X}, BL=0x{bl:08X}, BR=0x{br:08X}"
            )

            if (
                tl == 0xFFFF0000
                and tr == 0xFF00FF00
                and bl == 0xFF0000FF
                and br == 0xFFFFFFFF
            ):
                print(" Verification successful: 4096x4096 -> 1920x1080 downscaling accurate!")
                return 0
            else:
                print(" Verification FAILED: unexpected quadrant pixel values!")
                return 1


if __name__ == "__main__":
    sys.exit(main())
