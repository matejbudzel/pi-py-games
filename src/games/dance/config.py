from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
import os

from common.display import display_settings


APP_WIDTH = 854
APP_HEIGHT = 480
TARGET_FPS = 30
WINDOW_TITLE = "pi-dance"


@dataclass(frozen=True)
class Settings:
    title: str
    song_directory: Path
    exit_item_title: str
    exit_confirmation_text: str
    exit_confirm_button: str
    exit_cancel_button: str
    pause_text: str
    song_exit_confirmation_text: str
    song_exit_confirm_button: str
    song_exit_cancel_button: str
    timing_offset_ms: int
    display_backend: str
    framebuffer_device: Path
    display_cec: bool
    error_log: Path


def load_settings(config_path: Path | None = None) -> Settings:
    """Load user-editable settings, falling back to portable defaults."""
    if config_path is None:
        config_path = Path(os.environ.get("PI_DANCE_CONFIG", "config/dance.ini")).expanduser()
    parser = ConfigParser()
    parser.read(config_path, encoding="utf-8")

    title = parser.get("game", "title", fallback="Tancuj, tancuj, vykrúcaj!").strip()
    song_directory_value = parser.get("songs", "directory", fallback="songs").strip()
    song_directory = Path(song_directory_value).expanduser()
    if not song_directory.is_absolute():
        song_directory = config_path.parent / song_directory
    platform_display = display_settings(
        parser.get("display", "backend", fallback="pygame").strip().lower() or "pygame",
        Path(parser.get("display", "framebuffer", fallback="/dev/fb0").strip() or "/dev/fb0"),
    )
    return Settings(
        title=title or "Tancuj, tancuj, vykrúcaj!",
        song_directory=song_directory,
        exit_item_title=parser.get("exit", "item_title", fallback="Koniec").strip() or "Koniec",
        exit_confirmation_text=parser.get("exit", "confirmation_text", fallback="Naozaj skončiť?").strip() or "Naozaj skončiť?",
        exit_confirm_button=parser.get("exit", "confirm_button", fallback="Áno").strip() or "Áno",
        exit_cancel_button=parser.get("exit", "cancel_button", fallback="Nie").strip() or "Nie",
        pause_text=parser.get("gameplay", "pause_text", fallback="Pauza").strip() or "Pauza",
        song_exit_confirmation_text=parser.get("gameplay", "exit_confirmation_text", fallback="Prestať tancovať?").strip() or "Prestať tancovať?",
        song_exit_confirm_button=parser.get("gameplay", "exit_confirm_button", fallback="Áno").strip() or "Áno",
        song_exit_cancel_button=parser.get("gameplay", "exit_cancel_button", fallback="Nie").strip() or "Nie",
        timing_offset_ms=parser.getint("gameplay", "timing_offset_ms", fallback=0),
        display_backend=platform_display.backend,
        framebuffer_device=platform_display.framebuffer,
        display_cec=parser.getboolean("display", "cec", fallback=False),
        error_log=Path(parser.get("game", "error_log", fallback="~/.local/state/pi-dance/errors.log")).expanduser(),
    )


SETTINGS = load_settings()
SONG_DIRECTORY = SETTINGS.song_directory

TITLE = SETTINGS.title
FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "sweet16mono.ttf"

BACKGROUND = (0, 0, 0)
FOREGROUND = (240, 240, 240)
