#!/usr/bin/env python3
"""Create Pi-Dance runtime files from downloaded StepMania song bundles.

The input directory is deliberately external to the repository: it may contain
copyrighted audio and community charts. This tool preserves downloaded source
files and creates ``song.wav``, ``song.bmp``, and ``song.json`` alongside them.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


AUDIO_EXTENSIONS = (".ogg", ".mp3")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")
WAV_CODEC = "pcm_s16le"
WAV_SAMPLE_RATE = 22050
WAV_CHANNELS = 2
DIFFICULTY_ORDER = {
    "beginner": 0,
    "easy": 1,
    "medium": 2,
    "hard": 3,
    "challenge": 4,
    "edit": 5,
}


@dataclass(frozen=True)
class ChartChoice:
    difficulty: str
    meter: int


def sm_tag(contents: str, name: str) -> str | None:
    """Return a simple StepMania tag value, if present."""
    match = re.search(rf"#{re.escape(name)}\s*:(.*?);", contents, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def easiest_dance_single(contents: str) -> ChartChoice:
    """Choose the least difficult dance-single chart declared by an .sm file."""
    charts: list[ChartChoice] = []
    for match in re.finditer(r"#NOTES\s*:(.*?);", contents, re.IGNORECASE | re.DOTALL):
        fields = match.group(1).split(":", 5)
        if len(fields) != 6 or fields[0].strip().lower() != "dance-single":
            continue
        difficulty = fields[2].strip()
        try:
            meter = int(fields[3].strip())
        except ValueError:
            continue
        charts.append(ChartChoice(difficulty=difficulty, meter=meter))

    if not charts:
        raise ValueError("no usable dance-single chart")

    return min(
        charts,
        key=lambda chart: (DIFFICULTY_ORDER.get(chart.difficulty.lower(), 99), chart.meter),
    )


def source_url(song_dir: Path) -> str | None:
    """Read the original download URL from the bundle's existing text file."""
    for path in sorted(song_dir.glob("*.txt")):
        value = path.read_text(encoding="utf-8").strip()
        if value.startswith(("https://", "http://")):
            return value
    return None


def input_audio(song_dir: Path, music: str | None = None) -> Path:
    if music:
        path = song_dir / music.replace("\\", "/")
        if not path.resolve().is_relative_to(song_dir.resolve()):
            raise ValueError("chart MUSIC path escapes song directory")
        if path.is_file() and path.suffix.lower() in (*AUDIO_EXTENSIONS, ".wav"):
            return path
    audio = [path for path in song_dir.iterdir()
             if path.is_file() and path.suffix.lower() in (*AUDIO_EXTENSIONS, ".wav")
             and path.name != "song.wav"]
    if len(audio) != 1:
        raise ValueError(f"expected exactly one source MP3, OGG or WAV file, found {len(audio)}")
    return audio[0]


def input_cover(song_dir: Path) -> Path | None:
    """Return the most likely downloaded jacket image, if one exists."""
    candidates = [
        path
        for path in song_dir.iterdir()
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.name.lower() != "song.bmp"
    ]
    if not candidates:
        return None

    def priority(path: Path) -> tuple[int, str]:
        name = path.stem.casefold()
        if "jacket" in name or "cover" in name:
            return (0, name)
        if name == song_dir.name.casefold():
            return (1, name)
        return (2, name)

    return min(candidates, key=priority)


def fallback_cover_path() -> Path:
    return Path(__file__).parents[1] / "assets" / "gameplay" / "fallback-cover.bmp"


