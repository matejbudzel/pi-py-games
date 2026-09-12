from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path

from common.display import display_settings

LOGICAL_WIDTH, LOGICAL_HEIGHT = 427, 240
WIDTH, HEIGHT = 854, 480
OUTPUT_SIZE = (854, 480)
FPS = 30


@dataclass(frozen=True)
class Settings:
    title: str
    song_directory: Path
    timing_offset_ms: int
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
        parser.getint("gameplay", "timing_offset_ms", fallback=0), display.backend, display.framebuffer,
    )
