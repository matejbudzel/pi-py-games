"""Timing-based gameplay state, independent from Pygame rendering and devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .charts import Note


GREAT_WINDOW_SECONDS = 0.13
OK_WINDOW_SECONDS = 0.28
DOUBLE_TAP_SECONDS = 0.12
CLOSE_NOTE_GAP_SECONDS = 0.16
EDGE_WEIGHT = 0.7


class Judgement(Enum):
    GREAT = auto()
    OK = auto()
    MISS = auto()


@dataclass(frozen=True)
class JudgedNote:
    note: Note
    judgement: Judgement
    credit: float | None = None


@dataclass
class HoldProgress:
    held_seconds: float = 0.0
    edge_credit: float = 0.0


class Session:
    """Tracks pending chart notes and judges them against an audio song clock."""

    def __init__(self, notes: tuple[Note, ...]) -> None:
        self.pending = list(notes)
        self.judgements: list[JudgedNote] = []
        self.last_press_was_ignored = False
        self._last_successful_press: tuple[float, Note] | None = None
        self.active_holds: dict[str, JudgedNote] = {}
        self._hold_progress: dict[Note, HoldProgress] = {}
        self._pressed_since: dict[str, float] = {}

    def press(self, direction: str, song_time: float) -> JudgedNote | None:
        self._refresh_active_holds(song_time)
        self._pressed_since.setdefault(direction, song_time)
        if direction in self.active_holds:
            self.last_press_was_ignored = True
            return None
        self.last_press_was_ignored = self._is_accidental_double_tap(song_time)
        if self.last_press_was_ignored:
            return None
        candidates = [
            note
            for note in self.pending
            if note.direction == direction and (
                abs(note.timestamp - song_time) <= OK_WINDOW_SECONDS
                if note.end_timestamp is None
                else note.timestamp - OK_WINDOW_SECONDS <= song_time < note.end_timestamp
            )
        ]
        if not candidates:
            return None
        note = min(candidates, key=lambda candidate: abs(candidate.timestamp - song_time))
        judgement = Judgement.GREAT if abs(note.timestamp - song_time) <= GREAT_WINDOW_SECONDS else Judgement.OK
        result = JudgedNote(note=note, judgement=judgement)
        if note.end_timestamp is not None:
            progress = self._hold_progress.setdefault(note, HoldProgress())
            if not note.is_lift:
                progress.edge_credit = max(progress.edge_credit, self._edge_credit(song_time - note.timestamp))
            self._refresh_active_holds(song_time)
        else:
            self.pending.remove(note)
            self.judgements.append(result)
        self._last_successful_press = (song_time, note)
        return result

    def release(self, direction: str, song_time: float) -> JudgedNote | None:
        started_at = self._pressed_since.pop(direction, None)
        if started_at is None:
            return None
        feedback = None
        for note in list(self.pending):
            if note.timestamp > song_time + OK_WINDOW_SECONDS:
                break
            if note.direction != direction or note.end_timestamp is None:
                continue
            overlap = self._overlap(note, started_at, song_time)
            if overlap == 0 and (note.is_lift or note not in self._hold_progress):
                continue
            progress = self._hold_progress.setdefault(note, HoldProgress())
            progress.held_seconds += overlap
            if note.is_lift:
                progress.edge_credit = max(progress.edge_credit, self._edge_credit(song_time - note.end_timestamp))
            feedback = self._hold_result(note)
            finished = song_time >= note.end_timestamp - (OK_WINDOW_SECONDS if note.is_lift else GREAT_WINDOW_SECONDS)
            if finished:
                self._finish_hold(note, feedback)
        self._refresh_active_holds(song_time)
        return feedback

    def clear_pressed(self, song_time: float) -> None:
        """Preserve held time on disconnect without inventing a lift release."""
        for note in self.pending:
            started_at = self._pressed_since.get(note.direction)
            if started_at is not None and note.end_timestamp is not None:
                overlap = self._overlap(note, started_at, song_time)
                if overlap:
                    self._hold_progress.setdefault(note, HoldProgress()).held_seconds += overlap
        self._pressed_since.clear()
        self.active_holds.clear()

    @staticmethod
    def _edge_credit(error: float) -> float:
        return 1.0 if abs(error) <= GREAT_WINDOW_SECONDS else 0.5 if abs(error) <= OK_WINDOW_SECONDS else 0.0

    @staticmethod
    def _overlap(note: Note, start: float, end: float) -> float:
        return max(0.0, min(end, note.end_timestamp) - max(start, note.timestamp))

    def _refresh_active_holds(self, song_time: float) -> None:
        self.active_holds = {}
        for note in self.pending:
            if note.timestamp > song_time + OK_WINDOW_SECONDS:
                break
            if note.end_timestamp is not None and not note.is_lift and note.direction in self._pressed_since and song_time < note.end_timestamp:
                self.active_holds[note.direction] = JudgedNote(note, Judgement.OK)

    def _hold_result(self, note: Note, song_time: float | None = None) -> JudgedNote:
        progress = self._hold_progress.get(note, HoldProgress())
        duration = max(0.001, note.end_timestamp - note.timestamp)
        held_seconds = progress.held_seconds
        if song_time is not None and note.direction in self._pressed_since:
            held_seconds += self._overlap(note, self._pressed_since[note.direction], song_time)
        coverage = min(1.0, held_seconds / duration)
        # Forgive a small uncovered sliver only when the important edge was hit.
        if progress.edge_credit == 1 and duration - held_seconds <= GREAT_WINDOW_SECONDS:
            coverage = 1.0
        credit = EDGE_WEIGHT * progress.edge_credit + (1 - EDGE_WEIGHT) * coverage
        judgement = Judgement.GREAT if credit >= 0.9 else Judgement.OK if credit > 0 else Judgement.MISS
        return JudgedNote(note, judgement, credit)

    def _finish_hold(self, note: Note, result: JudgedNote) -> None:
        self.pending.remove(note)
        self._hold_progress.pop(note, None)
        self.judgements.append(result)

    def _is_accidental_double_tap(self, song_time: float) -> bool:
        if self._last_successful_press is None:
            return False
        previous_time, previous_note = self._last_successful_press
        if not 0 < song_time - previous_time <= DOUBLE_TAP_SECONDS:
            return False
        next_note = self.pending[0] if self.pending else None
        return next_note is None or next_note.timestamp - previous_note.timestamp > CLOSE_NOTE_GAP_SECONDS

    def expire(self, song_time: float) -> list[JudgedNote]:
        # A long hold must not prevent later taps from expiring on time.
        finished: list[JudgedNote] = []
        for note in self.pending:
            if note.timestamp > song_time:
                break
            if note.end_timestamp is not None:
                deadline = note.end_timestamp + (OK_WINDOW_SECONDS if note.is_lift else 0)
                if song_time >= deadline:
                    result = self._hold_result(note, song_time)
                    finished.append(result)
            elif note.timestamp < song_time - OK_WINDOW_SECONDS:
                result = JudgedNote(note=note, judgement=Judgement.MISS)
                finished.append(result)
        for result in finished:
            self.pending.remove(result.note)
            self._hold_progress.pop(result.note, None)
            self.judgements.append(result)
        self._refresh_active_holds(song_time)
        return finished

    def stars(self) -> int:
        if not self.judgements:
            return 1
        score = sum(2 * result.credit if result.credit is not None else 2 if result.judgement is Judgement.GREAT else 1 if result.judgement is Judgement.OK else 0 for result in self.judgements)
        return 1 + round(4 * score / (2 * len(self.judgements)))
