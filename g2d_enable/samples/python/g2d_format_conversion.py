#!/home/ukhan/venv_npu/bin/python
"""
g2d_format_conversion.py - G2D ARGB8888 -> YUV420 (NV21) Conversion in Python
=============================================================================
Python equivalent of `g2d_format_conversion.c` using zero-copy DMA-BUF + NumPy
via `sunxi_g2d.py`.
"""

import sys
import time
import numpy as np
from sunxi_g2d import G2DDevice, G2DFormat, G2DColorGamut


def main() -> int:
    width, height = 1920, 1080
    src_size = width * height * 4
    dst_size = width * height * 3 // 2
    src_color = 0xFFFF0000  # Pure Red (R=255, G=0, B=0)

    with G2DDevice() as g2d:
        with (
            g2d.alloc_buffer(src_size, shape=(height, width), dtype=np.uint32) as src_buf,
            g2d.alloc_buffer(dst_size, shape=(dst_size,), dtype=np.uint8) as dst_buf,
        ):
            src_buf.sync_start()
            src_buf.array.fill(src_color)
            src_buf.sync_end()

            dst_buf.sync_start()
            dst_buf.array.fill(0)
            dst_buf.sync_end()

            t0 = time.perf_counter()
            g2d.convert_format(
                src_buf,
                dst_buf,
                width=width,
                height=height,
                src_fmt=G2DFormat.ARGB8888,
                dst_fmt=G2DFormat.YUV420UVC_U1V1U0V0,
                gamut=G2DColorGamut.BT601,
            )
            dt_ms = (time.perf_counter() - t0) * 1000.0

            dst_buf.sync_start()
            y_val = int(dst_buf.array[(height // 2) * width + (width // 2)])
            uv_offset = width * height + (height // 4) * width
            v_val = int(dst_buf.array[uv_offset])
            u_val = int(dst_buf.array[uv_offset + 1])
            dst_buf.sync_end()

            mp_s = (width * height) / (dt_ms * 1000.0)
            print(
                f"[G2D_FORMAT_CONV] 1920x1080 ARGB8888 -> YUV420 NV21: "
                f"{dt_ms:6.2f} ms ({mp_s:6.1f} MP/s)"
            )
            print(f"Sample NV21 values for pure RED: Y={y_val}, V={v_val}, U={u_val}")

            # BT.601 for Pure Red (R=255, G=0, B=0): Y ~ 76..82, V ~ 240..255, U ~ 84..92
            if 65 <= y_val <= 95 and v_val >= 220 and 75 <= u_val <= 105:
                print(" Verification successful: ARGB8888 -> YUV420 NV21 conversion accurate!")
                return 0
            else:
                print(" Verification FAILED: unexpected YUV values!")
                return 1


if __name__ == "__main__":
    sys.exit(main())
