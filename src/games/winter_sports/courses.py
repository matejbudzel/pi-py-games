"""Data-only tracks and sport response profiles."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    length: float
    curve: float = 0.0
    width: float = 8.0
    feature: str = ""


@dataclass(frozen=True)
class Course:
    name: str
    segments: tuple[Segment, ...]
    def center_at(self, distance: float) -> tuple[float, float, Segment]:
        x = 0.0
        remaining = distance
        for index, segment in enumerate(self.segments):
            used = min(segment.length, max(0.0, remaining))
            x += segment.curve * used * used / 100.0
            if remaining <= segment.length:
                return x, sum(s.length for s in self.segments[:index]) + used, segment
            remaining -= segment.length
        return x, sum(s.length for s in self.segments), self.segments[-1]
    @property
    def length(self) -> float:
        return sum(segment.length for segment in self.segments)


@dataclass(frozen=True)
class Profile:
    acceleration: float
    steer: float
    inertia: float
    stability: float
    max_speed: float


COURSES = {
    "Bobsleigh": (Course("Ice Canyon", (Segment(80), Segment(100, .7), Segment(110, -.9), Segment(70, .35))), Course("Blue Chute", (Segment(70, -.6), Segment(120, .8), Segment(90, -.4)))),
    "Luge": (Course("Ice Canyon", (Segment(80), Segment(100, .7), Segment(110, -.9), Segment(70, .35))),),
    "Skeleton": (Course("Blue Chute", (Segment(70, -.6), Segment(120, .8), Segment(90, -.4))),),
    "Short track": (Course("500 m", ()), Course("1000 m", ()), Course("1500 m", ())),
    "Speed skating": (Course("500 m", ()), Course("1000 m", ()), Course("1500 m", ())),
    "Alpine skiing": (Course("Slalom", (Segment(55, 1.2, 6), Segment(55, -1.2, 6), Segment(65, 1.0, 6), Segment(60, -.8, 6))), Course("Downhill", (Segment(110, .3, 10), Segment(110, -.45, 10), Segment(100, .35, 9)))),
    "Snowboard slalom": (Course("Boarder", (Segment(70, 1.0, 7), Segment(70, -1.0, 7), Segment(70, .8, 7))),),
    "Ski cross": (Course("Roller Run", (Segment(60, .4), Segment(40, -.8, 7, "jump"), Segment(80, .8, 7), Segment(45, -.5, 7, "jump"))),),
    "Ski jumping": (Course("Small Hill", (Segment(100), Segment(35, 0, 8, "takeoff"), Segment(130, 0, 12, "landing"))), Course("Large Hill", (Segment(140), Segment(40, 0, 8, "takeoff"), Segment(180, 0, 14, "landing")))),
}
PROFILES = {
    "Bobsleigh": Profile(7, 1.0, 3.5, 1.0, 22), "Luge": Profile(6, 1.8, 1.6, .75, 20), "Skeleton": Profile(6, 2.2, 1.2, .62, 21),
    "Short track": Profile(6, 1.3, 2.2, .9, 23), "Speed skating": Profile(6, 1.3, 2.2, .9, 23), "Alpine skiing": Profile(5, 1.5, 2.0, .9, 20), "Snowboard slalom": Profile(4, 1.0, 3.7, .8, 18),
    "Ski cross": Profile(6, 1.5, 2.0, .72, 21), "Ski jumping": Profile(7, .8, 2.0, .8, 24),
}
