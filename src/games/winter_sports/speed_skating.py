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
    start_before_finish: float

    @property
    def target_seconds(self) -> float:
        return self.record_seconds * 1.10


# 111.12 m is the ISU short-track racing line: two 30.427 m straights and
# two 8 m-radius semicircles.  A 400 m long track uses 25 m-radius turns.
SHORT_TRACK = Oval("Short Track", 111.12, 8.0, 30.427, 7.0, 8.8, 1.20, 1.7, 1.3, .24, .12, 41.399, 55.56)
LONG_TRACK = Oval("Large Oval", 400.0, 25.0, 121.460, 8.0, 6.6, .42, 1.1, 3.8, .15, .10, 36.09, 100.0)
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


def closest_centerline(oval: Oval, x: float, y: float) -> tuple[float, float, float, float]:
    """Return nearest sampled racing-line point, heading, and distance error."""
    best: tuple[float, float, float, float] | None = None
    # This small fixed sample count is stable on a Pi and intentionally avoids
    # turning the renderer's pixels into simulation state.
    for index in range(96):
        distance = oval.lap_metres * index / 96
        center_x, center_y, heading = point_at(oval, distance)
        error = (x - center_x) ** 2 + (y - center_y) ** 2
        if best is None or error < best[3]:
            best = (distance, center_x, center_y, error)
    assert best is not None
    distance, center_x, center_y, error = best
    _, _, heading = point_at(oval, distance)
    return distance, center_x, center_y, error ** .5


@dataclass
class SpeedSkatingRun:
    oval: Oval
    speed: float = 0.0
    balance: float = 0.0
    elapsed: float = 0.0
    travelled: float = 0.0
    collisions: int = 0
    reverse_warning: bool = False
    wall_contact: bool = False

    def __post_init__(self) -> None:
        self.start_distance = self.oval.lap_metres - self.oval.start_before_finish
        self.x, self.y, self.heading = point_at(self.oval, self.start_distance)
        self.previous_x, self.previous_y = self.x, self.y

    def update(self, dt: float, gesture: GestureFrame) -> None:
        self.elapsed += dt
        both, one = gesture.left and gesture.right, gesture.left != gesture.right
        # Right-foot strokes while the left stays planted apply a left turn;
        # left-foot strokes do the mirror-image correction.
        if gesture.left_pressed and gesture.right:
            self.balance -= self.oval.imbalance_gain
        if gesture.right_pressed and gesture.left:
            self.balance += self.oval.imbalance_gain
        self.balance *= max(0.0, 1.0 - dt / (self.oval.inertia * 1.6))
        line_distance, center_x, center_y, line_error = closest_centerline(self.oval, self.x, self.y)
        _, _, ideal_heading = point_at(self.oval, line_distance)
        direction_error = abs(sin(self.heading - ideal_heading))
        self.reverse_warning = cos(self.heading - ideal_heading) < 0.0
        if one and not self.reverse_warning:
            cadence = min(1.0, gesture.cadence / 3.2) * gesture.regularity
            thrust = self.oval.cadence_gain * cadence * (1.0 - direction_error * .70)
            drag = .20 + direction_error * self.oval.curve_loss
        elif both:
            thrust, drag = 0.0, .65
        else:
            thrust = 0.0
            drag = self.oval.airborne_loss * (1.0 + gesture.airborne_seconds * 3.5)
        self.speed += (thrust - drag - self.speed / (18 * self.oval.inertia)) * dt
        self.speed = max(0.0, min(15.5, self.speed))
        # Heading is never pulled toward the track.  It changes only through
        # player input, and can point anywhere—including a warned reverse.
        turn_multiplier = 3.8 if self.wall_contact else 1.0
        self.heading -= self.balance * (1.3 + self.speed * .10) * turn_multiplier * dt
        self.previous_x, self.previous_y = self.x, self.y
        self.x += cos(self.heading) * self.speed * dt
        self.y += sin(self.heading) * self.speed * dt
        self.travelled += self.speed * dt
        _, center_x, center_y, line_error = closest_centerline(self.oval, self.x, self.y)
        self.wall_contact = line_error > self.oval.track_width / 2
        if self.wall_contact:
            # A collision is costly but never strands the skater beyond the
            # border.  Put them just inside the lane along the collision ray.
            away_x, away_y = self.x - center_x, self.y - center_y
            length = max(.001, (away_x * away_x + away_y * away_y) ** .5)
            safe_distance = self.oval.track_width * .42
            self.x = center_x + away_x / length * safe_distance
            self.y = center_y + away_y / length * safe_distance
            self.speed *= self.oval.wall_speed_factor
            self.balance *= .75
            self.collisions += 1

    @property
    def complete(self) -> bool:
        # The player must cross the fixed finish line in the correct direction,
        # not simply accumulate enough movement while circling somewhere else.
        crosses_finish = self.previous_x < 0 <= self.x and abs(self.y - self.oval.turn_radius) < self.oval.track_width
        return self.travelled >= 500.0 and crosses_finish and not self.reverse_warning

    def stars(self) -> int:
        ratio = self.elapsed / self.oval.target_seconds
        return max(1, min(5, 5 - self.collisions - max(0, int(ratio - 1.0))))
