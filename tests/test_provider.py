import json
import unittest
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

    def test_run_rejects_unknown_game(self):
        with self.assertRaises(ValueError):
            provider.run("not-a-game", Path("pi-py-games.ini"))

    def test_run_passes_game_specific_config_to_child(self):
        with patch("pi_py_games.provider.subprocess.call", return_value=0) as call:
            self.assertEqual(provider.run("pi-dance", Path("/tmp/provider.ini")), 0)
        self.assertEqual(call.call_args.args[0][1:], ["-m", "games.dance.main"])
        self.assertEqual(call.call_args.kwargs["env"]["PI_DANCE_CONFIG"], "/tmp/pi-dance.ini")
