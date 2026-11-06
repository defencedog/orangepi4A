#!/home/ukhan/venv_npu/bin/python
"""
sunxi_g2d.py - Pure-Python Zero-Copy Wrapper for Allwinner G2D (/dev/g2d)
==========================================================================
Target Board: Orange Pi 4A (Allwinner T527 / sun55iw3)
Kernel:       Mainline Linux 6.18.44 (sunxi_g2d.ko, g2d_legacy V2X)
Reference:    https://docs.radxa.com/en/cubie/a7s/app-dev/npu-dev/g2d-usage-guide

Provides:
  - Zero-copy DMA-BUF allocation via /dev/dma_heap/system with direct
    mmap + NumPy ndarray views (`DmaBuffer`)
  - Cache-coherency synchronization (`DMA_BUF_IOCTL_SYNC`)
  - Full ctypes definitions for `sunxi-g2d.h` (`G2DImageEnh`, `G2DBltH`,
    `G2DFillRectH`, `G2DHardwareVersion`) verified against aarch64 ABI
  - High-level Pythonic API (`G2DDevice`) for hardware rotation (90/180/270/0),
    mirror/flip (H/V), solid rectangle color fill, image scaling/resizing,
    and ARGB8888 <-> YUV420 (NV21/NV12) format conversion.
"""

from __future__ import annotations

import ctypes
import enum
import fcntl
import mmap
import os
from typing import Optional, Tuple, Union

import numpy as np

# ---------------------------------------------------------------------------
# Linux DMA-Heap & DMA-BUF ioctl definitions (aarch64)
# ---------------------------------------------------------------------------
DMA_HEAP_IOCTL_ALLOC = 0xC0184800
DMA_BUF_IOCTL_SYNC = 0x40086200

DMA_BUF_SYNC_READ = 1 << 0
DMA_BUF_SYNC_WRITE = 2 << 0
DMA_BUF_SYNC_RW = DMA_BUF_SYNC_READ | DMA_BUF_SYNC_WRITE
DMA_BUF_SYNC_START = 0 << 2
DMA_BUF_SYNC_END = 1 << 2


class DmaHeapAllocationData(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_uint64),
        ("fd", ctypes.c_uint32),
        ("fd_flags", ctypes.c_uint32),
        ("heap_flags", ctypes.c_uint64),
    ]


class DmaBufSync(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint64),
    ]


# ---------------------------------------------------------------------------
# Allwinner G2D ioctl & enum constants (from bsp/linux/sunxi-g2d.h)
# ---------------------------------------------------------------------------
G2D_CMD_BITBLT = 0x50
G2D_CMD_FILLRECT = 0x51
G2D_CMD_STRETCHBLT = 0x52
G2D_CMD_PALETTE_TBL = 0x53
G2D_CMD_QUEUE = 0x54
G2D_CMD_BITBLT_H = 0x55
G2D_CMD_FILLRECT_H = 0x56
G2D_CMD_BLD_H = 0x57
G2D_CMD_MASK_H = 0x58
G2D_CMD_QUERY_VERSION = 0x8008479F


