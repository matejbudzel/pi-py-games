#!/usr/bin/env python3
"""Prepare bare MP3 song folders using their embedded ID3 title and artist tags.

This deliberately writes only redistributable runtime derivatives next to the
external source MP3: ``song.wav``, ``song.bmp`` and ``song.json``.  Run
``generate_auto_charts.py`` afterwards to create the referenced ``song.sm``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from prepare_songs import (
    WAV_CHANNELS,
    WAV_CODEC,
    WAV_SAMPLE_RATE,
    audio_duration_seconds,
    fallback_cover_path,
    input_audio,
    input_cover,
    wav_matches_runtime_format,
)


def id3_tags(audio_path: Path) -> tuple[str, str]:
    """Read title/artist via ffprobe, which exposes MP3 ID3 metadata."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist", "-of", "json", str(audio_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = json.loads(result.stdout).get("format", {}).get("tags", {})
    title = tags.get("title", "").strip()
    artist = tags.get("artist", "").strip()
    if not title:
        raise ValueError("MP3 has no usable ID3 title tag")
    return title, artist


def prepare_song(song_dir: Path, overwrite: bool) -> None:
    source = input_audio(song_dir)
    title, artist = id3_tags(source)
    wav_path, cover_path, metadata_path = song_dir / "song.wav", song_dir / "song.bmp", song_dir / "song.json"
    metadata = {
        "title": title,
        "artist": artist,
        "duration_seconds": audio_duration_seconds(source),
        "audio": wav_path.name,
        "chart": "song.sm",
        "chart_style": "dance-single",
        "cover": cover_path.name,
        "source_url": None,
    }
    needs_wav = overwrite or not wav_path.exists() or not wav_matches_runtime_format(wav_path)
    needs_cover = overwrite or not cover_path.exists()
    needs_metadata = overwrite or not metadata_path.exists()
    print(f"{song_dir.name}: {title} — WAV {'create' if needs_wav else 'keep'}, cover {'create' if needs_cover else 'keep'}, metadata {'write' if needs_metadata else 'keep'}")
    with TemporaryDirectory(prefix=".prepare-id3-", dir=song_dir) as temporary:
        staging = Path(temporary)
        if needs_wav:
            converted = staging / wav_path.name
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-acodec", WAV_CODEC, "-ar", str(WAV_SAMPLE_RATE), "-ac", str(WAV_CHANNELS), str(converted)], check=True)
            converted.replace(wav_path)
        if needs_cover:
            source_cover = input_cover(song_dir)
            converted = staging / cover_path.name
            if source_cover:
                # A bare MP3 import normally has no cover; retain a supplied image if present.
                from prepare_songs import create_cover
                create_cover(source_cover, converted)
            else:
                shutil.copyfile(fallback_cover_path(), converted)
            converted.replace(cover_path)
        if needs_metadata:
            converted = staging / metadata_path.name
            converted.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            converted.replace(metadata_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("song_directory", type=Path, nargs="+", help="one or more bare-MP3 song folders")
    parser.add_argument("--overwrite", action="store_true", help="replace generated runtime files")
    args = parser.parse_args()
    for song_dir in args.song_directory:
        prepare_song(song_dir, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
