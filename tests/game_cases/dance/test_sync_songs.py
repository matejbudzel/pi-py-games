import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[3] / "src" / "games" / "dance" / "scripts"))
import sync_songs


def make_library(root: Path) -> Path:
    source = root / "source"
    bundle = source / "Song with spaces"
    bundle.mkdir(parents=True)
    metadata = {"title": "Example", "duration_seconds": 30,
                "audio": "song.wav", "chart": "original.sm", "cover": "song.bmp"}
    (bundle / "song.json").write_text(json.dumps(metadata))
    for name in ("song.wav", "song.bmp", "original.sm", "original.ogg", "original.ssc", "jacket.png", "source.txt"):
        (bundle / name).write_text(name)
    (source / ".ziv-cache").mkdir()
    (source / ".ziv-cache" / "source.zip").write_text("cache")
    (source / "list.txt").write_text("123 # Example\n")
    return source


class SyncSongsTests(unittest.TestCase):
    def test_remote_locations_and_remote_to_remote_rejection(self):
        self.assertEqual(sync_songs.remote_location("matej@devbox:/home/matej/pi-dance-songs"),
                         ("matej@devbox", "/home/matej/pi-dance-songs"))
        self.assertIsNone(sync_songs.remote_location("/tmp/local:songs"))
        self.assertEqual(sync_songs.remote_location("matej@[::1]:songs"), ("matej@[::1]", "songs"))
        with patch.object(sync_songs.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "one end"):
                sync_songs.sync_songs("devbox:/songs", "pi:/songs")
            run.assert_not_called()

    @unittest.skipUnless(shutil.which("rsync"), "requires rsync")
    def test_pull_runs_remote_scanner_and_transfers_only_runtime_files(self):
        with TemporaryDirectory(prefix="song's library ") as temporary:
            root = Path(temporary)
            source = make_library(root)
            destination = root / "destination"
            real_run = subprocess.run

            def local_transport(command, **kwargs):
                if command[0] == "ssh":
                    self.assertEqual(command[:3], ["ssh", "--", "matej@devbox"])
                    worker = shlex.split(command[3])
                    self.assertEqual(worker, ["python3", "-", "--manifest", str(source)])
                    # Execute exactly the script sent to SSH, using a local Python.
                    return real_run([sys.executable, *worker[1:]], **kwargs)
                self.assertEqual(command[0], "rsync")
                self.assertEqual(command[-2], f"matej@devbox:{source}/")
                return real_run([*command[:-2], str(source) + "/", command[-1]], **kwargs)

            with patch.object(sync_songs.subprocess, "run", side_effect=local_transport):
                self.assertEqual(sync_songs.sync_songs(f"matej@devbox:{source}", str(destination), True), 0)
                self.assertFalse(destination.exists())
                self.assertEqual(sync_songs.sync_songs(f"matej@devbox:{source}", str(destination)), 0)
            copied = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
            self.assertEqual(copied, set(sync_songs.runtime_files(source)))

    def test_failed_remote_scan_does_not_start_rsync(self):
        with patch.object(sync_songs.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "ssh")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                sync_songs.sync_songs("devbox:/missing", "/tmp/destination")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], "ssh")

    def test_manifest_follows_metadata_and_allows_missing_cover(self):
        with TemporaryDirectory() as temporary:
            source = make_library(Path(temporary))
            bundle = source / "Song with spaces"
            metadata = json.loads((bundle / "song.json").read_text())
            (bundle / "nested").mkdir()
            (bundle / "original.sm").rename(bundle / "nested" / "custom.sm")
            metadata["chart"] = "nested/custom.sm"
            (bundle / "song.json").write_text(json.dumps(metadata))
            (bundle / "song.bmp").unlink()
            files = sync_songs.runtime_files(source)
            self.assertEqual({str(path.relative_to(bundle.name)) for path in files},
                             {"song.json", "song.wav", "nested/custom.sm"})

    def test_missing_audio_or_escaping_path_stops_before_rsync(self):
        for audio in ("missing.wav", "../outside.wav", "/tmp/outside.wav"):
            with self.subTest(audio=audio), TemporaryDirectory() as temporary:
                source = make_library(Path(temporary))
                path = source / "Song with spaces" / "song.json"
                metadata = json.loads(path.read_text())
                metadata["audio"] = audio
                path.write_text(json.dumps(metadata))
                with patch.object(sync_songs.subprocess, "run") as run:
                    with self.assertRaises(ValueError):
                        sync_songs.sync_songs(source, "pi:/songs/")
                    run.assert_not_called()

    @unittest.skipUnless(shutil.which("rsync"), "requires rsync")
    def test_real_sync_preview_incremental_update_and_exclusions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_library(root)
            destination = root / "destination with spaces"
            self.assertEqual(sync_songs.sync_songs(source, str(destination), dry_run=True), 0)
            self.assertFalse(destination.exists())
            self.assertEqual(sync_songs.sync_songs(source, str(destination)), 0)
            files = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
            self.assertEqual(files, set(sync_songs.runtime_files(source)))
            audio = destination / "Song with spaces" / "song.wav"
            before = audio.stat().st_mtime_ns
            self.assertEqual(sync_songs.sync_songs(source, str(destination)), 0)
            self.assertEqual(audio.stat().st_mtime_ns, before)
            extra = destination / "unrelated.txt"
            extra.write_text("keep")
            (source / "Song with spaces" / "original.sm").write_text("changed chart content")
            self.assertEqual(sync_songs.sync_songs(source, str(destination)), 0)
            self.assertEqual((destination / "Song with spaces" / "original.sm").read_text(), "changed chart content")
            self.assertTrue(extra.exists())


if __name__ == "__main__":
    unittest.main()
