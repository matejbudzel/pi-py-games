"""User-facing text settings for Pixel Colors."""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    title: str
    exit_confirmation_text: str
    exit_confirm_button: str
    exit_cancel_button: str


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or Path(os.environ.get("PI_PIXEL_COLORS_CONFIG", "config/color_pages.ini")).expanduser()
    parser = ConfigParser()
    parser.read(path, encoding="utf-8")
    return Settings(
        parser.get("game", "title", fallback="PIXEL COLORS").strip() or "PIXEL COLORS",
        parser.get("exit", "confirmation_text", fallback="LEAVE?").strip() or "LEAVE?",
        parser.get("exit", "confirm_button", fallback="YES").strip() or "YES",
        parser.get("exit", "cancel_button", fallback="NO").strip() or "NO",
    )
