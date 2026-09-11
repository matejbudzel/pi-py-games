import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[3] / "src" / "games" / "dance" / "scripts"))
import list_songs


class ListSongsTests(unittest.TestCase):
    def test_inventory_sorts_by_metadata_title_and_lists_all_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            zulu = root / "zulu-folder"
            alpha = root / "alpha-folder"
            zulu.mkdir()
            alpha.mkdir()
            (zulu / "song.json").write_text(json.dumps({"title": "Zulu"}), encoding="utf-8")
            (alpha / "song.json").write_text(json.dumps({"title": "alpha"}), encoding="utf-8")
            (alpha / "nested").mkdir()
            (alpha / "song.wav").write_bytes(b"")
            (alpha / "nested" / "chart.sm").write_text("", encoding="utf-8")

            inventory = list_songs.read_inventory(root)

        self.assertEqual([song.title for song in inventory], ["alpha", "Zulu"])
        self.assertEqual(inventory[0].assets, (Path("nested/chart.sm"), Path("song.json"), Path("song.wav")))

    def test_reports_incomplete_bundle(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            incomplete = root / "incomplete"
            incomplete.mkdir()
            (incomplete / "source.ogg").write_bytes(b"")

            inventory = list_songs.read_inventory(root)

        self.assertEqual(inventory[0].title, "incomplete")
        self.assertEqual(inventory[0].problem, "missing song.json")

    def test_main_reports_missing_directory(self):
        with patch("builtins.print") as print_mock:
            result = list_songs.main(["missing-songs"])

        self.assertEqual(result, 1)
        self.assertIn("song directory does not exist", print_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
