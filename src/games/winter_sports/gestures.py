"""Pure contact facts derived from shared cardinal actions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GestureFrame:
    left: bool
    right: bool
    row: int
    cadence: float
    regularity: float
    symmetry: float
    lean: float
    airborne: bool
    airborne_seconds: float
    landed: bool
    landing_asymmetry: float
    row_transition: int
    left_pressed: bool = False
    right_pressed: bool = False


class GestureTracker:
    """Turns contact changes into intentionally modest sport-neutral facts."""
    def __init__(self) -> None:
        self.contacts: set[str] = set()
        self.last_step = {"left": None, "right": None}
        self.intervals: list[float] = []
        self.air_started: float | None = None
        self.row = 0
        self.previous_row = 0

    def update(self, held: set[str], now: float) -> GestureFrame:
        previous = self.contacts
        self.contacts = set(held)
        left, right = "left" in held, "right" in held
        row = 1 if "up" in held else -1 if "down" in held else 0
        left_pressed = left and "left" not in previous
        right_pressed = right and "right" not in previous
        for side, active in (("left", left), ("right", right)):
            if active and side not in previous:
                old = self.last_step[side]
                if old is not None and now > old:
                    self.intervals.append(now - old)
                    self.intervals = self.intervals[-8:]
                self.last_step[side] = now
        airborne = not left and not right
        if airborne and self.air_started is None:
            self.air_started = now
        landed = not airborne and not ({"left", "right"} & previous)
        air_time = 0.0 if self.air_started is None else now - self.air_started
        if landed:
            self.air_started = None
        cadence = 0.0 if not self.intervals else min(5.0, 1.0 / (sum(self.intervals) / len(self.intervals)))
        regularity = 0.0
        if len(self.intervals) > 1:
            mean = sum(self.intervals) / len(self.intervals)
            regularity = max(0.0, 1.0 - sum(abs(value - mean) for value in self.intervals) / len(self.intervals) / max(mean, .01))
        last_l, last_r = self.last_step["left"], self.last_step["right"]
        symmetry = 0.0 if last_l is None or last_r is None else min(1.0, abs(last_l - last_r) / .35)
        transition = row - self.previous_row
        self.previous_row, self.row = row, row
        return GestureFrame(left, right, row, cadence, regularity, symmetry, float(right) - float(left), airborne, air_time, landed, symmetry, transition, left_pressed, right_pressed)
