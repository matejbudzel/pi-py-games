"""Shared desktop and legacy-fbdev display ownership for Pygame games."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
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


def prepare_pygame_display(settings: DisplaySettings) -> None:
    """Select SDL's headless driver before Pygame initializes for fbdev mode."""
    if settings.backend == "fbdev":
        os.environ["SDL_VIDEODRIVER"] = "dummy"


class GameDisplay:
    """One game canvas with either SDL presentation or direct fbdev presentation."""

    def __init__(
        self,
        settings: DisplaySettings,
        canvas_size: tuple[int, int],
        presenter_factory: Callable[[Path, tuple[int, int]], FbdevPresenter] = FbdevPresenter,
    ) -> None:
        self.settings = settings
        self.canvas_size = canvas_size
        self._presenter_factory = presenter_factory
        self.framebuffer: FbdevPresenter | None = None
        self.canvas: pygame.Surface
        self._open()

    def _open(self) -> None:
        if self.settings.backend == "fbdev":
            pygame.display.set_mode((1, 1))
            self.framebuffer = self._presenter_factory(self.settings.framebuffer, self.canvas_size)
            self.canvas = self.framebuffer.canvas
        else:
            self.canvas = pygame.display.set_mode(self.canvas_size)

    def present(self, rectangles: list[pygame.Rect] | None = None) -> None:
        if self.framebuffer is not None:
            self.framebuffer.present(self.canvas, rectangles)
        else:
            pygame.display.flip()

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