def audio_duration_seconds(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return round(float(result.stdout.strip()), 3)


def is_runtime_wav_format(stream: dict[str, object]) -> bool:
    return (
        stream.get("codec_name") == WAV_CODEC
        and stream.get("sample_rate") == str(WAV_SAMPLE_RATE)
        and stream.get("channels") == WAV_CHANNELS
    )


def wav_matches_runtime_format(wav_path: Path) -> bool:
    """Return whether an existing WAV already uses the Pi runtime format."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-of",
            "json",
            str(wav_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return False
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError:
        return False
    return len(streams) == 1 and is_runtime_wav_format(streams[0])


def existing_metadata(metadata_path: Path) -> dict[str, object]:
    if not metadata_path.exists():
        return {}
    value = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("song.json must contain an object")
    return value


def merged_metadata(generated: dict[str, object], existing: dict[str, object], overwrite: bool) -> dict[str, object]:
    """Keep user-edited metadata while backfilling new generated fields."""
    if overwrite:
        return generated
    return {**generated, **existing}


def create_cover(source: Path, output: Path) -> None:
    subprocess.run(
        [
            "magick",
            str(source),
            "-auto-orient",
            "-filter",
            "point",
            "-resize",
            "256x256^",
            "-gravity",
            "center",
            "-extent",
            "256x256",
            f"BMP3:{output}",
        ],
        check=True,
    )


def prepare_song(song_dir: Path, overwrite: bool, dry_run: bool) -> None:
    sm_files = sorted(song_dir.glob("*.sm"))
    if len(sm_files) != 1:
        raise ValueError(f"expected exactly one .sm file, found {len(sm_files)}")

    sm_path = sm_files[0]
    sm_contents = sm_path.read_text(encoding="utf-8-sig")
    choice = easiest_dance_single(sm_contents)
    source_audio = input_audio(song_dir, sm_tag(sm_contents, "MUSIC"))
    wav_path = song_dir / "song.wav"
    cover_path = song_dir / "song.bmp"
    metadata_path = song_dir / "song.json"
    source_cover = input_cover(song_dir)

    title = sm_tag(sm_contents, "TITLE") or song_dir.name
    artist = sm_tag(sm_contents, "ARTIST") or ""
    metadata = {
        "title": title,
        "artist": artist,
        "duration_seconds": audio_duration_seconds(source_audio),
        "audio": wav_path.name,
        "chart": sm_path.name,
        "chart_style": "dance-single",
        "cover": cover_path.name,
        "source_url": source_url(song_dir),
    }
    existing = existing_metadata(metadata_path)
    metadata = merged_metadata(metadata, existing, overwrite)
    needs_wav = overwrite or not wav_path.exists() or not wav_matches_runtime_format(wav_path)
    needs_cover = overwrite or not cover_path.exists()
    needs_metadata = overwrite or not metadata_path.exists() or metadata != existing

    actions = [
        f"WAV {'create' if not wav_path.exists() else 'regenerate' if needs_wav else 'keep'}",
        f"cover {'create' if needs_cover else 'keep'}",
        f"metadata {'write' if needs_metadata else 'keep'}",
    ]
    print(f"{song_dir.name}: {choice.difficulty} {choice.meter}; {', '.join(actions)}")
    if dry_run:
        return

    # Interrupted conversions must not leave partial files that a rerun keeps.
    with TemporaryDirectory(prefix=".prepare-", dir=song_dir) as temporary:
        staging = Path(temporary)
        if needs_wav:
            converted = staging / "song.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(source_audio), "-acodec", WAV_CODEC, "-ar", str(WAV_SAMPLE_RATE), "-ac", str(WAV_CHANNELS), str(converted)],
                check=True,
            )
            converted.replace(wav_path)
        if needs_cover:
            converted = staging / "song.bmp"
            if source_cover is not None:
                create_cover(source_cover, converted)
            else:
                shutil.copyfile(fallback_cover_path(), converted)
            converted.replace(cover_path)
        if needs_metadata:
            converted = staging / "song.json"
            converted.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            converted.replace(metadata_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("song_directory", type=Path, help="directory containing one directory per downloaded song")
    parser.add_argument("--overwrite", action="store_true", help="replace existing generated WAV, cover, and metadata files")
    parser.add_argument("--dry-run", action="store_true", help="validate and list changes without writing files")
    args = parser.parse_args()

    failures = 0
    for song_dir in sorted(path for path in args.song_directory.iterdir()
                           if path.is_dir() and not path.name.startswith(".")):
        try:
            prepare_song(song_dir, args.overwrite, args.dry_run)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            failures += 1
            print(f"{song_dir.name}: skipped: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
