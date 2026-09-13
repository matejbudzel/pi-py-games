"""Continuous, deterministic event simulation independent of rendering."""
from __future__ import annotations
from dataclasses import dataclass
import random
from .courses import Course, Profile
from .gestures import GestureFrame

@dataclass
class Run:
    course: Course
    profile: Profile
    tuning: dict[str, float]
    seed: int
    distance: float = 0.0
    lateral: float = 0.0
    lateral_velocity: float = 0.0
    speed: float = 0.0
    balance: float = 0.0
    airborne: float = 0.0
    falls: int = 0
    def __post_init__(self) -> None:
        self.random = random.Random(self.seed)
        self.wind = self.random.uniform(-1, 1) * self.tuning["wind"]
    def update(self, dt: float, gesture: GestureFrame, sport: str) -> None:
        _, _, segment = self.course.center_at(self.distance)
        cadence = min(1.0, gesture.cadence / 3.0) * gesture.regularity
        propulsion = cadence if sport in ("Bobsleigh", "Speed skating") or self.distance < 15 else .25
        if sport == "Ski jumping" and self.distance < 20: propulsion = cadence
        if gesture.airborne:
            self.airborne += dt
            if sport in ("Bobsleigh", "Luge", "Skeleton"): propulsion *= .15
        elif gesture.landed:
            self.airborne = 0.0
            self.balance += gesture.landing_asymmetry * 1.5
        steer = gesture.lean * self.profile.steer * self.tuning["steering"]
        required = segment.curve * min(1.0, self.speed / self.profile.max_speed)
        self.balance += (steer - required - self.balance / self.profile.stability + self.wind * .12) * dt
        self.lateral_velocity += (steer - required - self.lateral_velocity / self.profile.inertia) * dt
        self.lateral += self.lateral_velocity * dt
        error = abs(self.lateral) / max(segment.width, 1) + abs(self.balance) * .35
        self.speed += (self.profile.acceleration * (0.22 + propulsion * self.tuning["cadence"]) - self.speed * .11 - error * 1.2) * dt
        self.speed = max(1.0, min(self.profile.max_speed, self.speed))
        if error > 1.25:
            self.speed *= .72
            self.balance *= .5
            self.lateral *= .65
            self.falls += 1
        self.distance += self.speed * dt
    @property
    def complete(self) -> bool: return self.distance >= self.course.length
    def stars(self) -> int:
        return max(1, min(5, 5 - self.falls - int(abs(self.lateral) / 3)))
