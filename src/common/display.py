"""Shared desktop and legacy-fbdev display ownership for Pygame games."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Callable

import pygame

from .fbdev import FbdevPresenter


@dataclass(frozen=True)
class DisplaySettings:
    backend: str = "pygame"
    framebuffer: Path = Path("/dev/fb0")

    def __post_init__(self) -> None:
        if self.backend not in ("pygame", "fbdev"):
            raise ValueError(f"unknown display backend: {self.backend}")


def display_settings(default_backend: str = "pygame", default_framebuffer: Path = Path("/dev/fb0")) -> DisplaySettings:
    """Read provider-supplied platform settings, with portable defaults."""
    backend = os.environ.get("PI_PY_GAMES_DISPLAY_BACKEND", default_backend).strip().lower() or default_backend
    framebuffer = Path(os.environ.get("PI_PY_GAMES_FRAMEBUFFER", str(default_framebuffer))).expanduser()
    return DisplaySettings(backend, framebuffer)


def initialize_pygame(settings: DisplaySettings, audio: bool = False) -> None:
    """Initialize only the subsystems a direct-fbdev game actually needs.

    SDL2 opens and grabs Linux keyboard event devices during normal video
    initialization.  fbdev games use the tty and direct joystick reader
    instead, so they must not call :func:`pygame.init`.
    """
    if settings.backend == "pygame":
        pygame.init()
        return
    pygame.font.init()
    if audio:
        pygame.mixer.init()


class GameDisplay:
    """One game canvas with either SDL presentation or direct fbdev presentation."""

    def __init__(
        self,
        settings: DisplaySettings,
        canvas_size: tuple[int, int],
        presenter_factory: Callable[[Path, tuple[int, int]], FbdevPresenter] = FbdevPresenter,
        *,
        logical_size: tuple[int, int] | None = None,
    ) -> None:
        self.settings = settings
        self.canvas_size = canvas_size
        self.logical_size = logical_size or canvas_size
        self._presenter_factory = presenter_factory
        self.framebuffer: FbdevPresenter | None = None
        self._output: pygame.Surface
        self.canvas: pygame.Surface
        self.last_scale_ms = 0.0
        self.last_backend_present_ms = 0.0
        self._open()

    def _open(self) -> None:
        if self.settings.backend == "fbdev":
            self.framebuffer = self._presenter_factory(self.settings.framebuffer, self.canvas_size)
            self._output = self.framebuffer.canvas
        else:
            self._output = pygame.display.set_mode(self.canvas_size)
        if self.logical_size == self.canvas_size:
            self.canvas = self._output
        else:
            # fbdev's RGB565 canvas cannot be an in-place scale destination for
            # Pygame's default 32-bit surface.  Match the output format so the
            # scaler can write directly to it on both desktop and Pi.
            self.canvas = pygame.Surface(
                self.logical_size,
                depth=self._output.get_bitsize(),
                masks=self._output.get_masks(),
            )

    def present(self, rectangles: list[pygame.Rect] | None = None) -> None:
        scale_started = time.perf_counter()
        if self.canvas is not self._output:
            # pygame.transform.scale is deliberately nearest-neighbour.  Scale
            # only dirty logical rectangles when possible; fbdev otherwise pays
            # a full 854x480 conversion and framebuffer copy every frame.
            if rectangles is None:
                pygame.transform.scale(self.canvas, self.canvas_size, self._output)
                rectangles = None
            else:
                source_rectangles = rectangles
                output_rectangles: list[pygame.Rect] = []
                for source in source_rectangles:
                    source = source.clip(self.canvas.get_rect())
                    if not source.width or not source.height:
                        continue
                    left = round(source.left * self.canvas_size[0] / self.logical_size[0])
                    top = round(source.top * self.canvas_size[1] / self.logical_size[1])
                    right = round(source.right * self.canvas_size[0] / self.logical_size[0])
                    bottom = round(source.bottom * self.canvas_size[1] / self.logical_size[1])
                    destination = pygame.Rect(left, top, right - left, bottom - top)
                    pygame.transform.scale(self.canvas.subsurface(source), destination.size, self._output.subsurface(destination))
                    output_rectangles.append(destination)
                rectangles = output_rectangles
        self.last_scale_ms = (time.perf_counter() - scale_started) * 1000
        backend_started = time.perf_counter()
        if self.framebuffer is not None:
            self.framebuffer.present(self._output, rectangles)
        else:
            pygame.display.flip()
        self.last_backend_present_ms = (time.perf_counter() - backend_started) * 1000

    def reopen(self) -> None:
        if self.framebuffer is None:
            return
        self.framebuffer.close()
        self.framebuffer = None
        self._open()

    def close(self) -> None:
        if self.framebuffer is not None:
            self.framebuffer.close()
            self.framebuffer = None
