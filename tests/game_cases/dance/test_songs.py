import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pi_dance.songs import discover_songs, focus_color_for_title


class SongDiscoveryTests(unittest.TestCase):
    def test_discovers_complete_bundles_sorted_by_title(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_song(root, "second", "Zebra")
            self._write_song(root, "first", "Apple")
            self._write_song(root, "broken", "Broken", audio=False)

            songs = discover_songs(root)

        self.assertEqual([song.title for song in songs], ["Apple", "Zebra"])
        self.assertTrue(songs[0].cover_path.name == "fallback-cover.bmp")

    def test_focus_color_is_stable_and_bright(self) -> None:
        color = focus_color_for_title("How Far I'll Go")

        self.assertEqual(color, focus_color_for_title("How Far I'll Go"))
        self.assertNotEqual(color, focus_color_for_title("Shake It Off"))
        self.assertGreaterEqual(max(color), 230)

    def test_invalid_durations_do_not_break_discovery(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_song(root, "valid", "Valid")
            for index, duration in enumerate(("invalid", "NaN", "Infinity", -1)):
                self._write_song(root, str(index), "Broken")
                path = root / str(index) / "song.json"
                metadata = json.loads(path.read_text())
                metadata["duration_seconds"] = duration
                path.write_text(json.dumps(metadata))
            self.assertEqual([song.title for song in discover_songs(root)], ["Valid"])

    def test_legacy_difficulty_fields_are_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_song(root, "legacy", "Legacy")
            path = root / "legacy" / "song.json"
            metadata = json.loads(path.read_text())
            metadata.update(chart_difficulty="Hard", chart_meter="unused")
            path.write_text(json.dumps(metadata))
            self.assertEqual([song.title for song in discover_songs(root)], ["Legacy"])

    @staticmethod
    def _write_song(root: Path, name: str, title: str, audio: bool = True) -> None:
        bundle = root / name
        bundle.mkdir()
        (bundle / "song.json").write_text(json.dumps({
            "title": title,
            "audio": "song.wav",
            "chart": "chart.sm",
            "duration_seconds": 120,
        }))
        (bundle / "chart.sm").touch()
        if audio:
            (bundle / "song.wav").touch()