class G2DFormat(enum.IntEnum):
    """Enhanced pixel formats (`g2d_fmt_enh` in sunxi-g2d.h)."""
    ARGB8888 = 0x00
    ABGR8888 = 0x01
    RGBA8888 = 0x02
    BGRA8888 = 0x03
    XRGB8888 = 0x04
    XBGR8888 = 0x05
    RGBX8888 = 0x06
    BGRX8888 = 0x07
    RGB888 = 0x08
    BGR888 = 0x09
    RGB565 = 0x0A
    BGR565 = 0x0B
    ARGB4444 = 0x0C
    ABGR4444 = 0x0D
    RGBA4444 = 0x0E
    BGRA4444 = 0x0F
    ARGB1555 = 0x10
    ABGR1555 = 0x11
    RGBA5551 = 0x12
    BGRA5551 = 0x13
    ARGB2101010 = 0x14
    ABGR2101010 = 0x15
    RGBA1010102 = 0x16
    BGRA1010102 = 0x17

    IYUV422_V0Y1U0Y0 = 0x20
    IYUV422_Y1V0Y0U0 = 0x21
    IYUV422_U0Y1V0Y0 = 0x22
    IYUV422_Y1U0Y0V0 = 0x23
    YUV422UVC_V1U1V0U0 = 0x24
    YUV422UVC_U1V1U0V0 = 0x25
    YUV422_PLANAR = 0x26

    YUV420UVC_V1U1V0U0 = 0x28  # NV12 in little-endian (Y plane + interleaved U,V bytes)
    YUV420UVC_U1V1U0V0 = 0x29  # NV21 in little-endian (Y plane + interleaved V,U bytes)
    YUV420_PLANAR = 0x2A

    YUV411UVC_V1U1V0U0 = 0x2C
    YUV411UVC_U1V1U0V0 = 0x2D
    YUV411_PLANAR = 0x2E

    Y8 = 0x30


class G2DBltFlagsH(enum.IntFlag):
    """Blit / rotation flags (`g2d_blt_flags_h` in sunxi-g2d.h)."""
    NONE_H = 0x00000000
    ROT_90 = 0x00000100
    ROT_180 = 0x00000200
    ROT_270 = 0x00000300
    ROT_0 = 0x00000400
    ROT_H = 0x00001000  # Horizontal mirror / flip
    ROT_V = 0x00002000  # Vertical mirror / flip


class G2DAlphaModeEnh(enum.IntEnum):
    PIXEL_ALPHA = 0
    GLOBAL_ALPHA = 1
    MIXER_ALPHA = 2


class G2DColorGamut(enum.IntEnum):
    BT601 = 0
    BT709 = 1
    BT2020 = 2


class G2DColorRange(enum.IntEnum):
    RANGE_0_255 = 0
    RANGE_16_235 = 1


# ---------------------------------------------------------------------------
# Allwinner G2D ctypes structures (verified against aarch64 C layout)
# ---------------------------------------------------------------------------
class G2DRect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int32),
        ("y", ctypes.c_int32),
        ("w", ctypes.c_uint32),
        ("h", ctypes.c_uint32),
    ]


class G2DSize(ctypes.Structure):
    _fields_ = [
        ("w", ctypes.c_uint32),
        ("h", ctypes.c_uint32),
    ]


class G2DCoor(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_uint32),
        ("y", ctypes.c_uint32),
    ]


class G2DImageEnh(ctypes.Structure):
    _fields_ = [
        ("bbuff", ctypes.c_int32),
        ("color", ctypes.c_uint32),
        ("format", ctypes.c_uint32),
        ("laddr", ctypes.c_uint32 * 3),
        ("haddr", ctypes.c_uint32 * 3),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("align", ctypes.c_uint32 * 3),
        ("clip_rect", G2DRect),
        ("resize", G2DSize),
        ("coor", G2DCoor),
        ("gamut", ctypes.c_uint32),
        ("bpremul", ctypes.c_int32),
        ("alpha", ctypes.c_uint8),
        ("mode", ctypes.c_uint32),
        ("fd", ctypes.c_int32),
        ("use_phy_addr", ctypes.c_uint32),
        ("color_range", ctypes.c_uint32),
    ]


class G2DFillRectH(ctypes.Structure):
    _fields_ = [
        ("dst_image_h", G2DImageEnh),
    ]


class G2DBltH(ctypes.Structure):
    _fields_ = [
        ("flag_h", ctypes.c_uint32),
        ("src_image_h", G2DImageEnh),
        ("dst_image_h", G2DImageEnh),
    ]


class G2DHardwareVersion(ctypes.Structure):
    _fields_ = [
        ("g2d_version", ctypes.c_uint32),
        ("chip_version", ctypes.c_uint32),
    ]


