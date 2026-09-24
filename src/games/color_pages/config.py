"""User-facing text settings for Pixel Colors."""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    title: str
    art_directory: Path
    no_images_text: str
    exit_confirmation_text: str
    exit_confirm_button: str
    exit_cancel_button: str


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or Path(os.environ.get("PI_PIXEL_COLORS_CONFIG", "config/color_pages.ini")).expanduser()
    parser = ConfigParser()
    parser.read(path, encoding="utf-8")
    art_directory = Path(parser.get("art", "directory", fallback="../src/games/color_pages/assets/pages")).expanduser()
    if not art_directory.is_absolute():
        art_directory = path.parent / art_directory
    return Settings(
        parser.get("game", "title", fallback="PIXEL FARBY").strip() or "PIXEL FARBY",
        art_directory,
        parser.get("art", "no_images_text", fallback="Žiadne obrázky nie sú k dispozícii").strip() or "Žiadne obrázky nie sú k dispozícii",
        parser.get("exit", "confirmation_text", fallback="Naozaj skončiť?").strip() or "Naozaj skončiť?",
        parser.get("exit", "confirm_button", fallback="Áno").strip() or "Áno",
        parser.get("exit", "cancel_button", fallback="Nie").strip() or "Nie",
    )
