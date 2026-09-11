"""Small StepMania .sm parser for dance-single taps, holds and lifts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PANEL_DIRECTIONS = ("left", "down", "up", "right")
DIFFICULTY_ORDER = {"beginner": 0, "easy": 1, "medium": 2, "hard": 3, "challenge": 4, "edit": 5}


@dataclass(frozen=True)
class Note:
    timestamp: float
    direction: str
    end_timestamp: float | None = None
    is_lift: bool = False

    @property
    def arrow_timestamp(self) -> float:
        return self.end_timestamp if self.is_lift else self.timestamp


@dataclass(frozen=True)
class Chart:
    difficulty: str
    meter: int
    notes: tuple[Note, ...]


@dataclass(frozen=True)
class SongCharts:
    offset: float
    charts: tuple[Chart, ...]


def difficulty_key(chart: Chart) -> tuple[int, int]:
    return DIFFICULTY_ORDER.get(chart.difficulty.casefold(), 99), chart.meter


def load_sm(path: Path) -> SongCharts:
    return parse_sm(path.read_text(encoding="utf-8-sig"))


def parse_sm(contents: str) -> SongCharts:
    """Parse timing and every usable dance-single chart from a StepMania file."""
    offset = float(_tag_value(contents, "OFFSET") or 0)
    bpm_changes = _parse_bpms(_tag_value(contents, "BPMS"))
    charts = tuple(
        chart
        for notes_block in re.findall(r"#NOTES\s*:(.*?);", contents, flags=re.IGNORECASE | re.DOTALL)
        if (chart := _parse_chart(notes_block, bpm_changes, offset)) is not None
    )
    return SongCharts(offset=offset, charts=charts)


def _tag_value(contents: str, name: str) -> str | None:
    match = re.search(rf"#{re.escape(name)}\s*:(.*?);", contents, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def _parse_bpms(value: str | None) -> tuple[tuple[float, float], ...]:
    if not value:
        raise ValueError("missing #BPMS tag")
    changes: list[tuple[float, float]] = []
    for entry in value.replace("\n", "").split(","):
        beat_text, separator, bpm_text = entry.strip().partition("=")
        if not separator:
            raise ValueError(f"invalid BPM entry: {entry!r}")
        beat, bpm = float(beat_text), float(bpm_text)
        if bpm <= 0:
            raise ValueError("BPM must be positive")
        changes.append((beat, bpm))
    changes.sort()
    if not changes or changes[0][0] != 0:
        raise ValueError("#BPMS must start at beat 0")
    return tuple(changes)


def _parse_chart(notes_block: str, bpm_changes: tuple[tuple[float, float], ...], offset: float) -> Chart | None:
    fields = notes_block.split(":", 5)
    if len(fields) != 6 or fields[0].strip().lower() != "dance-single":
        return None
    try:
        meter = int(fields[3].strip())
    except ValueError as error:
        raise ValueError(f"invalid chart meter: {fields[3]!r}") from error

    notes: list[Note] = []
    holds: dict[int, int] = {}
    measures = fields[5].split(",")
    for measure_index, measure in enumerate(measures):
        rows = _note_rows(measure)
        if not rows:
            continue
        for row_index, row in enumerate(rows):
            beat = measure_index * 4 + row_index * 4 / len(rows)
            timestamp = _seconds_at_beat(beat, bpm_changes) + offset
            for panel, value in enumerate(row):
                if value == "1":
                    notes.append(Note(timestamp=timestamp, direction=PANEL_DIRECTIONS[panel]))
                elif value == "L":
                    # SM stores only the release edge. Supply a one-beat lead-in.
                    start = _seconds_at_beat(beat - 1, bpm_changes) + offset
                    previous = next((note for note in reversed(notes) if note.direction == PANEL_DIRECTIONS[panel]), None)
                    if previous is not None:
                        start = max(start, previous.end_timestamp if previous.end_timestamp is not None else previous.timestamp)
                    notes.append(Note(min(start, timestamp - 0.001), PANEL_DIRECTIONS[panel], timestamp, is_lift=True))
                elif value == "2":
                    holds[panel] = len(notes)
                    notes.append(Note(timestamp=timestamp, direction=PANEL_DIRECTIONS[panel]))
                elif value == "3" and panel in holds:
                    index = holds.pop(panel)
                    head = notes[index]
                    notes[index] = Note(head.timestamp, head.direction, timestamp)
    return Chart(difficulty=fields[2].strip(), meter=meter, notes=tuple(sorted(notes, key=lambda note: note.timestamp)))


def _note_rows(measure: str) -> list[str]:
    rows: list[str] = []
    for line in measure.splitlines():
        row = line.split("//", 1)[0].strip()
        if row:
            if len(row) != 4 or any(value not in "01234MLFK" for value in row):
                raise ValueError(f"invalid dance-single note row: {row!r}")
            rows.append(row)
    return rows


def _seconds_at_beat(beat: float, bpm_changes: tuple[tuple[float, float], ...]) -> float:
    seconds = 0.0
    previous_beat, previous_bpm = bpm_changes[0]
    for change_beat, change_bpm in bpm_changes[1:]:
        if beat <= change_beat:
            return seconds + (beat - previous_beat) * 60 / previous_bpm
        seconds += (change_beat - previous_beat) * 60 / previous_bpm
        previous_beat, previous_bpm = change_beat, change_bpm
    return seconds + (beat - previous_beat) * 60 / previous_bpm
