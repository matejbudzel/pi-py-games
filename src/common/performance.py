"""Lightweight frame timing for the Raspberry Pi performance HUD."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FrameTiming:
    input_ms: float = 0.0
    update_ms: float = 0.0
    render_ms: float = 0.0
    present_ms: float = 0.0
    work_ms: float = 0.0
    frame_ms: float = 0.0

    @property
    def frames_per_second(self) -> float:
        return 0.0 if self.frame_ms <= 0 else 1000 / self.frame_ms


@dataclass
class PerformanceTracker:
    started_at: float = field(default_factory=time.perf_counter)
    frames: int = 0
    latest: FrameTiming = field(default_factory=FrameTiming)
    totals: dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in _TIMING_NAMES})
    maxima: dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in _TIMING_NAMES})

    def record(self, timing: FrameTiming) -> None:
        self.frames += 1
        self.latest = timing
        for name in _TIMING_NAMES:
            value = getattr(timing, name)
            self.totals[name] += value
            self.maxima[name] = max(self.maxima[name], value)

    def report(self, now: float | None = None) -> str:
        duration = max(0.0, (time.perf_counter() if now is None else now) - self.started_at)
        average_fps = 0.0 if duration == 0 else self.frames / duration
        lines = [
            "pygame game performance report",
            f"duration_seconds={duration:.3f}",
            f"frames={self.frames}",
            f"average_fps={average_fps:.2f}",
        ]
        for name in _TIMING_NAMES:
            average = 0.0 if self.frames == 0 else self.totals[name] / self.frames
            lines.append(f"average_{name}={average:.3f}")
            lines.append(f"maximum_{name}={self.maxima[name]:.3f}")
        lines.extend(f"last_{name}={getattr(self.latest, name):.3f}" for name in _TIMING_NAMES)
        return "\n".join(lines) + "\n"

    def write_report(self, path: Path) -> None:
        path.write_text(self.report(), encoding="utf-8")


_TIMING_NAMES = ("input_ms", "update_ms", "render_ms", "present_ms", "work_ms", "frame_ms")
