from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "games" / "dance" / "scripts"))
import import_ziv_songs as importer


PAGE = """
<h1>Example &amp; Song / Example Artist</h1>
<table><tr><td>Last Updated By</td><td><a href="user?userid=1">Chart Maker</a></td></tr>
<tr><td>ZIP</td><td><a href="download.php?type=ddrsimfile&amp;simfileid=123">ZIP</a></td></tr></table>
"""
CHART = """#TITLE:Chart title;
#ARTIST:Chart artist;
#MUSIC:audio.wav;
#BPMS:0=120;
#NOTES:dance-single::Beginner:1:0:
1000
0000
0100
0000
;
"""


def synthetic_zip(path: Path) -> None:
    audio = BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\0" * 22050 * 4)
    with ZipFile(path, "w") as zipped:
        zipped.writestr("Pack/Example/chart.sm", CHART)
        zipped.writestr("Pack/Example/audio.wav", audio.getvalue())
        zipped.write(importer.prepare_songs.fallback_cover_path(), "Pack/Example/jacket.bmp")


class ImportSongsTests(unittest.TestCase):
    def test_id_comments_duplicates_and_validation(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "ids.txt"
            path.write_text("# favourites\n123\n00456 # next song\n123\n")
            self.assertEqual(importer.read_ids(path), [123, 456])
            path.write_text("123\n../456\n")
            with self.assertRaisesRegex(ValueError, ":2:"):
                importer.read_ids(path)

    def test_site_metadata_and_matching_download(self):
        page = importer.parse_page(PAGE, 123)
        self.assertEqual(page["title"], "Example & Song")
        self.assertEqual(page["artist"], "Example Artist")
        self.assertEqual(page["ziv_last_updated_by"], "Chart Maker")
        self.assertEqual(page["download_url"], importer.BASE_URL + "download.php?type=ddrsimfile&simfileid=123")
        with self.assertRaisesRegex(ValueError, "matching ZIP"):
            importer.parse_page(PAGE, 456)
        with self.assertRaises(ValueError):
            importer.parse_page("<h1>Access denied</h1>", 123)

    def test_zip_rejects_unsafe_paths(self):
        for name in ("../escape.sm", "/absolute.sm", "folder\\escape.sm", "C:/escape.sm"):
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "source.zip"
                with ZipFile(archive, "w") as zipped:
                    zipped.writestr(name, CHART)
                with self.assertRaisesRegex(ValueError, "unsafe ZIP"):
                    importer.extract_bundle(archive, root / "output")

    def test_zip_rejects_ambiguous_or_ssc_only_bundles(self):
        for names in (("a.sm", "b.sm"), ("a.ssc",)):
            with self.subTest(names=names), TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "source.zip"
                with ZipFile(archive, "w") as zipped:
                    for name in names:
                        zipped.writestr(name, CHART)
                with self.assertRaisesRegex(ValueError, "expected one .sm"):
                    importer.extract_bundle(archive, root / "output")

    def test_failed_download_preserves_previous_file_and_removes_partial(self):
        response = BytesIO(b"partial")
        response.headers = {"Content-Length": "100"}
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "source.zip"
            output.write_bytes(b"previous")
            with patch.object(importer, "urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    importer.download("https://example.com", output)
            self.assertEqual(output.read_bytes(), b"previous")
            self.assertFalse(output.with_name("source.zip.part").exists())

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "magick")),
                         "requires desktop conversion tools")
    def test_import_rerun_and_repair_are_usable_by_game(self):
        from pi_dance.songs import discover_songs
        from pi_dance.charts import load_sm

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture.zip"
            synthetic_zip(fixture)
            destination = root / "songs"

            def download(url, output):
                if "viewsimfile" in url:
                    output.write_text(PAGE)
                else:
                    shutil.copyfile(fixture, output)

            with patch.object(importer, "download", side_effect=download) as network:
                importer.import_song(123, destination)
                self.assertEqual(network.call_count, 2)
            bundle = destination / "ziv-123"
            runtime = [bundle / name for name in ("song.wav", "song.bmp")]
            timestamps = [path.stat().st_mtime_ns for path in runtime]
            metadata = json.loads((bundle / "song.json").read_text())
            self.assertNotIn("chart_difficulty", metadata)
            self.assertNotIn("chart_meter", metadata)
            metadata["title"] = "My edited title"
            importer.write_json(bundle / "song.json", metadata)

            with patch.object(importer, "download", side_effect=AssertionError("unexpected network")):
                importer.import_song(123, destination)
                self.assertEqual(timestamps, [path.stat().st_mtime_ns for path in runtime])
                (bundle / "chart.sm").unlink()
                (bundle / "song.bmp").unlink()
                (bundle / "song.wav").unlink()
                importer.import_song(123, destination)
            songs = discover_songs(destination)
            self.assertEqual(len(songs), 1)
            self.assertEqual(songs[0].title, "My edited title")
            self.assertTrue(load_sm(songs[0].chart_path).charts)
            self.assertTrue(importer.prepare_songs.wav_matches_runtime_format(songs[0].audio_path))
            self.assertTrue(songs[0].cover_path.is_file())

    def test_failed_cover_conversion_does_not_publish_partial_cover(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            synthetic_zip(archive)
            bundle = importer.extract_bundle(archive, root / "output")
            (bundle / "song.wav").write_bytes(b"existing")

            def broken_cover(source, output):
                output.write_bytes(b"incomplete")
                raise subprocess.CalledProcessError(1, "magick")

            with patch.object(importer.prepare_songs, "audio_duration_seconds", return_value=1), \
                    patch.object(importer.prepare_songs, "wav_matches_runtime_format", return_value=True), \
                    patch.object(importer.prepare_songs, "create_cover", side_effect=broken_cover):
                with self.assertRaises(subprocess.CalledProcessError):
                    importer.prepare_songs.prepare_song(bundle, False, False)
            self.assertFalse((bundle / "song.bmp").exists())
            self.assertFalse((bundle / "song.json").exists())


if __name__ == "__main__":
    unittest.main()
