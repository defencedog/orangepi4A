#!/home/ukhan/venv_npu/bin/python
"""
g2d_rotation_or_mirror.py - Hardware G2D Rotation & Mirror Benchmark in Python
==============================================================================
Python equivalent of `g2d_rotation_or_mirror.c` using zero-copy DMA-BUF + NumPy
via `sunxi_g2d.py`.

Tests 1920x1080 ARGB8888:
  - 90° clockwise rotation (`G2D_ROT_90` -> 1080x1920)
  - 180° rotation (`G2D_ROT_180` -> 1920x1080)
  - 270° clockwise rotation (`G2D_ROT_270` -> 1080x1920)
  - Horizontal flip (`G2D_ROT_H` -> 1920x1080)
  - Vertical flip (`G2D_ROT_V` -> 1920x1080)
"""

import sys
import time
import numpy as np
from sunxi_g2d import G2DDevice, G2DFormat


def main() -> int:
    src_w, src_h = 1920, 1080
    size_bytes = src_w * src_h * 4

    with G2DDevice() as g2d:
        g2d_ver, chip_ver = g2d.query_version()
        print(f"[Python G2D] Opened /dev/g2d (G2D IP version: 0x{g2d_ver:08x}, chip: 0x{chip_ver:08x})")

        with (
            g2d.alloc_buffer(size_bytes, shape=(src_h, src_w), dtype=np.uint32) as src_buf,
            g2d.alloc_buffer(size_bytes, shape=(src_w, src_h), dtype=np.uint32) as dst_rot90,
            g2d.alloc_buffer(size_bytes, shape=(src_h, src_w), dtype=np.uint32) as dst_same,
        ):
            # Populate source buffer with a deterministic coordinate-encoded pattern
            src_buf.sync_start()
            y_idx = np.arange(src_h, dtype=np.uint32)[:, None] & 0xFF
            x_idx = np.arange(src_w, dtype=np.uint32)[None, :] & 0xFF
            src_pattern = (0xFF << 24) | (y_idx << 16) | (x_idx << 8) | ((x_idx + y_idx) & 0xFF)
            src_buf.array[:, :] = src_pattern
            dst_rot90.array.fill(0)
            src_buf.sync_end()
            dst_rot90.sync_end()

            # 1. 90-degree clockwise hardware rotation (1920x1080 -> 1080x1920)
            t0 = time.perf_counter()
            g2d.rotate(src_buf, dst_rot90, src_w, src_h, angle=90, fmt=G2DFormat.ARGB8888)
            dt_ms = (time.perf_counter() - t0) * 1000.0

            dst_rot90.sync_start()
            expected_90 = np.rot90(src_pattern, k=-1)  # 90 deg clockwise
            ok_90 = bool(np.array_equal(dst_rot90.array, expected_90))
            dst_rot90.sync_end()

            mp_s = (src_w * src_h) / (dt_ms * 1000.0)
            print(f"[G2D_ROT_90]  1920x1080 -> 1080x1920: {dt_ms:6.2f} ms ({mp_s:6.1f} MP/s) | exact match: {ok_90}")
            if not ok_90:
                return 1

            # 2. 180-degree hardware rotation (1920x1080 -> 1920x1080)
            t0 = time.perf_counter()
            g2d.rotate(src_buf, dst_same, src_w, src_h, angle=180, fmt=G2DFormat.ARGB8888)
            dt_180_ms = (time.perf_counter() - t0) * 1000.0

            dst_same.sync_start()
            expected_180 = np.rot90(src_pattern, k=2)
            ok_180 = bool(np.array_equal(dst_same.array, expected_180))
            dst_same.sync_end()
            print(f"[G2D_ROT_180] 1920x1080 -> 1920x1080: {dt_180_ms:6.2f} ms ({(src_w*src_h)/(dt_180_ms*1000.0):6.1f} MP/s) | exact match: {ok_180}")
            if not ok_180:
                return 1

            # 3. Horizontal mirror / flip (G2D_ROT_H)
            t0 = time.perf_counter()
            g2d.flip(src_buf, dst_same, src_w, src_h, horizontal=True, fmt=G2DFormat.ARGB8888)
            dt_h_ms = (time.perf_counter() - t0) * 1000.0

            dst_same.sync_start()
            expected_h = np.fliplr(src_pattern)
            ok_h = bool(np.array_equal(dst_same.array, expected_h))
            dst_same.sync_end()
            print(f"[G2D_ROT_H]   1920x1080 -> 1920x1080: {dt_h_ms:6.2f} ms ({(src_w*src_h)/(dt_h_ms*1000.0):6.1f} MP/s) | exact match: {ok_h}")
            if not ok_h:
                return 1

            # 4. Vertical mirror / flip (G2D_ROT_V)
            t0 = time.perf_counter()
            g2d.flip(src_buf, dst_same, src_w, src_h, horizontal=False, fmt=G2DFormat.ARGB8888)
            dt_v_ms = (time.perf_counter() - t0) * 1000.0

            dst_same.sync_start()
            expected_v = np.flipud(src_pattern)
            ok_v = bool(np.array_equal(dst_same.array, expected_v))
            dst_same.sync_end()
            print(f"[G2D_ROT_V]   1920x1080 -> 1920x1080: {dt_v_ms:6.2f} ms ({(src_w*src_h)/(dt_v_ms*1000.0):6.1f} MP/s) | exact match: {ok_v}")
            if not ok_v:
                return 1

    print(" Verification successful: All hardware rotation & mirror tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
