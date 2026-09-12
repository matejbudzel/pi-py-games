"""Small legacy Linux framebuffer presenter for the Raspberry Pi 1."""

from __future__ import annotations

import ctypes
import fcntl
import mmap
import os
from pathlib import Path

import pygame

try:
    from ._fbcopy import copy_full as _copy_full_native
except ImportError:  # Source checkouts remain usable before the extension builds.
    _copy_full_native = None


FBIOGET_FSCREENINFO = 0x4602
FBIOGET_VSCREENINFO = 0x4600


class FramebufferError(RuntimeError):
    """The configured Linux framebuffer cannot present this canvas."""


class _Bitfield(ctypes.Structure):
    _fields_ = [("offset", ctypes.c_uint32), ("length", ctypes.c_uint32), ("msb_right", ctypes.c_uint32)]


class _VariableScreenInfo(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_uint32), ("yres", ctypes.c_uint32),
        ("xres_virtual", ctypes.c_uint32), ("yres_virtual", ctypes.c_uint32),
        ("xoffset", ctypes.c_uint32), ("yoffset", ctypes.c_uint32),
        ("bits_per_pixel", ctypes.c_uint32), ("grayscale", ctypes.c_uint32),
        ("red", _Bitfield), ("green", _Bitfield), ("blue", _Bitfield), ("transp", _Bitfield),
        ("nonstd", ctypes.c_uint32), ("activate", ctypes.c_uint32),
        ("height", ctypes.c_uint32), ("width", ctypes.c_uint32), ("accel_flags", ctypes.c_uint32),
        ("pixclock", ctypes.c_uint32), ("left_margin", ctypes.c_uint32), ("right_margin", ctypes.c_uint32),
        ("upper_margin", ctypes.c_uint32), ("lower_margin", ctypes.c_uint32),
        ("hsync_len", ctypes.c_uint32), ("vsync_len", ctypes.c_uint32),
        ("sync", ctypes.c_uint32), ("vmode", ctypes.c_uint32), ("rotate", ctypes.c_uint32),
        ("colorspace", ctypes.c_uint32), ("reserved", ctypes.c_uint32 * 4),
    ]


class _FixedScreenInfo(ctypes.Structure):
    _fields_ = [
        ("identifier", ctypes.c_char * 16), ("smem_start", ctypes.c_ulong), ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32), ("type_aux", ctypes.c_uint32), ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16), ("ypanstep", ctypes.c_uint16), ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32), ("mmio_start", ctypes.c_ulong), ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32), ("capabilities", ctypes.c_uint16), ("reserved", ctypes.c_uint16 * 2),
    ]


def _bitmask(field: _Bitfield) -> int:
    return 0 if field.length == 0 else ((1 << field.length) - 1) << field.offset


def _read_screen_info(descriptor: int) -> tuple[_FixedScreenInfo, _VariableScreenInfo]:
    fixed_data = bytearray(ctypes.sizeof(_FixedScreenInfo))
    variable_data = bytearray(ctypes.sizeof(_VariableScreenInfo))
    fcntl.ioctl(descriptor, FBIOGET_FSCREENINFO, fixed_data, True)
    fcntl.ioctl(descriptor, FBIOGET_VSCREENINFO, variable_data, True)
    return _FixedScreenInfo.from_buffer_copy(fixed_data), _VariableScreenInfo.from_buffer_copy(variable_data)


class FbdevPresenter:
    """Copy a Pygame canvas to a 16-bit Linux framebuffer with native blits."""

    def __init__(self, path: Path, canvas_size: tuple[int, int]) -> None:
        self._descriptor = os.open(path, os.O_RDWR)
        try:
            fixed, variable = _read_screen_info(self._descriptor)
            if variable.bits_per_pixel != 16:
                raise FramebufferError(f"{path} is {variable.bits_per_pixel} bpp; RGB565 framebuffer required")
            if canvas_size[0] > variable.xres or canvas_size[1] > variable.yres:
                raise FramebufferError(f"canvas {canvas_size[0]}x{canvas_size[1]} does not fit {variable.xres}x{variable.yres} framebuffer")
            self._line_length = fixed.line_length
            self._bytes_per_pixel = variable.bits_per_pixel // 8
            self._map = mmap.mmap(self._descriptor, fixed.smem_len, access=mmap.ACCESS_WRITE)
            self._framebuffer_offset = variable.yoffset * fixed.line_length + variable.xoffset * self._bytes_per_pixel
            self._masks = (_bitmask(variable.red), _bitmask(variable.green), _bitmask(variable.blue), _bitmask(variable.transp))
            self._surface = pygame.Surface((variable.xres, variable.yres), depth=16, masks=self._masks)
            self._canvas_rect = pygame.Rect((variable.xres - canvas_size[0]) // 2, (variable.yres - canvas_size[1]) // 2, *canvas_size)
            self._canvas = pygame.Surface(canvas_size, depth=16, masks=self._masks)
            self._surface.fill((0, 0, 0))
            self._copy_rectangles(self._surface, [pygame.Rect(0, 0, variable.xres, variable.yres)])
        except BaseException:
            self.close()
            raise

    def present(self, canvas: pygame.Surface, rectangles: list[pygame.Rect] | None = None) -> None:
        if canvas.get_size() != self._canvas_rect.size:
            raise FramebufferError(f"canvas changed to {canvas.get_size()}, expected {self._canvas_rect.size}")
        dirty = [rectangle.clip(canvas.get_rect()) for rectangle in (rectangles or [canvas.get_rect()])]
        dirty = [rectangle for rectangle in dirty if rectangle.width and rectangle.height]
        if not dirty:
            return
        if self._canvas_rect == self._surface.get_rect():
            self._copy_rectangles(canvas, dirty)
            return
        for rectangle in dirty:
            destination = rectangle.move(self._canvas_rect.topleft)
            self._surface.blit(canvas, destination, rectangle)
            self._copy_rectangles(self._surface, [destination])

    @property
    def canvas(self) -> pygame.Surface:
        return self._canvas

    def close(self) -> None:
        if hasattr(self, "_map"):
            self._map.close()
            del self._map
        if hasattr(self, "_descriptor"):
            os.close(self._descriptor)
            del self._descriptor

    def _copy_rectangles(self, surface: pygame.Surface, rectangles: list[pygame.Rect]) -> None:
        source_pitch = surface.get_pitch()
        if len(rectangles) == 1 and rectangles[0] == surface.get_rect() and source_pitch == self._line_length:
            byte_count = source_pitch * surface.get_height()
            if _copy_full_native is not None:
                try:
                    _copy_full_native(surface.get_view("0"), self._map, self._framebuffer_offset, byte_count)
                except (BufferError, TypeError, ValueError):
                    # A pygame build without a contiguous BufferProxy still
                    # works through the established Python path.
                    pixels = bytes(surface.get_view("0"))
                    self._map[self._framebuffer_offset:self._framebuffer_offset + byte_count] = pixels
            else:
                pixels = bytes(surface.get_view("0"))
                self._map[self._framebuffer_offset:self._framebuffer_offset + byte_count] = pixels
            return
        pixels = memoryview(surface.get_view("0")).cast("B")
        for rectangle in rectangles:
            row_width = rectangle.width * self._bytes_per_pixel
            for row in range(rectangle.height):
                source_start = (rectangle.y + row) * source_pitch + rectangle.x * self._bytes_per_pixel
                target_start = self._framebuffer_offset + (rectangle.y + row) * self._line_length + rectangle.x * self._bytes_per_pixel
                self._map[target_start:target_start + row_width] = pixels[source_start:source_start + row_width]