# Compile-time ABI sanity checks matching aarch64 gcc
assert ctypes.sizeof(DmaHeapAllocationData) == 24
assert ctypes.sizeof(DmaBufSync) == 8
assert ctypes.sizeof(G2DRect) == 16
assert ctypes.sizeof(G2DSize) == 8
assert ctypes.sizeof(G2DCoor) == 8
assert ctypes.sizeof(G2DImageEnh) == 116
assert ctypes.sizeof(G2DFillRectH) == 116
assert ctypes.sizeof(G2DBltH) == 236


def format_byte_size(width: int, height: int, fmt: G2DFormat) -> int:
    """Calculate the buffer size in bytes for a given image format and dimensions."""
    if fmt in (
        G2DFormat.ARGB8888,
        G2DFormat.ABGR8888,
        G2DFormat.RGBA8888,
        G2DFormat.BGRA8888,
        G2DFormat.XRGB8888,
        G2DFormat.XBGR8888,
        G2DFormat.RGBX8888,
        G2DFormat.BGRX8888,
    ):
        return width * height * 4
    if fmt in (G2DFormat.RGB888, G2DFormat.BGR888):
        return width * height * 3
    if fmt in (G2DFormat.RGB565, G2DFormat.BGR565):
        return width * height * 2
    if fmt in (
        G2DFormat.YUV420UVC_V1U1V0U0,
        G2DFormat.YUV420UVC_U1V1U0V0,
        G2DFormat.YUV420_PLANAR,
    ):
        return width * height * 3 // 2
    if fmt == G2DFormat.Y8:
        return width * height
    raise ValueError(f"Unsupported G2DFormat for size calculation: {fmt}")


# ---------------------------------------------------------------------------
# Zero-Copy DMA-BUF Buffer Class
# ---------------------------------------------------------------------------
class DmaBuffer:
    """
    Represents a DMA-BUF allocated from `/dev/dma_heap/system` and memory-mapped
    into Python with a zero-copy NumPy array view.
    """

    def __init__(
        self,
        size: int,
        heap_fd: Optional[int] = None,
        shape: Optional[Tuple[int, ...]] = None,
        dtype: Union[np.dtype, type] = np.uint8,
    ):
        self.size = int(size)
        self._owns_heap_fd = heap_fd is None
        self._heap_fd = (
            os.open("/dev/dma_heap/system", os.O_RDWR) if heap_fd is None else heap_fd
        )

        alloc = DmaHeapAllocationData(
            len=self.size,
            fd=0,
            fd_flags=os.O_RDWR | os.O_CLOEXEC,
            heap_flags=0,
        )
        fcntl.ioctl(self._heap_fd, DMA_HEAP_IOCTL_ALLOC, alloc)
        self.fd = int(alloc.fd)

        if self._owns_heap_fd:
            os.close(self._heap_fd)
            self._heap_fd = -1

        self.mmap_obj = mmap.mmap(
            self.fd,
            self.size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
        )
        raw_arr = np.frombuffer(self.mmap_obj, dtype=dtype)
        self.array = raw_arr.reshape(shape) if shape is not None else raw_arr

    def sync_start(self, flags: int = DMA_BUF_SYNC_RW) -> None:
        """Begin CPU access to the DMA-BUF (`DMA_BUF_SYNC_START`)."""
        sync = DmaBufSync(flags=DMA_BUF_SYNC_START | flags)
        fcntl.ioctl(self.fd, DMA_BUF_IOCTL_SYNC, sync)

    def sync_end(self, flags: int = DMA_BUF_SYNC_RW) -> None:
        """End CPU access to the DMA-BUF (`DMA_BUF_SYNC_END`) and flush caches."""
        sync = DmaBufSync(flags=DMA_BUF_SYNC_END | flags)
        fcntl.ioctl(self.fd, DMA_BUF_IOCTL_SYNC, sync)

    def close(self) -> None:
        """Release the NumPy view, unmap memory, and close the DMA-BUF fd."""
        self.array = None
        if getattr(self, "mmap_obj", None) is not None:
            try:
                self.mmap_obj.close()
            except BufferError:
                pass
            self.mmap_obj = None
        if getattr(self, "fd", -1) >= 0:
            os.close(self.fd)
            self.fd = -1
        if getattr(self, "_owns_heap_fd", False) and getattr(self, "_heap_fd", -1) >= 0:
            os.close(self._heap_fd)
            self._heap_fd = -1

    def __enter__(self) -> "DmaBuffer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# High-Level Allwinner G2D Hardware Accelerator Device Class
