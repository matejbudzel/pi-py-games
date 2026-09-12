import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from pi_py_games import provider


class ProviderTests(unittest.TestCase):
    def test_manifest_uses_launcher_schema(self):
        document = provider.manifest(Path("/games/pi-py-games.ini"))
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["games"][0]["id"], "pi-dance")
        self.assertEqual(document["games"][0]["command"][1:], ["-m", "pi_py_games.provider", "--config", "/games/pi-py-games.ini", "run", "pi-dance"])
        self.assertEqual(document["games"][1]["id"], "2048")

    def test_manifest_uses_game_configured_title(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            game_config = root / "shadow.ini"
            game_config.write_text("[game]\ntitle=Tienozem\n", encoding="utf-8")
            provider_config = root / "provider.ini"
            provider_config.write_text("[shadow-run]\nconfig=shadow.ini\n", encoding="utf-8")
            document = provider.manifest(provider_config)
        shadow_run = next(game for game in document["games"] if game["id"] == "shadow-run")
        self.assertEqual(shadow_run["title"], "Tienozem")

    def test_run_rejects_unknown_game(self):
        with self.assertRaises(ValueError):
            provider.run("not-a-game", Path("pi-py-games.ini"))

    def test_run_passes_game_specific_config_to_child(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "provider.ini"
            config.write_text("[display]\nbackend=fbdev\nframebuffer=/dev/fb1\n", encoding="utf-8")
            with patch("pi_py_games.provider.subprocess.call", return_value=0) as call:
                self.assertEqual(provider.run("pi-dance", config), 0)
        self.assertEqual(call.call_args.args[0][1:], ["-m", "pi_py_games.runner", "pi-dance", "games.dance.main"])
        self.assertEqual(call.call_args.kwargs["env"]["PI_DANCE_CONFIG"], str(config.parent / "config/dance.ini"))
        self.assertEqual(call.call_args.kwargs["env"]["PI_PY_GAMES_DISPLAY_BACKEND"], "fbdev")
        self.assertEqual(call.call_args.kwargs["env"]["PI_PY_GAMES_FRAMEBUFFER"], "/dev/fb1")
        self.assertEqual(call.call_args.kwargs["env"]["PI_PY_GAMES_ERROR_LOG"], str(Path("~/.local/state/pi-py-games/errors.log").expanduser()))
