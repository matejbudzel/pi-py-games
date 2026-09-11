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
class Board:
    cells: list[list[int]] = field(default_factory=lambda: [[0] * SIZE for _ in range(SIZE)])
    score: int = 0
    random_source: random.Random = field(default_factory=random.Random, repr=False)

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
        return True

    def move(self, direction: str) -> bool:
        before = [row[:] for row in self.cells]
        gained = 0
        for index in range(SIZE):
            if direction == "left":
                line, points = _collapse(self.cells[index])
                self.cells[index] = line
            elif direction == "right":
                line, points = _collapse(list(reversed(self.cells[index])))
                self.cells[index] = list(reversed(line))
            elif direction == "up":
                line, points = _collapse([self.cells[row][index] for row in range(SIZE)])
                for row, value in enumerate(line):
                    self.cells[row][index] = value
            elif direction == "down":
                line, points = _collapse([self.cells[row][index] for row in reversed(range(SIZE))])
                for row, value in zip(reversed(range(SIZE)), line):
                    self.cells[row][index] = value
            else:
                raise ValueError("unknown direction: %s" % direction)
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
