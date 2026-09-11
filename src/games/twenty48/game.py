"""Pure 2048 board rules, kept independent from Pygame and input devices."""

from __future__ import annotations

from dataclasses import dataclass, field
import random


SIZE = 4


def _collapse(line: list[int]) -> tuple[list[int], int]:
    values = [value for value in line if value]
    merged: list[int] = []
    gained = 0
    index = 0
    while index < len(values):
        if index + 1 < len(values) and values[index] == values[index + 1]:
            value = values[index] * 2
            merged.append(value)
            gained += value
            index += 2
        else:
            merged.append(values[index])
            index += 1
    return merged + [0] * (SIZE - len(merged)), gained


@dataclass
class TileMotion:
    """A tile's pre-spawn movement, expressed in board coordinates."""

    source: tuple[int, int]
    destination: tuple[int, int]
    value: int
    merged: bool = False


@dataclass
class Board:
    cells: list[list[int]] = field(default_factory=lambda: [[0] * SIZE for _ in range(SIZE)])
    score: int = 0
    random_source: random.Random = field(default_factory=random.Random, repr=False)
    last_moves: list[TileMotion] = field(default_factory=list, init=False, repr=False)
    last_spawn: tuple[int, int] | None = field(default=None, init=False, repr=False)

    @classmethod
    def new(cls, random_source: random.Random | None = None) -> "Board":
        board = cls(random_source=random_source or random.Random())
        board.add_tile()
        board.add_tile()
        return board

    def add_tile(self) -> bool:
        empty = [(row, column) for row in range(SIZE) for column in range(SIZE) if self.cells[row][column] == 0]
        if not empty:
            return False
        row, column = self.random_source.choice(empty)
        self.cells[row][column] = 4 if self.random_source.random() < 0.1 else 2
        self.last_spawn = (row, column)
        return True

    def move(self, direction: str) -> bool:
        before = [row[:] for row in self.cells]
        gained = 0
        self.last_moves = []
        self.last_spawn = None
        for index in range(SIZE):
            if direction not in ("left", "right", "up", "down"):
                raise ValueError("unknown direction: %s" % direction)
            if direction == "left":
                coordinates = [(index, column) for column in range(SIZE)]
            elif direction == "right":
                coordinates = [(index, column) for column in reversed(range(SIZE))]
            elif direction == "up":
                coordinates = [(row, index) for row in range(SIZE)]
            else:
                coordinates = [(row, index) for row in reversed(range(SIZE))]
            values, points, motions = _collapse_with_motions(
                [(coordinate, before[coordinate[0]][coordinate[1]]) for coordinate in coordinates]
            )
            for coordinate, value in zip(coordinates, values):
                self.cells[coordinate[0]][coordinate[1]] = value
            self.last_moves.extend(motions)
            gained += points
        changed = self.cells != before
        if changed:
            self.score += gained
            self.add_tile()
        return changed

    @property
    def game_over(self) -> bool:
        if any(value == 0 for row in self.cells for value in row):
            return False
        return all(
            self.cells[row][column] != self.cells[row + 1][column]
            for row in range(SIZE - 1)
            for column in range(SIZE)
        ) and all(
            self.cells[row][column] != self.cells[row][column + 1]
            for row in range(SIZE)
            for column in range(SIZE - 1)
        )


def _collapse_with_motions(
    line: list[tuple[tuple[int, int], int]],
) -> tuple[list[int], int, list[TileMotion]]:
    """Collapse a line while retaining enough information for the view to animate it."""
    values = [(coordinate, value) for coordinate, value in line if value]
    collapsed: list[int] = []
    motions: list[TileMotion] = []
    gained = 0
    index = 0
    while index < len(values):
        source, value = values[index]
        destination = line[len(collapsed)][0]
        if index + 1 < len(values) and value == values[index + 1][1]:
            collapsed.append(value * 2)
            gained += value * 2
            motions.extend((
                TileMotion(source, destination, value, merged=True),
                TileMotion(values[index + 1][0], destination, value, merged=True),
            ))
            index += 2
        else:
            collapsed.append(value)
            motions.append(TileMotion(source, destination, value))
            index += 1
    return collapsed + [0] * (SIZE - len(collapsed)), gained, motions
