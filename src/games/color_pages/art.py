"""External PNG coloring pages, kept separate from the game program."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

Color = tuple[int, int, int]
VALID_SIZES = frozenset((16, 32, 64))


@dataclass(frozen=True)
class Page:
    title: str
    source: Path
    size: int
    palette: tuple[Color, ...]
    pixels: tuple[tuple[int, ...], ...]  # -1 is transparent / always-black background.

    @property
    def color_count(self) -> int:
        return len(self.palette)


def load_pages(directory: Path) -> tuple[Page, ...]:
    """Load supported first-level PNGs; malformed or unsuitable files are ignored."""
    try:
        candidates = sorted(
            (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".png"),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return ()
    pages: list[Page] = []
    for path in candidates:
        try:
            surface = pygame.image.load(path)
            width, height = surface.get_size()
            if width != height or width not in VALID_SIZES:
                continue
            palette: list[Color] = []
            palette_index: dict[Color, int] = {}
            pixels: list[tuple[int, ...]] = []
            for y in range(height):
                row: list[int] = []
                for x in range(width):
                    sample = surface.get_at((x, y))
                    if sample.a == 0:
                        row.append(-1)
                        continue
                    color = (sample.r, sample.g, sample.b)
                    index = palette_index.get(color)
                    if index is None:
                        index = len(palette)
                        palette_index[color] = index
                        palette.append(color)
                    row.append(index)
                pixels.append(tuple(row))
        except pygame.error:
            continue
        pages.append(Page(path.stem, path, width, tuple(palette), tuple(pixels)))
    return tuple(pages)
