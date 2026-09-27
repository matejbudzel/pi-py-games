"""Local configuration for Blocks."""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    title: str
    splash_text: str
    leave_question: str
    pause_text: str
    new_high_score_text: str
    yes: str
    no: str
    high_score_path: Path
    countdown_seconds: int


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or Path(os.environ.get("PI_BLOCKS_CONFIG", "config/blocks.ini")).expanduser()
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    score_path = Path(parser.get("storage", "high_score_path", fallback="~/.local/state/pi-py-games/blocks.json")).expanduser()
    if not score_path.is_absolute():
        score_path = path.parent / score_path
    return Settings(
        title=parser.get("game", "title", fallback="BLOCKS").strip() or "BLOCKS",
        splash_text=parser.get("text", "splash_text", fallback="STLAČ ŠTART").strip() or "STLAČ ŠTART",
        leave_question=parser.get("text", "leave_question", fallback="Odísť?").strip() or "Odísť?",
        pause_text=parser.get("text", "pause_text", fallback="PAUZA").strip() or "PAUZA",
        new_high_score_text=parser.get("text", "new_high_score_text", fallback="NOVÝ REKORD!").strip() or "NOVÝ REKORD!",
        yes=parser.get("text", "yes", fallback="Áno").strip() or "Áno",
        no=parser.get("text", "no", fallback="Nie").strip() or "Nie",
        high_score_path=score_path,
        countdown_seconds=max(1, parser.getint("tuning", "countdown_seconds", fallback=3)),
    )
