#!/usr/bin/env python3
"""Turn raw output from analyze_chart_audio.py into concise visual evidence."""
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import rankdata

OUT = Path("research/chart_audio")


def main():
    with (OUT / "grid_features.csv").open() as f:
        rows = list(csv.DictReader(f))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["song"], r["difficulty"], int(r["meter"]))].append(r)
    summary = []
    for (song, difficulty, meter), values in sorted(groups.items()):
        labels = np.array([int(r["note"]) for r in values])
        features = np.array([float(r["feature"]) for r in values])
        # Mann-Whitney interpretation: probability a step has more transient/energy
        # than a non-step. This is equivalent to ROC AUC without a sklearn import.
        pos, neg = features[labels == 1], features[labels == 0]
        auc = (rankdata(features)[labels == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
        summary.append((song, difficulty, meter, len(pos), labels.mean(), pos.mean(), neg.mean(), auc))
    with (OUT / "chart_summary.csv").open("w", newline="") as f:
        writer = csv.writer(f); writer.writerow(["song", "difficulty", "meter", "steps", "grid_density", "step_feature_mean", "rest_feature_mean", "onset_auc"]); writer.writerows(summary)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for difficulty in sorted({s[1] for s in summary}):
        values = [s for s in summary if s[1] == difficulty]
        axes[0].scatter([s[2] for s in values], [s[4] for s in values], label=difficulty, alpha=.8)
        axes[1].scatter([s[2] for s in values], [s[7] for s in values], label=difficulty, alpha=.8)
    axes[0].set(xlabel="declared meter", ylabel="steps per 16th-note grid", title="Difficulty mostly controls density")
    axes[1].axhline(.5, color="black", lw=1); axes[1].set(xlabel="declared meter", ylabel="onset/energy AUC", ylim=(.35, 1), title="Audio-only step timing evidence")
    axes[1].legend(fontsize=8, ncol=2); fig.tight_layout(); fig.savefig(OUT / "overview.png", dpi=160); plt.close(fig)
    counts = Counter((s[1], s[2]) for s in summary)
    with (OUT / "README.md").open("w") as f:
        f.write("# Audio/chart research output\n\n")
        f.write(f"Parsed {len(summary)} dance-single charts from {len(set(s[0] for s in summary))} songs. Grid is every 16th note using each chart's BPM and offset. `onset_auc` is 0.50=random; higher means onset/energy is more often high at an authored step.\n\n")
        f.write("`overview.png` summarizes density and audio-timing evidence. `chart_summary.csv` contains per-chart metrics; `grid_features.csv` is raw per-16th data.\n\n")
        f.write("Difficulty/meter chart counts: " + ", ".join(f"{d} {m}: {n}" for (d,m), n in sorted(counts.items())) + "\n")
    print(len(summary), "charts", len(set(s[0] for s in summary)), "songs")
    print("overall AUC median", round(statistics.median(s[7] for s in summary), 3))
    for d in sorted({s[1] for s in summary}):
        s = [x for x in summary if x[1] == d]
        print(d, len(s), "density", round(statistics.median(x[4] for x in s), 3), "AUC", round(statistics.median(x[7] for x in s), 3))

if __name__ == "__main__": main()
