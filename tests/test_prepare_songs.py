from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


MODULE_PATH = Path(__file__).parents[1] / "src" / "games" / "dance" / "scripts" / "prepare_songs.py"
SPEC = spec_from_file_location("prepare_songs", MODULE_PATH)
assert SPEC and SPEC.loader
prepare_songs = module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_songs
SPEC.loader.exec_module(prepare_songs)


class PrepareSongsTests(unittest.TestCase):
    def test_selects_beginner_chart(self) -> None:
        contents = """
#NOTES:dance-single::Hard:8:0:0000;
#NOTES:dance-single::Beginner:3:0:0000;
#NOTES:dance-double::Beginner:1:0:00000000;
"""
        self.assertEqual(prepare_songs.easiest_dance_single(contents), prepare_songs.ChartChoice("Beginner", 3))

    def test_uses_meter_when_difficulty_names_match(self) -> None:
        contents = "#NOTES:dance-single::Easy:5:0:0000; #NOTES:dance-single::Easy:2:0:0000;"
        self.assertEqual(prepare_songs.easiest_dance_single(contents), prepare_songs.ChartChoice("Easy", 2))

    def test_reads_a_basic_sm_tag(self) -> None:
        self.assertEqual(prepare_songs.sm_tag("#TITLE:Example Song;", "TITLE"), "Example Song")

    def test_prefers_existing_metadata_when_backfilling(self) -> None:
        generated = {"title": "Generated", "cover": "song.bmp", "chart_meter": 1}
        existing = {"title": "Hand-picked title", "chart_meter": 4}

        self.assertEqual(
            prepare_songs.merged_metadata(generated, existing, overwrite=False),
            {"title": "Hand-picked title", "cover": "song.bmp", "chart_meter": 4},
        )

    def test_prefers_jacket_over_other_images(self) -> None:
        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "Example"
            bundle.mkdir()
            (bundle / "Example.png").touch()
            (bundle / "Example-jacket.png").touch()
            (bundle / "song.bmp").touch()

            self.assertEqual(prepare_songs.input_cover(bundle).name, "Example-jacket.png")

    def test_recognises_only_the_low_bandwidth_runtime_wav_format(self) -> None:
        self.assertTrue(prepare_songs.is_runtime_wav_format({"codec_name": "pcm_s16le", "sample_rate": "22050", "channels": 2}))
        self.assertFalse(prepare_songs.is_runtime_wav_format({"codec_name": "pcm_s16le", "sample_rate": "44100", "channels": 2}))
        self.assertFalse(prepare_songs.is_runtime_wav_format({"codec_name": "pcm_s16le", "sample_rate": "22050", "channels": 1}))
