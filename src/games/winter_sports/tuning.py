"""Robust local JSON tuning persistence."""
from __future__ import annotations
import json
from pathlib import Path

DEFAULTS = {
    "wind": 0.35, "steering": 1.0, "balance": 1.0, "cadence": 1.0,
    "curve_loss": 1.0, "airborne_loss": 1.0, "inertia": 1.0,
    "imbalance": 1.0, "wall": 1.0,
}
def load(path: Path) -> dict[str, float]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        saved = {}
    return {key: float(saved.get(key, value)) for key, value in DEFAULTS.items()}
def save(path: Path, values: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: values[key] for key in DEFAULTS}, indent=2), encoding="utf-8")
