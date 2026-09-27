"""Pure falling-block rules for Blocks; no Pygame or device dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
import random


BOARD_WIDTH, BOARD_HEIGHT = 10, 20
PIECES: dict[str, tuple[tuple[tuple[int, int], ...], ...]] = {
    "I": (((0, 1), (1, 1), (2, 1), (3, 1)), ((2, 0), (2, 1), (2, 2), (2, 3))),
    "O": (((1, 0), (2, 0), (1, 1), (2, 1)),),
    "T": (((1, 0), (0, 1), (1, 1), (2, 1)), ((1, 0), (1, 1), (2, 1), (1, 2)), ((0, 1), (1, 1), (2, 1), (1, 2)), ((1, 0), (0, 1), (1, 1), (1, 2))),
    "S": (((1, 0), (2, 0), (0, 1), (1, 1)), ((1, 0), (1, 1), (2, 1), (2, 2))),
    "Z": (((0, 0), (1, 0), (1, 1), (2, 1)), ((2, 0), (1, 1), (2, 1), (1, 2))),
    "J": (((0, 0), (0, 1), (1, 1), (2, 1)), ((1, 0), (2, 0), (1, 1), (1, 2)), ((0, 1), (1, 1), (2, 1), (2, 2)), ((1, 0), (1, 1), (0, 2), (1, 2))),
    "L": (((2, 0), (0, 1), (1, 1), (2, 1)), ((1, 0), (1, 1), (1, 2), (2, 2)), ((0, 1), (1, 1), (2, 1), (0, 2)), ((0, 0), (1, 0), (1, 1), (1, 2))),
}
LINE_SCORES = (0, 100, 300, 500, 800)


@dataclass
class Piece:
    name: str
    x: int = 3
    y: int = 0
    rotation: int = 0

    @property
    def cells(self) -> tuple[tuple[int, int], ...]:
        return PIECES[self.name][self.rotation % len(PIECES[self.name])]


@dataclass
class Game:
    board: list[list[str | None]] = field(default_factory=lambda: [[None] * BOARD_WIDTH for _ in range(BOARD_HEIGHT)])
    random_source: random.Random = field(default_factory=random.Random, repr=False)
    bag: list[str] = field(default_factory=list)
    current: Piece | None = None
    next_name: str = "I"
    score: int = 0
    lines: int = 0
    game_over: bool = False

    @classmethod
    def new(cls, random_source: random.Random | None = None) -> "Game":
        game = cls(random_source=random_source or random.Random())
        game.next_name = game._take_name()
        game.spawn()
        return game

    @property
    def level(self) -> int:
        return 1 + self.lines // 10

    @property
    def fall_seconds(self) -> float:
        return max(0.12, 0.85 - (self.level - 1) * 0.045)

    def _take_name(self) -> str:
        if not self.bag:
            self.bag = list(PIECES)
            self.random_source.shuffle(self.bag)
        return self.bag.pop()

    def spawn(self) -> None:
        self.current = Piece(self.next_name)
        self.next_name = self._take_name()
        if self._collides(self.current):
            self.game_over = True

    def _collides(self, piece: Piece) -> bool:
        return any(x + piece.x < 0 or x + piece.x >= BOARD_WIDTH or y + piece.y >= BOARD_HEIGHT or (y + piece.y >= 0 and self.board[y + piece.y][x + piece.x] is not None) for x, y in piece.cells)

    def move(self, dx: int, dy: int) -> bool:
        if self.game_over or self.current is None:
            return False
        candidate = Piece(self.current.name, self.current.x + dx, self.current.y + dy, self.current.rotation)
        if self._collides(candidate):
            return False
        self.current = candidate
        return True

    def rotate(self, direction: int) -> bool:
        if self.game_over or self.current is None:
            return False
        turns = len(PIECES[self.current.name])
        rotation = (self.current.rotation + direction) % turns
        # A small, conventional wall kick keeps rotation friendly at either edge.
        for offset in (0, -1, 1, -2, 2):
            candidate = Piece(self.current.name, self.current.x + offset, self.current.y, rotation)
            if not self._collides(candidate):
                self.current = candidate
                return True
        return False

    def tick(self) -> bool:
        if self.move(0, 1):
            return False
        self._lock()
        return True

    def soft_drop(self) -> bool:
        if self.move(0, 1):
            self.score += 1
            return True
        self._lock()
        return False

    def _lock(self) -> None:
        if self.current is None:
            return
        for x, y in self.current.cells:
            if y + self.current.y >= 0:
                self.board[y + self.current.y][x + self.current.x] = self.current.name
        full = [row for row in self.board if all(cell is not None for cell in row)]
        if full:
            self.board = [[None] * BOARD_WIDTH for _ in full] + [row for row in self.board if not all(cell is not None for cell in row)]
            cleared = len(full)
            self.score += LINE_SCORES[cleared] * self.level
            self.lines += cleared
        self.spawn()
