#!/usr/bin/env python3
"""Create conservative kid-friendly Easy and Medium StepMania charts from WAV audio.

The generator derives *timing* from librosa beat/onset features. Arrows come
from short, deliberately repeatable dance patterns: audio cannot determine a
human author's lane choice. It emits no jumps or holds, keeps Easy to quarter
notes and Medium to eighth notes, and is intended as a playable first draft.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np


EASY_PATTERNS = (("L", "R", "D"), ("R", "L", "U"), ("D", "U", "L"), ("U", "D", "R"))
MEDIUM_PATTERNS = (("L", "R", "D", "U"), ("R", "L", "U", "D"), ("D", "U", "L", "R"), ("U", "D", "R", "L"))
LANE_INDEX = {"L": 0, "D": 1, "U": 2, "R": 3}


def normalise(values: np.ndarray) -> np.ndarray:
    return (values - values.mean()) / (values.std() + 1e-9)


def nearest_feature(feature: np.ndarray, feature_times: np.ndarray, target_times: np.ndarray) -> np.ndarray:
    index = np.searchsorted(feature_times, target_times).clip(1, len(feature_times) - 1)
    left = index - 1
    index -= target_times - feature_times[left] < feature_times[index] - target_times
    return feature[index]


def kid_tempo(raw_tempo: float) -> float:
    """Fold beat-tracker octave mistakes into a comfortable dance tempo."""
    while raw_tempo < 80:
        raw_tempo *= 2
    while raw_tempo > 180:
        raw_tempo /= 2
    return raw_tempo


def select_slots(scores: np.ndarray, candidates: list[int], count: int, minimum_gap: int) -> set[int]:
    """Pick energetic slots without bursts too close for a young player."""
    chosen: set[int] = set()
    for slot in sorted(candidates, key=lambda value: scores[value], reverse=True):
        if all(abs(slot - existing) >= minimum_gap for existing in chosen):
            chosen.add(slot)
        if len(chosen) == count:
            break
    return chosen


def arrows_for_slots(slots: set[int], patterns: tuple[tuple[str, ...], ...]) -> dict[int, str]:
    """Use a phrase-stable pattern rather than independent random directions."""
    output: dict[int, str] = {}
    event_index = 0
    for slot in sorted(slots):
        phrase = (slot // 64) % len(patterns)  # new four-measure pattern every phrase
        pattern = patterns[phrase]
        output[slot] = pattern[event_index % len(pattern)]
        event_index += 1
    return output


def note_rows(slots: set[int], arrows: dict[int, str], measure_count: int) -> str:
    rows: list[str] = []
    for measure in range(measure_count):
        for row in range(16):
            slot = measure * 16 + row
            values = ["0"] * 4
            if slot in slots:
                values[LANE_INDEX[arrows[slot]]] = "1"
            rows.append("".join(values))
        if measure != measure_count - 1:
            rows.append(",")
    return "\n".join(rows)


def chart_block(difficulty: str, meter: int, rows: str) -> str:
    return f"""#NOTES:\n     dance-single:\n     :\n     {difficulty}:\n     {meter}:\n     0,0,0,0,0:\n{rows}\n;\n"""


def generate(song_dir: Path, overwrite: bool) -> None:
    wav_path, metadata_path, sm_path = song_dir / "song.wav", song_dir / "song.json", song_dir / "song.sm"
    if not wav_path.is_file() or not metadata_path.is_file():
        raise ValueError("requires song.wav and song.json; run prepare_id3_songs.py first")
    if sm_path.exists() and not overwrite:
        raise ValueError("song.sm already exists (pass --overwrite to replace it)")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    audio, sample_rate = librosa.load(wav_path, sr=22050, mono=True)
    tempo_value, beat_frames = librosa.beat.beat_track(y=audio, sr=sample_rate, trim=False, sparse=True)
    beats = librosa.frames_to_time(beat_frames, sr=sample_rate)
    if len(beats) < 8:
        raise ValueError("could not find a stable beat")
    tempo = kid_tempo(float(np.asarray(tempo_value).reshape(-1)[0]))
    offset = float(beats[0])
    beat_seconds = 60 / tempo
    duration = len(audio) / sample_rate
    measure_count = max(1, int((duration - offset) / (beat_seconds * 4)))
    slots = np.arange(measure_count * 16)
    times = offset + slots * beat_seconds / 4
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate, hop_length=512)
    rms = librosa.feature.rms(y=audio, hop_length=512)[0]
    feature_times = librosa.frames_to_time(np.arange(len(onset)), sr=sample_rate, hop_length=512)
    scores = nearest_feature(normalise(onset) + .30 * normalise(rms), feature_times, times)
    easy_slots: set[int] = set()
    medium_slots: set[int] = set()
    # Each measure has 16 SM rows. Easy only evaluates quarters; Medium evaluates eighths.
    for measure in range(measure_count):
        start = measure * 16
        easy_candidates = list(range(start, start + 16, 4))
        medium_candidates = list(range(start, start + 16, 2))
        energy = float(scores[start : start + 16].mean())
        easy_slots |= select_slots(scores, easy_candidates, 3 if energy > 0.15 else 2, minimum_gap=4)
        medium_slots |= select_slots(scores, medium_candidates, 5 if energy > 0.15 else 4, minimum_gap=2)
    easy_arrows = arrows_for_slots(easy_slots, EASY_PATTERNS)
    medium_arrows = arrows_for_slots(medium_slots, MEDIUM_PATTERNS)
    title = str(metadata.get("title") or song_dir.name).replace(";", ",")
    artist = str(metadata.get("artist") or "").replace(";", ",")
    header = f"#TITLE:{title};\n#ARTIST:{artist};\n#MUSIC:{wav_path.name};\n#OFFSET:{offset:.6f};\n#BPMS:0.000000={tempo:.6f};\n\n"
    sm_path.write_text(header + chart_block("Easy", 3, note_rows(easy_slots, easy_arrows, measure_count)) + "\n" + chart_block("Medium", 6, note_rows(medium_slots, medium_arrows, measure_count)), encoding="utf-8")
    print(f"{song_dir.name}: {tempo:.1f} BPM, offset {offset:.3f}s, Easy {len(easy_slots)} steps, Medium {len(medium_slots)} steps")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("song_directory", type=Path, nargs="+", help="prepared song folders")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing generated song.sm")
    args = parser.parse_args()
    for song_dir in args.song_directory:
        generate(song_dir, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
