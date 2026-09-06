#!/usr/bin/env python3
"""Print an alphabetical inventory of song bundles and their files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class SongInventory:
    title: str
    folder: Path
    assets: tuple[Path, ...]
    problem: str | None = None


def read_inventory(song_directory: Path) -> list[SongInventory]:
    """Read immediate song-bundle folders, ordered by their displayed title."""
    if not song_directory.is_dir():
        raise FileNotFoundError(f"song directory does not exist: {song_directory}")

    songs: list[SongInventory] = []
    for folder in song_directory.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        title = folder.name
        problem: str | None = None
        metadata_path = folder / "song.json"
        if not metadata_path.is_file():
            problem = "missing song.json"
        else:
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata_title = metadata.get("title")
                if not isinstance(metadata_title, str) or not metadata_title.strip():
                    problem = "song.json has no usable title"
                else:
                    title = metadata_title.strip()
            except (OSError, json.JSONDecodeError):
                problem = "invalid song.json"

        assets = tuple(sorted(
            (path.relative_to(folder) for path in folder.rglob("*") if path.is_file()),
            key=lambda path: str(path).casefold(),
        ))
        songs.append(SongInventory(title=title, folder=folder, assets=assets, problem=problem))

    return sorted(songs, key=lambda song: (song.title.casefold(), song.folder.name.casefold()))


def print_inventory(song_directory: Path) -> None:
    """Print a readable inventory for ``song_directory``."""
    songs = read_inventory(song_directory)
    if not songs:
        print("No song folders found.")
        return

    for song in songs:
        print(song.title)
        print(f"  Folder: {song.folder}")
        print(f"  Assets: {', '.join(map(str, song.assets)) or '(none)'}")
        if song.problem:
            print(f"  Note: {song.problem}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Pi-Dance song bundles and their assets.")
    parser.add_argument(
        "song_directory",
        nargs="?",
        type=Path,
        default=Path("songs"),
        help="song directory to inspect (default: songs)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        print_inventory(args.song_directory)
    except FileNotFoundError as error:
        print(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
