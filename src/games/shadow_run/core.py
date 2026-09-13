"""Pure runner rules: safe stances, beat-led terrain, stamina and score."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import random


class Lane(Enum):
    LEFT = 0
    CENTER = 1
    RIGHT = 2


Stance = tuple[Lane, Lane]
STANCES: tuple[Stance, ...] = (
    (Lane.LEFT, Lane.LEFT), (Lane.LEFT, Lane.CENTER), (Lane.LEFT, Lane.RIGHT),
    (Lane.CENTER, Lane.CENTER), (Lane.CENTER, Lane.RIGHT), (Lane.RIGHT, Lane.RIGHT),
)


def normalise_stance(lanes: tuple[Lane, Lane] | list[Lane] | set[Lane]) -> Stance | None:
    """Canonicalise contacts. One distinct contact is a wide-lane double foot stance."""
    values = sorted(lanes, key=lambda lane: lane.value)
    if not values or len(values) > 2:
        return None
    if len(values) == 1:
        return (values[0], values[0])
    return (values[0], values[1])


def is_valid_stance(contacts: set[Lane] | Mapping[Lane, int], required: Stance) -> bool:
    """Require one physical contact for each foot in the planned stance."""
    counts = dict(contacts) if isinstance(contacts, Mapping) else {lane: 1 for lane in contacts}
    required_counts = {lane: required.count(lane) for lane in set(required)}
    # One real foot can overlap two panels in its broad lane.  Those duplicate
    # signals are harmless, but a double-foot single-lane stance still needs
    # two independent contacts in that lane.
    return (
        all(lane in required_counts for lane, count in counts.items() if count > 0)
        and all(counts.get(lane, 0) >= needed for lane, needed in required_counts.items())
    )


def is_safe_transition(current: Stance, next_stance: Stance) -> bool:
    """At least one foot lane remains: never ask both feet to move at once."""
    return bool(set(current) & set(next_stance)) and current != next_stance


def reachable_stances(current: Stance, *, include_single_lane: bool = False) -> tuple[Stance, ...]:
    choices = [stance for stance in STANCES if is_safe_transition(current, stance)]
    if not include_single_lane:
        choices = [stance for stance in choices if stance[0] != stance[1]]
    return tuple(choices)


def lane_contacts(actions: set[str]) -> set[Lane]:
    """Map shared cardinal pad actions into broad physical mat lanes."""
    result: set[Lane] = set()
    if "left" in actions:
        result.add(Lane.LEFT)
    if "right" in actions:
        result.add(Lane.RIGHT)
    if "up" in actions or "down" in actions:
        result.add(Lane.CENTER)
    return result


@dataclass(frozen=True)
class Beat:
    time: float
    strength: float = 0.0
    accent: bool = False


@dataclass(frozen=True)
class Difficulty:
    speed: float
    min_segment: float
    transition_window: float
    single_lane_chance: float


def difficulty_at(song_time: float, duration: float) -> Difficulty:
    progress = min(1.0, max(0.0, song_time / max(duration, 1.0)))
    return Difficulty(30 + 14 * progress, 2.7 - 0.9 * progress, 0.72 - 0.20 * progress, 0.03 + 0.14 * progress)


def scroll_distance(song_time: float, duration: float) -> float:
    """Pixels travelled under the linear speed curve used by difficulty_at."""
    time = min(max(song_time, 0.0), duration)
    return 30.0 * time + 7.0 * time * time / max(duration, 1.0)


def time_at_scroll_distance(distance: float, duration: float) -> float:
    """Inverse of scroll_distance, used while building fixed terrain rows."""
    distance = max(0.0, distance)
    duration = max(duration, 1.0)
    # 7/duration * t² + 30t - distance = 0
    return min(duration, (-30.0 + (900.0 + 28.0 * distance / duration) ** 0.5) * duration / 14.0)


def stars_for_performance(correct_seconds: float, duration: float, stamina: float) -> int:
    """Turn hidden run performance into a friendly, always-positive result."""
    if duration <= 0:
        return 1
    correct_ratio = min(1.0, max(0.0, correct_seconds / duration))
    stamina_ratio = min(1.0, max(0.0, stamina / 100.0))
    combined = correct_ratio * 0.55 + stamina_ratio * 0.45
    return 1 + min(4, int(combined * 4 + 0.5))


class TerrainGenerator:
    def __init__(self, beats: tuple[Beat, ...] = (), seed: int | None = None) -> None:
        self.beats, self.rng = beats, random.Random(seed)
        self.stance: Stance = (Lane.LEFT, Lane.CENTER)
        self.last_change = 0.0
        self._beat_index = 0
        self._due_time = 0.0

    def due(self, song_time: float, duration: float) -> bool:
        difficulty = difficulty_at(song_time, duration)
        if song_time - self.last_change < difficulty.min_segment:
            return False
        while self._beat_index < len(self.beats) and self.beats[self._beat_index].time < song_time - 0.12:
            self._beat_index += 1
        if self._beat_index < len(self.beats):
            beat = self.beats[self._beat_index]
            if abs(beat.time - song_time) <= 0.12 and (beat.accent or beat.strength >= 0.55):
                self._beat_index += 1
                # Store the source timestamp, rather than the frame/planning
                # timestamp, so a prepared map has exact musical boundaries.
                self._due_time = beat.time
                return True
        if song_time - self.last_change >= difficulty.min_segment + 1.8:
            self._due_time = song_time
            return True
        return False

    def advance(self, song_time: float, duration: float) -> Stance | None:
        if not self.due(song_time, duration):
            return None
        choices = reachable_stances(self.stance, include_single_lane=self.rng.random() < difficulty_at(song_time, duration).single_lane_chance)
        self.stance = self.rng.choice(choices)
        self.last_change = self._due_time
        return self.stance


@dataclass(frozen=True)
class TerrainChange:
    time: float
    stance: Stance


class TerrainTimeline:
    """Plans terrain ahead of the receptor without changing the active stance early."""
    def __init__(self, beats: tuple[Beat, ...] = (), seed: int | None = None) -> None:
        self.generator = TerrainGenerator(beats, seed)
        self.initial_stance = self.generator.stance
        self.changes: list[TerrainChange] = []
        self.planned_until = 0.0

    def plan_to(self, horizon: float, duration: float) -> None:
        """Fill a look-ahead horizon in small deterministic time increments."""
        while self.planned_until < horizon:
            self.planned_until = min(horizon, self.planned_until + 0.10)
            stance = self.generator.advance(self.planned_until, duration)
            if stance is not None:
                self.changes.append(TerrainChange(self.generator.last_change, stance))

    def prepare_song(self, duration: float) -> None:
        """Build the complete immutable terrain map before audio begins."""
        self.plan_to(duration, duration)

    def tile_stances(self, duration: float, tile_size: int) -> tuple[Stance, ...]:
        """Return a fixed stance for every scrolling tile row in a song.

        A row is never recoloured after this preparation step.  Its assigned
        stance is the one needed when that row reaches the receptor.
        """
        if tile_size <= 0:
            raise ValueError("tile_size must be positive")
        row_count = int(scroll_distance(duration, duration) / tile_size) + 3
        return tuple(
            self.stance_at(time_at_scroll_distance(row * tile_size, duration))
            for row in range(row_count)
        )

    def stance_at(self, song_time: float) -> Stance:
        stance = self.initial_stance
        for change in self.changes:
            if change.time > song_time:
                break
            stance = change.stance
        return stance

    def latest_change_at(self, song_time: float) -> TerrainChange | None:
        latest = None
        for change in self.changes:
            if change.time > song_time:
                break
            latest = change
        return latest

    def in_transition_window(self, song_time: float, duration: float) -> bool:
        return any(abs(change.time - song_time) <= difficulty_at(change.time, duration).transition_window for change in self.changes)


@dataclass
class Stamina:
    value: float = 100.0
    correct_since: float | None = None

    def update(self, now: float, delta: float, valid: bool, transition_open: bool) -> None:
        if valid or transition_open:
            if valid:
                self.correct_since = self.correct_since if self.correct_since is not None else now
            if self.correct_since is not None and now - self.correct_since > 2.0:
                self.value = min(100.0, self.value + 4.0 * delta)
        else:
            self.correct_since = None
            # A missed stance should be recoverable for young players: it takes
            # about three times as long to exhaust the full stamina bar.
            self.value = max(0.0, self.value - 6.0 * delta)
