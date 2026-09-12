"""Runtime reading of lightweight `.shadow.json` preparation sidecars."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from .core import Beat

SIDECAR_SUFFIX = ".shadow.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Song:
    title: str
    audio_path: Path
    sidecar_path: Path
    duration: float
    tempo_bpm: float
    beats: tuple[Beat, ...]


def sidecar_path_for(audio: Path) -> Path:
    return audio.with_suffix(SIDECAR_SUFFIX)


def load_song(audio: Path) -> Song | None:
    try:
        document = json.loads(sidecar_path_for(audio).read_text(encoding="utf-8"))
        source = document["source"]
        if document["schema_version"] != SCHEMA_VERSION or source["file"] != audio.name or source["size"] != audio.stat().st_size or source["mtime_ns"] != audio.stat().st_mtime_ns:
            return None
        duration, tempo = float(document["duration"]), float(document["tempo_bpm"])
        if not math.isfinite(duration) or duration <= 0 or not math.isfinite(tempo) or tempo <= 0:
            return None
        beats = tuple(Beat(float(item["time"]), float(item.get("strength", 0)), bool(item.get("accent", False))) for item in document["beats"])
        if any(not math.isfinite(beat.time) or beat.time < 0 for beat in beats):
            return None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return Song(audio.stem, audio, sidecar_path_for(audio), duration, tempo, beats)


def discover_songs(directory: Path) -> list[Song]:
    if not directory.is_dir():
        return []
    return sorted((song for audio in directory.rglob("*.wav") if (song := load_song(audio)) is not None), key=lambda song: song.title.casefold())
