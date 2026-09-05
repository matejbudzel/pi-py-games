"""Discovery of prepared external song bundles."""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Song:
    title: str
    path: Path
    focus_color: tuple[int, int, int]
    audio_path: Path
    chart_path: Path
    cover_path: Path
    duration_seconds: float


def focus_color_for_title(title: str) -> tuple[int, int, int]:
    """Create a stable, high-contrast colour from a song's displayed title."""
    hue = int.from_bytes(hashlib.blake2s(title.encode("utf-8"), digest_size=2).digest(), "big") / 65536
    return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.72, 1.0))


def fallback_cover_path() -> Path:
    return Path(__file__).parent / "assets" / "gameplay" / "fallback-cover.bmp"


def discover_songs(song_directory: Path) -> list[Song]:
    """Return valid prepared songs, sorted by their displayed title.

    A malformed or incomplete external bundle must not stop the game menu from
    opening, so invalid entries are ignored here.
    """
    if not song_directory.is_dir():
        return []

    songs: list[Song] = []
    for bundle in song_directory.iterdir():
        metadata_path = bundle / "song.json"
        if not bundle.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            title = metadata["title"]
            audio = metadata["audio"]
            chart = metadata["chart"]
            cover = metadata.get("cover", "song.bmp")
            duration_seconds = float(metadata["duration_seconds"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(audio, str) or not isinstance(chart, str) or not isinstance(cover, str) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
            continue
        if not (bundle / audio).is_file() or not (bundle / chart).is_file():
            continue
        clean_title = title.strip()
        resolved_cover = bundle / cover
        if not resolved_cover.is_file():
            resolved_cover = fallback_cover_path()
        songs.append(
            Song(
                title=clean_title,
                path=bundle,
                focus_color=focus_color_for_title(clean_title),
                audio_path=bundle / audio,
                chart_path=bundle / chart,
                cover_path=resolved_cover,
                duration_seconds=duration_seconds,
            )
        )
    return sorted(songs, key=lambda song: song.title.casefold())
