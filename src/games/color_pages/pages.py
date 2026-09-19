"""Small, redistributable palette-indexed pixel-art pages."""
from __future__ import annotations

from dataclasses import dataclass
import math

Color = tuple[int, int, int]
Pixel = tuple[int, int]


@dataclass(frozen=True)
class Page:
    title: str
    size: int
    palette: tuple[Color, ...]
    pixels: tuple[tuple[int, ...], ...]  # -1 is the always-black background.

    @property
    def color_count(self) -> int:
        return len(self.palette)


def _canvas(size: int) -> list[list[int]]:
    return [[-1 for _ in range(size)] for _ in range(size)]


def _put(canvas: list[list[int]], x: int, y: int, color: int) -> None:
    if 0 <= y < len(canvas) and 0 <= x < len(canvas):
        canvas[y][x] = color


def _circle(canvas: list[list[int]], cx: int, cy: int, radius: int, color: int) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                _put(canvas, x, y, color)


def _line(canvas: list[list[int]], a: Pixel, b: Pixel, width: int, color: int) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    steps = max(abs(dx), abs(dy), 1)
    for step in range(steps + 1):
        x = round(a[0] + dx * step / steps)
        y = round(a[1] + dy * step / steps)
        _circle(canvas, x, y, max(0, width // 2), color)


def _page(title: str, size: int, palette: tuple[Color, ...], painter) -> Page:
    canvas = _canvas(size)
    painter(canvas)
    return Page(title, size, palette, tuple(tuple(row) for row in canvas))


def _heart() -> Page:
    palette = ((230, 55, 92), (255, 121, 151), (137, 30, 65))
    def paint(c):
        for y in range(2, 15):
            for x in range(16):
                dx, dy = x - 7.5, y - 7
                if ((dx + 3.2) ** 2 + (dy + 1.8) ** 2 < 18 or (dx - 3.2) ** 2 + (dy + 1.8) ** 2 < 18) and y < 9 or abs(dx) < 7 - abs(y - 8):
                    _put(c, x, y, 0)
        for x in range(3, 13): _put(c, x, 3, 1)
        for y in range(5, 9): _put(c, 3, y, 1)
        for x, y in ((5, 5), (6, 5), (5, 6), (6, 6), (11, 8), (10, 9), (9, 10), (8, 11)):
            _put(c, x, y, 2)
    return _page("Heart", 16, palette, paint)


def _star() -> Page:
    palette = ((255, 204, 54), (255, 239, 134), (218, 143, 25))
    def paint(c):
        points = ((8, 1), (10, 6), (15, 6), (11, 9), (13, 14), (8, 11), (3, 14), (5, 9), (1, 6), (6, 6))
        # rasterise by testing the polygon scan lines
        for y in range(16):
            crossings = []
            for a, b in zip(points, points[1:] + points[:1]):
                if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                    crossings.append(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
            for a, b in zip(sorted(crossings)[::2], sorted(crossings)[1::2]):
                for x in range(math.ceil(a), math.floor(b) + 1): _put(c, x, y, 0)
        for x in range(6, 10): _put(c, x, 4, 1)
        for x, y in ((8, 1), (8, 2), (12, 7), (11, 8), (8, 11), (4, 7)):_put(c, x, y, 2)
    return _page("Star", 16, palette, paint)


def _clover() -> Page:
    palette = ((54, 178, 81), (106, 220, 112), (23, 106, 57))
    def paint(c):
        for cx, cy in ((5, 5), (10, 5), (5, 10), (10, 10)):_circle(c, cx, cy, 3, 0)
        _line(c, (8, 10), (12, 15), 2, 2)
        for x, y in ((4, 3), (5, 3), (9, 3), (10, 3), (3, 8), (8, 8)):_put(c, x, y, 1)
    return _page("Clover", 16, palette, paint)


def _flower() -> Page:
    palette = ((248, 92, 148), (255, 172, 194), (255, 211, 49), (59, 169, 79), (25, 103, 55))
    def paint(c):
        _line(c, (16, 16), (16, 31), 3, 4)
        _line(c, (16, 25), (7, 25), 3, 3); _line(c, (16, 28), (25, 27), 3, 3)
        for angle in range(0, 360, 45):
            _circle(c, 16 + round(math.cos(math.radians(angle))*8), 16 + round(math.sin(math.radians(angle))*8), 6, 0)
        _circle(c, 16, 16, 5, 2)
        _circle(c, 14, 14, 2, 1)
    return _page("Flower", 32, palette, paint)


def _rainbow() -> Page:
    palette = ((239, 70, 83), (255, 151, 51), (255, 220, 61), (75, 186, 96), (66, 140, 231), (139, 92, 211))
    def paint(c):
        cx, cy = 16, 30
        for y in range(32):
            for x in range(32):
                r = math.hypot(x-cx, y-cy)
                if y <= cy and 11 <= r <= 27:
                    _put(c, x, y, min(5, int((r-11)//3)))
    return _page("Rainbow", 32, palette, paint)


def _unicorn() -> Page:
    palette = ((250, 246, 235), (222, 104, 179), (121, 193, 244), (252, 210, 57), (73, 70, 111), (255, 158, 190))
    def paint(c):
        # friendly side-on unicorn, deliberately chunky for a 64px page
        for y in range(17, 50):
            for x in range(12, 53):
                if ((x-32)/22)**2 + ((y-34)/16)**2 < 1: _put(c, x, y, 0)
        _circle(c, 43, 22, 12, 0); _circle(c, 49, 28, 8, 0)
        _line(c, (40, 12), (46, 1), 4, 3)
        for y in range(15, 42): _line(c, (19, y), (15, y+3), 3, 1)
        _circle(c, 48, 21, 2, 4); _circle(c, 54, 30, 2, 5)
        for x in (21, 35): _line(c, (x, 45), (x, 57), 5, 0)
        _line(c, (15, 30), (4, 23), 4, 2)
    return _page("Unicorn", 64, palette, paint)


def _fairy() -> Page:
    palette = ((251, 205, 167), (108, 75, 159), (96, 211, 212), (255, 230, 115), (240, 112, 173), (67, 70, 110))
    def paint(c):
        _circle(c, 32, 16, 8, 0); _circle(c, 32, 12, 9, 1)
        _line(c, (32, 24), (32, 43), 8, 4)
        _line(c, (28, 28), (19, 37), 3, 0); _line(c, (36, 28), (45, 37), 3, 0)
        _line(c, (29, 42), (22, 56), 4, 5); _line(c, (35, 42), (42, 56), 4, 5)
        for cx, cy, rx, ry in ((19, 27, 14, 8), (45, 27, 14, 8)):
            for y in range(cy-ry, cy+ry+1):
                for x in range(cx-rx, cx+rx+1):
                    if ((x-cx)/rx)**2 + ((y-cy)/ry)**2 < 1: _put(c, x, y, 2)
        _circle(c, 29, 16, 1, 5); _circle(c, 35, 16, 1, 5)
        _line(c, (43, 36), (54, 47), 2, 3)
    return _page("Fairy", 64, palette, paint)


def _butterfly() -> Page:
    """An extra small page: the request says eight, while naming seven motifs."""
    palette = ((241, 92, 170), (113, 113, 225), (255, 215, 56), (65, 72, 103))
    def paint(c):
        for cx, cy, radius, color in ((10, 9, 7, 0), (22, 9, 7, 1), (10, 23, 7, 1), (22, 23, 7, 0)):
            _circle(c, cx, cy, radius, color)
        _line(c, (16, 6), (16, 27), 3, 3)
        _circle(c, 16, 5, 3, 2)
    return _page("Butterfly", 32, palette, paint)


PAGES = (_heart(), _star(), _clover(), _flower(), _rainbow(), _unicorn(), _fairy(), _butterfly())
