from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pi_dance.config import load_settings


class SettingsTests(unittest.TestCase):
    def test_reads_title_and_resolves_relative_song_directory(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "pi-dance.ini"
            config_path.write_text("[game]\ntitle = Dance!\n[songs]\ndirectory = music\n[exit]\nitem_title = Exit\n")

            settings = load_settings(config_path)

        self.assertEqual(settings.title, "Dance!")
        self.assertEqual(settings.song_directory, config_path.parent / "music")
        self.assertEqual(settings.exit_item_title, "Exit")
        self.assertEqual(settings.pause_text, "Pauza")
        self.assertEqual(settings.display_backend, "pygame")

    def test_uses_defaults_when_config_is_missing(self) -> None:
        settings = load_settings(Path("missing-pi-dance.ini"))

        self.assertEqual(settings.title, "Tancuj, tancuj, vykrúcaj!")
        self.assertEqual(settings.song_directory, Path("songs"))
        self.assertEqual(settings.exit_confirmation_text, "Naozaj skončiť?")
        self.assertEqual(settings.song_exit_confirmation_text, "Prestať tancovať?")
        self.assertEqual(settings.timing_offset_ms, 0)
        self.assertEqual(settings.framebuffer_device, Path("/dev/fb0"))
