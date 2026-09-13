from __future__ import annotations
from dataclasses import dataclass
from configparser import ConfigParser
from pathlib import Path
import os
from common.display import display_settings

WIDTH, HEIGHT, OUTPUT_SIZE, FPS = 427, 240, (854, 480), 30
@dataclass(frozen=True)
class Settings:
    title: str; display_backend: str; framebuffer_device: Path; tuning_path: Path
def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("PI_WINTER_SPORTS_CONFIG", "config/winter-sports.ini"))
    parser = ConfigParser()
    parser.read(path, encoding="utf-8")
    display = display_settings(
        parser.get("display", "backend", fallback="pygame").strip().lower() or "pygame",
        Path(parser.get("display", "framebuffer", fallback="/dev/fb0").strip() or "/dev/fb0"),
    )
    title = parser.get("game", "title", fallback="Winter Sports").strip() or "Winter Sports"
    return Settings(title, display.backend, display.framebuffer, path.parent / "winter-sports-tuning.json")
