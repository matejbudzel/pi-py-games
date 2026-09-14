"""Robust local JSON tuning persistence."""
from __future__ import annotations
import json
from pathlib import Path

DEFAULTS = {
    "wind": 0.35, "steering": 1.0, "balance": 1.0, "cadence": 1.0,
    "curve_loss": 1.0, "airborne_loss": 1.0, "inertia": 1.0,
    "imbalance": 1.0, "wall": 1.0,
}
def load(path: Path, profile: str = "default") -> dict[str, float]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        saved = {}
    # Version-one files were a flat value mapping.  Treat them as the default
    # profile so existing local calibration is retained after this upgrade.
    if not isinstance(saved, dict):
        saved = {}
    if all(not isinstance(value, dict) for value in saved.values()):
        saved = saved if profile == "default" else {}
    else:
        saved = saved.get(profile, {})
    return {key: float(saved.get(key, value)) for key, value in DEFAULTS.items()}


def save(path: Path, values: dict[str, float], profile: str = "default") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    if all(not isinstance(value, dict) for value in existing.values()):
        existing = {"default": existing}
    existing[profile] = {key: values[key] for key in DEFAULTS}
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
