#!/usr/bin/env python3
"""Find reusable direction and difficulty-transform patterns in .sm charts."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

from analyze_chart_audio import SONGS, charts

OUT = Path("research/chart_audio")
LANES = "LDU R".replace(" ", "")  # StepMania lane order: Left, Down, Up, Right.


def token(row: str) -> str:
    return "+".join(LANES[i] for i, char in enumerate(row) if char in "124M")


def entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    return -sum((n / total) * math.log2(n / total) for n in counts.values()) if total else 0.0


def main() -> None:
    all_charts = []
    for path in SONGS.glob("*/*.sm"):
        title = path.stem
        for difficulty, meter, notes in charts(path.read_text(errors="replace")):
            events = {round(beat * 192): token(row) for beat, row in notes}
            all_charts.append((title, difficulty, meter, events))
    transitions: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    motifs: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    totals = Counter()
    for _, difficulty, _, events in all_charts:
        singles = [value for _, value in sorted(events.items()) if "+" not in value]
        for a, b in zip(singles, singles[1:]):
            transitions[difficulty][(a, b)] += 1
        for index in range(len(singles) - 2):
            motifs[difficulty][tuple(singles[index : index + 3])] += 1
        totals[difficulty] += len(singles)
    # Do lower-meter charts retain the same timed arrows from their high-meter sibling?
    comparisons = []
    by_song: dict[str, list[tuple[str, int, dict[int, str]]]] = defaultdict(list)
    for title, difficulty, meter, events in all_charts:
        by_song[title].append((difficulty, meter, events))
    for title, group in by_song.items():
        for first_index, (_, first_meter, first) in enumerate(group):
            for _, second_meter, second in group[first_index + 1 :]:
                low_meter, low, high_meter, high = (first_meter, first, second_meter, second) if first_meter < second_meter else (second_meter, second, first_meter, first)
                if low_meter == high_meter or not low:
                    continue
                shared_slots = set(low) & set(high)
                same_arrow = sum(low[slot] == high[slot] for slot in shared_slots)
                comparisons.append((title, low_meter, high_meter, len(low), len(high), len(shared_slots) / len(low), same_arrow / len(shared_slots) if shared_slots else 0))
    with (OUT / "difficulty_containment.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["song", "low_meter", "high_meter", "low_events", "high_events", "low_timing_retained", "same_arrow_when_retained"])
        writer.writerows(comparisons)
    lines = ["# Arrow-pattern findings\n", "Direction is not encoded in the audio features, but the charts have strong reusable choreography constraints. Tokens use `L`, `D`, `U`, `R`; `+` means a jump.\n"]
    for difficulty in sorted(transitions):
        conditional = defaultdict(Counter)
        for (left, right), count in transitions[difficulty].items():
            conditional[left][right] += count
        lines.append(f"## {difficulty}\n")
        best_next_accuracy = sum(max(values.values()) for values in conditional.values()) / sum(sum(values.values()) for values in conditional.values())
        lines.append(f"Single-arrow events: {totals[difficulty]}; mean next-arrow uncertainty: {sum(entropy(v) for v in conditional.values()) / len(conditional):.2f} bits (2 bits would be four equally likely choices); a one-arrow Markov predictor only reaches {best_next_accuracy:.0%} accuracy.\n")
        lines.append("Top transitions: " + ", ".join(f"`{a}→{b}` ({n})" for (a, b), n in transitions[difficulty].most_common(8)) + ".\n")
        lines.append("Top three-step motifs: " + ", ".join(f"`{'→'.join(m)}` ({n})" for m, n in motifs[difficulty].most_common(8)) + ".\n")
    retention = [row[5] for row in comparisons]
    arrow_match = [row[6] for row in comparisons if row[5] > 0]
    lines += ["## Cross-difficulty relationship\n", f"Across {len(comparisons)} same-song low→high-meter pairs, a lower chart retains a median **{sorted(retention)[len(retention)//2]:.0%}** of its step timings in the higher chart. Where the timing remains, the exact arrow matches a median **{sorted(arrow_match)[len(arrow_match)//2]:.0%}** of the time.\n", "This supports generating difficulty variants by retaining a deterministic, high-scoring timing backbone and adding/removing events—not independently choosing arbitrary arrows for each difficulty.\n"]
    (OUT / "arrow_patterns.md").write_text("\n".join(lines))
    print("wrote", OUT / "arrow_patterns.md")


if __name__ == "__main__":
    main()
