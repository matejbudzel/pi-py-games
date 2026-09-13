#!/usr/bin/env python3
"""Compare StepMania dance-single charts with audio features (research-only)."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import roc_auc_score

SONGS = Path("/home/matej/pi-dance-songs")
OUT = Path("research/chart_audio")


def tag(text: str, name: str) -> str:
    match = re.search(rf"#{name}:\s*(.*?);", text, re.S | re.I)
    return match.group(1).strip() if match else ""


def bpms(text: str) -> list[tuple[float, float]]:
    values = []
    for pair in tag(text, "BPMS").replace("\n", "").split(","):
        if "=" in pair:
            beat, bpm = pair.split("=", 1)
            values.append((float(beat), float(bpm)))
    return sorted(values) or [(0.0, 120.0)]


def beat_to_seconds(beat: float, changes: list[tuple[float, float]], offset: float) -> float:
    seconds = -offset
    last_beat, bpm = changes[0]
    for next_beat, next_bpm in changes[1:]:
        if beat <= next_beat:
            return seconds + (beat - last_beat) * 60 / bpm
        seconds += (next_beat - last_beat) * 60 / bpm
        last_beat, bpm = next_beat, next_bpm
    return seconds + (beat - last_beat) * 60 / bpm


def charts(text: str) -> list[tuple[str, int, list[tuple[float, str]]]]:
    # The classic #NOTES form used by this collection.  Holds/mines count as a
    # step at their start, while releases do not.
    found = []
    for body in re.findall(r"#NOTES:\s*(.*?);", text, re.S | re.I):
        fields = body.split(":", 5)
        if len(fields) != 6 or fields[0].strip() != "dance-single":
            continue
        difficulty = fields[2].strip()
        try:
            meter = int(fields[3].strip())
        except ValueError:
            meter = 0
        notes = []
        for measure_index, measure in enumerate(fields[5].split(",")):
            rows = [r.strip() for r in measure.splitlines() if re.fullmatch(r"[0-9A-Z]{4}", r.strip())]
            for index, row in enumerate(rows):
                if any(char in "124M" for char in row):
                    notes.append((measure_index * 4 + index * 4 / len(rows), row))
        found.append((difficulty, meter, notes))
    return found


def zscore(values: np.ndarray) -> np.ndarray:
    return (values - values.mean()) / (values.std() + 1e-9)


def nearest_values(values: np.ndarray, times: np.ndarray) -> np.ndarray:
    positions = np.searchsorted(times, values).clip(1, len(times) - 1)
    left, right = positions - 1, positions
    positions -= values - times[left] < times[right] - values
    return positions


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, visual_examples = [], []
    for sm_path in sorted(SONGS.glob("*/*.sm")):
        wav = sm_path.parent / "song.wav"
        if not wav.exists():
            continue
        text = sm_path.read_text(errors="replace")
        song_title = tag(text, "TITLE") or sm_path.stem
        changes, offset = bpms(text), float(tag(text, "OFFSET") or 0)
        audio, sr = librosa.load(wav, sr=22050, mono=True)
        onset = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=512)
        rms = librosa.feature.rms(y=audio, hop_length=512)[0]
        centroid = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=512)[0]
        times = librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=512)
        feature = zscore(onset) + 0.35 * zscore(rms) + 0.20 * zscore(np.abs(np.diff(centroid, prepend=centroid[0])))
        max_beat = (len(audio) / sr + offset) * changes[-1][1] / 60
        grid_beats = np.arange(0, max_beat, 0.25)
        grid_times = np.array([beat_to_seconds(b, changes, offset) for b in grid_beats])
        valid = (grid_times >= 0) & (grid_times < times[-1])
        grid_beats, grid_times = grid_beats[valid], grid_times[valid]
        grid_feature = feature[nearest_values(grid_times, times)]
        for difficulty, meter, notes in charts(text):
            note_beats = np.array([beat for beat, _ in notes])
            labels = np.isclose(grid_beats[:, None], note_beats[None, :], atol=.02).any(axis=1) if len(note_beats) else np.zeros(len(grid_beats), bool)
            # Compare exact StepMania timing to onset/features, separately per chart.
            auc = roc_auc_score(labels, grid_feature) if labels.any() and (~labels).any() else float("nan")
            note_times = np.array([beat_to_seconds(b, changes, offset) for b, _ in notes])
            for b, t, value, hit in zip(grid_beats, grid_times, grid_feature, labels):
                rows.append({"song": song_title, "difficulty": difficulty, "meter": meter, "beat": b, "time": t, "feature": value, "note": int(hit)})
            visual_examples.append((song_title, difficulty, meter, audio, sr, onset, times, note_times, note_beats, auc))
    with (OUT / "grid_features.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader(); writer.writerows(rows)
    # Per-chart evidence table: audio-feature separation at charted versus uncharted 16ths.
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["song"], row["difficulty"], row["meter"])].append(row)
    summary = []
    for key, selected in sorted(grouped.items()):
        hits = np.array([r["feature"] for r in selected if r["note"]])
        rests = np.array([r["feature"] for r in selected if not r["note"]])
        auc = roc_auc_score([r["note"] for r in selected], [r["feature"] for r in selected])
        summary.append((*key, len(hits), len(hits) / len(selected), hits.mean(), rests.mean(), auc))
    with (OUT / "chart_summary.csv").open("w", newline="") as file:
        writer = csv.writer(file); writer.writerow(["song", "difficulty", "meter", "steps", "grid_density", "step_feature_mean", "rest_feature_mean", "onset_auc"]); writer.writerows(summary)
    # Overview: density by declared difficulty, and ability of audio energy/transients to locate authored steps.
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for difficulty in sorted({s[1] for s in summary}):
        values = [s for s in summary if s[1] == difficulty]
        axes[0].scatter([s[2] for s in values], [s[4] for s in values], label=difficulty, alpha=.8)
        axes[1].scatter([s[2] for s in values], [s[7] for s in values], label=difficulty, alpha=.8)
    axes[0].set(xlabel="declared meter", ylabel="steps per 16th-note grid", title="Difficulty mostly controls density")
    axes[1].axhline(.5, color="black", lw=1); axes[1].set(xlabel="declared meter", ylabel="onset-feature AUC", ylim=(.35, 1), title="Audio-only step timing evidence")
    axes[1].legend(fontsize=8, ncol=2); fig.tight_layout(); fig.savefig(OUT / "overview.png", dpi=160); plt.close(fig)
    # Four representative aligned timelines. A spectrogram plus charted rows show timing alignment directly.
    samples = [x for x in visual_examples if x[1] in {"Beginner", "Easy", "Medium"}][:4]
    fig, axes = plt.subplots(len(samples), 1, figsize=(15, 3.2 * len(samples)), sharex=False)
    for ax, (title, difficulty, meter, audio, sr, onset, times, note_times, note_beats, auc) in zip(np.atleast_1d(axes), samples):
        duration = min(45, len(audio) / sr)
        spec = librosa.amplitude_to_db(np.abs(librosa.stft(audio[: int(duration * sr)], n_fft=1024)), ref=np.max)
        librosa.display.specshow(spec, x_axis="time", y_axis="log", sr=sr, hop_length=512, ax=ax, cmap="magma")
        shown = note_times[(note_times >= 0) & (note_times <= duration)]
        ax.vlines(shown, 40, 9000, color="#63e6be", lw=.7, alpha=.85)
        ax.set(title=f"{title} — {difficulty} {meter}; green = authored steps; timing AUC {auc:.2f}", ylim=(40, 9000))
    fig.tight_layout(); fig.savefig(OUT / "spectrogram_chart_alignment.png", dpi=150); plt.close(fig)
    counts = Counter((s[1], s[2]) for s in summary)
    with (OUT / "README.md").open("w") as file:
        file.write("# Audio/chart research output\n\n")
        file.write(f"Parsed {len(summary)} dance-single charts from {len(set(s[0] for s in summary))} songs. Grid is every 16th note using each chart's BPM and offset. `onset_auc` is 0.50=random; above it means the onset/energy feature tends to be higher at an authored step.\n\n")
        file.write("`spectrogram_chart_alignment.png` overlays authored step times on a 45-second log-frequency spectrogram. `overview.png` summarizes density and timing evidence. `chart_summary.csv` contains per-chart metrics; `grid_features.csv` is the raw per-16th grid data.\n\n")
        file.write("Difficulty/meter chart counts: " + ", ".join(f"{d} {m}: {n}" for (d,m),n in sorted(counts.items())) + "\n")


if __name__ == "__main__":
    main()
