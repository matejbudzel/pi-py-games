from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path

from common.display import display_settings

WIDTH, HEIGHT = 427, 240
OUTPUT_SIZE = (854, 480)
FPS = 30


@dataclass(frozen=True)
class Settings:
    title: str
    song_directory: Path
    timing_offset_ms: int
    pause_text: str
    exit_confirmation_text: str
    exit_confirm_button: str
    exit_cancel_button: str
    display_backend: str
    framebuffer_device: Path


def load_settings(config_path: Path | None = None) -> Settings:
    config_path = config_path or Path(os.environ.get("PI_SHADOW_RUN_CONFIG", "config/shadow-run.ini")).expanduser()
    parser = ConfigParser()
    parser.read(config_path, encoding="utf-8")
    song_directory = Path(parser.get("songs", "directory", fallback="shadow-run-songs")).expanduser()
    if not song_directory.is_absolute():
        song_directory = config_path.parent / song_directory
    display = display_settings(parser.get("display", "backend", fallback="pygame"), Path(parser.get("display", "framebuffer", fallback="/dev/fb0")))
    return Settings(
        parser.get("game", "title", fallback="Shadow Run").strip() or "Shadow Run", song_directory,
        parser.getint("gameplay", "timing_offset_ms", fallback=0),
        parser.get("gameplay", "pause_text", fallback="Pauza").strip() or "Pauza",
        parser.get("gameplay", "exit_confirmation_text", fallback="Odísť z hry?").strip() or "Odísť z hry?",
        parser.get("gameplay", "exit_confirm_button", fallback="Áno").strip() or "Áno",
        parser.get("gameplay", "exit_cancel_button", fallback="Nie").strip() or "Nie",
        display.backend, display.framebuffer,
    )
