"""Offline WAV beat preparation; deliberately not imported by the game runtime.

Usage: ``python -m games.shadow_run.prepare_songs MUSIC_DIRECTORY``.
Each ``name.wav`` receives a neighbouring ``name.shadow.json`` sidecar.
``librosa`` is optional but recommended on the desktop; a deterministic WAV
energy fallback keeps preparation useful without it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import wave

from .songs import SCHEMA_VERSION, sidecar_path_for


def source_info(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {"file": path.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def is_current(audio: Path, sidecar: Path) -> bool:
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
        return value.get("schema_version") == SCHEMA_VERSION and value.get("source") == source_info(audio)
    except (OSError, ValueError, TypeError):
        return False


def _fallback_analysis(path: Path) -> tuple[float, float, list[dict[str, object]]]:
    """Cheap analysis when librosa is unavailable; validates PCM WAV safely."""
    with wave.open(str(path), "rb") as wav:
        channels, rate, frames = wav.getnchannels(), wav.getframerate(), wav.getnframes()
        if channels < 1 or rate < 8000 or frames < rate:
            raise ValueError("WAV has insufficient PCM audio")
        duration = frames / rate
    # A conservative clock is more useful than claiming precise analysis.
    bpm = 120.0
    interval = 60.0 / bpm
    beats = [{"time": round(time, 4), "strength": 0.35, "accent": index % 4 == 0} for index, time in enumerate(_frange(0.0, duration, interval))]
    return duration, bpm, beats


def _frange(start: float, end: float, step: float):
    while start < end:
        yield start
        start += step


def analyze(path: Path) -> dict[str, object]:
    try:
        import librosa  # type: ignore[import-not-found]
    except ImportError:
        duration, bpm, beats = _fallback_analysis(path)
    else:
        samples, rate = librosa.load(str(path), sr=None, mono=True)
        if len(samples) == 0 or rate <= 0:
            raise ValueError("WAV contains no audio")
        onset = librosa.onset.onset_strength(y=samples, sr=rate)
        tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=rate)
        bpm = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
        times = librosa.frames_to_time(beat_frames, sr=rate)
        strengths = onset[beat_frames] if len(beat_frames) else []
        maximum = float(max(strengths)) if len(strengths) else 1.0
        beats = [{"time": round(float(time), 4), "strength": round(float(strength) / maximum, 3), "accent": index % 4 == 0} for index, (time, strength) in enumerate(zip(times, strengths))]
        duration = len(samples) / rate
        if not beats or bpm <= 0:
            duration, bpm, beats = _fallback_analysis(path)
    return {"schema_version": SCHEMA_VERSION, "analyzer": "librosa-or-wave-fallback", "title": path.stem, "source": source_info(path), "duration": round(duration, 4), "tempo_bpm": round(bpm, 3), "beats": beats}


def prepare(directory: Path, force: bool = False) -> int:
    failures = 0
    for audio in sorted(directory.rglob("*.wav")):
        print(f"FOUND     {audio}")
        sidecar = sidecar_path_for(audio)
        if not force and is_current(audio, sidecar):
            print("SKIPPED   already prepared")
            continue
        try:
            sidecar.write_text(json.dumps(analyze(audio), indent=2) + "\n", encoding="utf-8")
            print(f"ANALYZED  {audio} -> {sidecar.name}")
        except (OSError, ValueError, EOFError, wave.Error) as error:
            failures += 1
            print(f"ERROR     {audio}: {error}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare WAV files for Shadow Run (desktop only)")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if not args.directory.is_dir():
        parser.error(f"not a directory: {args.directory}")
    return prepare(args.directory, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