# ---------------------------------------------------------------------------
class G2DDevice:
    """
    Python interface to `/dev/g2d` and `/dev/dma_heap/system`.
    Can be used as a context manager:
        with G2DDevice() as g2d:
            ...
    """

    def __init__(
        self,
        g2d_path: str = "/dev/g2d",
        heap_path: str = "/dev/dma_heap/system",
    ):
        self.g2d_fd = os.open(g2d_path, os.O_RDWR)
        self.heap_fd = os.open(heap_path, os.O_RDWR)

    def close(self) -> None:
        if getattr(self, "heap_fd", -1) >= 0:
            os.close(self.heap_fd)
            self.heap_fd = -1
        if getattr(self, "g2d_fd", -1) >= 0:
            os.close(self.g2d_fd)
            self.g2d_fd = -1

    def __enter__(self) -> "G2DDevice":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def query_version(self) -> Tuple[int, int]:
        """Query `(g2d_version, chip_version)` via `G2D_CMD_QUERY_VERSION`."""
        ver = G2DHardwareVersion()
        fcntl.ioctl(self.g2d_fd, G2D_CMD_QUERY_VERSION, ver)
        return int(ver.g2d_version), int(ver.chip_version)

    def alloc_buffer(
        self,
        size: int,
        shape: Optional[Tuple[int, ...]] = None,
        dtype: Union[np.dtype, type] = np.uint8,
    ) -> DmaBuffer:
        """Allocate a zero-copy `DmaBuffer` from `/dev/dma_heap/system`."""
        return DmaBuffer(size=size, heap_fd=self.heap_fd, shape=shape, dtype=dtype)

    def alloc_image_buffer(
        self,
        width: int,
        height: int,
        fmt: G2DFormat = G2DFormat.ARGB8888,
    ) -> DmaBuffer:
        """Allocate a `DmaBuffer` shaped appropriately for the given image format."""
        size = format_byte_size(width, height, fmt)
        if fmt in (
            G2DFormat.ARGB8888,
            G2DFormat.ABGR8888,
            G2DFormat.RGBA8888,
            G2DFormat.BGRA8888,
            G2DFormat.XRGB8888,
            G2DFormat.XBGR8888,
            G2DFormat.RGBX8888,
            G2DFormat.BGRX8888,
        ):
            shape: Optional[Tuple[int, ...]] = (height, width, 4)
        elif fmt in (G2DFormat.RGB888, G2DFormat.BGR888):
            shape = (height, width, 3)
        elif fmt == G2DFormat.Y8:
            shape = (height, width)
        else:
            shape = (size,)
        return self.alloc_buffer(size=size, shape=shape, dtype=np.uint8)

    # -----------------------------------------------------------------------
    # Core Low-Level DMA-BUF G2D Operations
    # -----------------------------------------------------------------------
    def rotate(
        self,
        src_buf: DmaBuffer,
        dst_buf: DmaBuffer,
        src_w: int,
        src_h: int,
        angle: int = 90,
        fmt: G2DFormat = G2DFormat.ARGB8888,
    ) -> None:
        """
        Hardware rotation using `G2D_CMD_BITBLT_H` (`G2D_ROT`).
        Supported `angle` values: 0, 90, 180, 270.
        For 90 or 270 degrees, destination dimensions are `(src_h, src_w)`.
        """
        flag_map = {
            0: G2DBltFlagsH.ROT_0,
            90: G2DBltFlagsH.ROT_90,
            180: G2DBltFlagsH.ROT_180,
            270: G2DBltFlagsH.ROT_270,
        }
        if angle not in flag_map:
            raise ValueError(f"Unsupported rotation angle {angle}; must be 0, 90, 180, or 270")

        dst_w, dst_h = (src_h, src_w) if angle in (90, 270) else (src_w, src_h)
        blt = G2DBltH()
        blt.flag_h = int(flag_map[angle])

        blt.src_image_h.bbuff = 1
        blt.src_image_h.format = int(fmt)
        blt.src_image_h.width = src_w
        blt.src_image_h.height = src_h
        blt.src_image_h.clip_rect = G2DRect(0, 0, src_w, src_h)
        blt.src_image_h.alpha = 0xFF
        blt.src_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.src_image_h.fd = src_buf.fd

        blt.dst_image_h.bbuff = 1
        blt.dst_image_h.format = int(fmt)
        blt.dst_image_h.width = dst_w
        blt.dst_image_h.height = dst_h
        blt.dst_image_h.clip_rect = G2DRect(0, 0, dst_w, dst_h)
        blt.dst_image_h.alpha = 0xFF
        blt.dst_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.dst_image_h.fd = dst_buf.fd

        fcntl.ioctl(self.g2d_fd, G2D_CMD_BITBLT_H, blt)

    def flip(
        self,
        src_buf: DmaBuffer,
        dst_buf: DmaBuffer,
        width: int,
        height: int,
        horizontal: bool = True,
        fmt: G2DFormat = G2DFormat.ARGB8888,
    ) -> None:
        """
        Hardware mirror/flip using `G2D_CMD_BITBLT_H` (`G2D_ROT_H` or `G2D_ROT_V`).
        """
        blt = G2DBltH()
        blt.flag_h = int(G2DBltFlagsH.ROT_H if horizontal else G2DBltFlagsH.ROT_V)

        blt.src_image_h.bbuff = 1
        blt.src_image_h.format = int(fmt)
        blt.src_image_h.width = width
        blt.src_image_h.height = height
        blt.src_image_h.clip_rect = G2DRect(0, 0, width, height)
        blt.src_image_h.alpha = 0xFF
        blt.src_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.src_image_h.fd = src_buf.fd

        blt.dst_image_h.bbuff = 1
        blt.dst_image_h.format = int(fmt)
        blt.dst_image_h.width = width
        blt.dst_image_h.height = height
        blt.dst_image_h.clip_rect = G2DRect(0, 0, width, height)
        blt.dst_image_h.alpha = 0xFF
        blt.dst_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.dst_image_h.fd = dst_buf.fd

        fcntl.ioctl(self.g2d_fd, G2D_CMD_BITBLT_H, blt)

    def fill_rect(
        self,
        dst_buf: DmaBuffer,
        width: int,
        height: int,
        color_argb: int,
        rect: Optional[Tuple[int, int, int, int]] = None,
        fmt: G2DFormat = G2DFormat.ARGB8888,
    ) -> None:
        """
        Solid rectangle color fill using `G2D_CMD_FILLRECT_H`.
        `rect` is an optional `(x, y, w, h)` tuple; defaults to `(0, 0, width, height)`.
        """
        rx, ry, rw, rh = rect if rect is not None else (0, 0, width, height)
        fill = G2DFillRectH()
        fill.dst_image_h.bbuff = 1
        fill.dst_image_h.color = int(color_argb) & 0xFFFFFFFF
        fill.dst_image_h.format = int(fmt)
        fill.dst_image_h.width = width
        fill.dst_image_h.height = height
        fill.dst_image_h.clip_rect = G2DRect(rx, ry, rw, rh)
        fill.dst_image_h.alpha = 0xFF
        fill.dst_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        fill.dst_image_h.fd = dst_buf.fd

        fcntl.ioctl(self.g2d_fd, G2D_CMD_FILLRECT_H, fill)

    def scale(
        self,
        src_buf: DmaBuffer,
        src_w: int,
        src_h: int,
        dst_buf: DmaBuffer,
        dst_w: int,
        dst_h: int,
        fmt: G2DFormat = G2DFormat.ARGB8888,
        src_rect: Optional[Tuple[int, int, int, int]] = None,
        dst_rect: Optional[Tuple[int, int, int, int]] = None,
    ) -> None:
        """
        Scale / resize an image buffer using `G2D_CMD_BITBLT_H`.
        """
        sx, sy, sw, sh = src_rect if src_rect is not None else (0, 0, src_w, src_h)
        dx, dy, dw, dh = dst_rect if dst_rect is not None else (0, 0, dst_w, dst_h)

        blt = G2DBltH()
        blt.flag_h = int(G2DBltFlagsH.NONE_H)

        blt.src_image_h.bbuff = 1
        blt.src_image_h.format = int(fmt)
        blt.src_image_h.width = src_w
        blt.src_image_h.height = src_h
        blt.src_image_h.clip_rect = G2DRect(sx, sy, sw, sh)
        blt.src_image_h.alpha = 0xFF
        blt.src_image_h.mode = int(G2DAlphaModeEnh.GLOBAL_ALPHA)
        blt.src_image_h.fd = src_buf.fd

        blt.dst_image_h.bbuff = 1
        blt.dst_image_h.format = int(fmt)
        blt.dst_image_h.width = dst_w
        blt.dst_image_h.height = dst_h
        blt.dst_image_h.clip_rect = G2DRect(dx, dy, dw, dh)
        blt.dst_image_h.resize = G2DSize(dw, dh)
        blt.dst_image_h.alpha = 0xFF
        blt.dst_image_h.mode = int(G2DAlphaModeEnh.GLOBAL_ALPHA)
        blt.dst_image_h.fd = dst_buf.fd

        fcntl.ioctl(self.g2d_fd, G2D_CMD_BITBLT_H, blt)

    def convert_format(
        self,
        src_buf: DmaBuffer,
        dst_buf: DmaBuffer,
        width: int,
        height: int,
        src_fmt: G2DFormat = G2DFormat.ARGB8888,
        dst_fmt: G2DFormat = G2DFormat.YUV420UVC_V1U1V0U0,
        gamut: G2DColorGamut = G2DColorGamut.BT601,
    ) -> None:
        """
        Convert pixel format (e.g. `ARGB8888` -> `YUV420UVC_V1U1V0U0` NV21)
        using `G2D_CMD_BITBLT_H`.
        """
        blt = G2DBltH()
        blt.flag_h = int(G2DBltFlagsH.NONE_H)

        blt.src_image_h.bbuff = 1
        blt.src_image_h.format = int(src_fmt)
        blt.src_image_h.width = width
        blt.src_image_h.height = height
        blt.src_image_h.clip_rect = G2DRect(0, 0, width, height)
        blt.src_image_h.gamut = int(gamut)
        blt.src_image_h.alpha = 0xFF
        blt.src_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.src_image_h.fd = src_buf.fd

        blt.dst_image_h.bbuff = 1
        blt.dst_image_h.format = int(dst_fmt)
        blt.dst_image_h.width = width
        blt.dst_image_h.height = height
        blt.dst_image_h.clip_rect = G2DRect(0, 0, width, height)
        blt.dst_image_h.gamut = int(gamut)
        blt.dst_image_h.alpha = 0xFF
        blt.dst_image_h.mode = int(G2DAlphaModeEnh.PIXEL_ALPHA)
        blt.dst_image_h.fd = dst_buf.fd

        fcntl.ioctl(self.g2d_fd, G2D_CMD_BITBLT_H, blt)
