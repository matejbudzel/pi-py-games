"""Speed-skating-specific oval geometry and continuous input physics."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin

from .gestures import GestureFrame


@dataclass(frozen=True)
class Oval:
    name: str
    lap_metres: float
    turn_radius: float
    straight_metres: float
    track_width: float
    cadence_gain: float
    curve_loss: float
    airborne_loss: float
    inertia: float
    imbalance_gain: float
    wall_speed_factor: float
    record_seconds: float

    @property
    def target_seconds(self) -> float:
        return self.record_seconds * 1.10


# 111.12 m is the ISU short-track racing line: two 30.427 m straights and
# two 8 m-radius semicircles.  A 400 m long track uses 25 m-radius turns.
SHORT_TRACK = Oval("Short Track", 111.12, 8.0, 30.427, 7.0, 8.8, 1.20, 1.7, 1.3, .24, .12, 41.399)
LONG_TRACK = Oval("Large Oval", 400.0, 25.0, 121.460, 8.0, 6.6, .42, 1.1, 3.8, .15, .10, 36.09)
OVALS = {SHORT_TRACK.name: SHORT_TRACK, LONG_TRACK.name: LONG_TRACK}


def point_at(oval: Oval, distance: float, offset: float = 0.0) -> tuple[float, float, float]:
    """World x/y and tangent heading for a clockwise stadium racing line."""
    lap = distance % oval.lap_metres
    half = oval.straight_metres / 2
    first_straight = oval.straight_metres
    curve = pi * oval.turn_radius
    # Start at the middle of the bottom straight, travelling right.  The long
    # straights remain horizontal, so the rounded ends visibly sit top/bottom.
    if lap < first_straight:
        x, y, heading = -half + lap, oval.turn_radius, 0.0
    elif lap < first_straight + curve:
        angle = pi / 2 - (lap - first_straight) / oval.turn_radius
        x, y, heading = half + oval.turn_radius * cos(angle), oval.turn_radius * sin(angle), angle - pi / 2
    elif lap < 2 * first_straight + curve:
        used = lap - first_straight - curve
        x, y, heading = half - used, -oval.turn_radius, pi
    else:
        angle = -pi / 2 - (lap - 2 * first_straight - curve) / oval.turn_radius
        x, y, heading = -half + oval.turn_radius * cos(angle), oval.turn_radius * sin(angle), angle - pi / 2
    # The normal points across the lane, which lets the camera and renderer
    # stay in world coordinates while the skater shifts toward a border.
    return x - sin(heading) * offset, y + cos(heading) * offset, heading


@dataclass
class SpeedSkatingRun:
    oval: Oval
    distance: float = 0.0
    speed: float = 0.0
    offset: float = 0.0
    balance: float = 0.0
    elapsed: float = 0.0
    collisions: int = 0

    def update(self, dt: float, gesture: GestureFrame) -> None:
        self.elapsed += dt
        both = gesture.left and gesture.right
        one = gesture.left != gesture.right
        # A single-foot press while the other foot remains planted makes a
        # small, persistent edge change toward that foot.
        if gesture.left_pressed and gesture.right:
            self.balance -= self.oval.imbalance_gain
        if gesture.right_pressed and gesture.left:
            self.balance += self.oval.imbalance_gain
        self.balance += gesture.lean * .45 * dt
        self.balance *= max(0.0, 1.0 - dt / self.oval.inertia)
        _, _, heading = point_at(self.oval, self.distance)
        curve = abs(sin(heading))
        direction_error = min(1.0, abs(self.balance))
        if one:
            cadence = min(1.0, gesture.cadence / 3.2) * gesture.regularity
            thrust = self.oval.cadence_gain * cadence * (1.0 - direction_error * .55)
            drag = .20 + curve * self.oval.curve_loss * direction_error
        elif both:
            thrust, drag = 0.0, .65
        else:
            # A tiny hop is only a light coast; staying airborne compounds
            # drag rapidly and ends in a stop instead of a useful exploit.
            thrust = 0.0
            drag = self.oval.airborne_loss * (1.0 + gesture.airborne_seconds * 3.5)
        self.speed += (thrust - drag - self.speed / (18 * self.oval.inertia)) * dt
        self.speed = max(0.0, min(15.5, self.speed))
        self.offset += self.balance * self.speed * .06 * dt
        border = self.oval.track_width / 2
        if abs(self.offset) > border:
            self.offset = (border if self.offset > 0 else -border) * .82
            self.speed *= self.oval.wall_speed_factor
            self.balance *= -.35
            self.collisions += 1
        self.distance += self.speed * dt

    @property
    def complete(self) -> bool:
        return self.distance >= 500.0

    def stars(self) -> int:
        ratio = self.elapsed / self.oval.target_seconds
        return max(1, min(5, 5 - self.collisions - max(0, int(ratio - 1.0))))
