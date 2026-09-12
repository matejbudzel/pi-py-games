from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

import pygame
from unittest.mock import patch

from games.shadow_run.core import Beat, Lane, Stamina, TerrainGenerator, difficulty_at, is_safe_transition, is_valid_stance, lane_contacts
from games.shadow_run.songs import SCHEMA_VERSION, load_song, sidecar_path_for
from common.input import Action, actions_from_event
from games.shadow_run.main import command_arguments


class CoreTests(unittest.TestCase):
    def test_cardinal_actions_become_wide_lanes(self):
        self.assertEqual(lane_contacts({"left", "up", "down"}), {Lane.LEFT, Lane.CENTER})

    def test_three_by_three_debug_keyboard_layout_uses_broad_lanes(self):
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q)), [Action.LEFT])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x)), [Action.UP])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c)), [Action.RIGHT])

    def test_provider_runner_arguments_are_not_parsed_as_game_arguments(self):
        with patch("games.shadow_run.main.sys.argv", ["/x/runner.py", "shadow-run", "games.shadow_run.main"]):
            self.assertEqual(command_arguments(), [])
        self.assertEqual(command_arguments(["--seed", "4"]), ["--seed", "4"])

    def test_transitions_keep_a_lane_occupied(self):
        self.assertTrue(is_safe_transition((Lane.LEFT, Lane.CENTER), (Lane.CENTER, Lane.RIGHT)))
        self.assertFalse(is_safe_transition((Lane.LEFT, Lane.LEFT), (Lane.RIGHT, Lane.RIGHT)))

    def test_stance_requires_no_extra_danger_contact(self):
        self.assertTrue(is_valid_stance({Lane.LEFT, Lane.CENTER}, (Lane.LEFT, Lane.CENTER)))
        self.assertFalse(is_valid_stance({Lane.LEFT, Lane.CENTER, Lane.RIGHT}, (Lane.LEFT, Lane.CENTER)))

    def test_generator_never_demands_two_feet_move(self):
        generator = TerrainGenerator(seed=4)
        old = generator.stance
        for now in range(5, 90, 5):
            new = generator.advance(float(now), 100)
            if new:
                self.assertTrue(is_safe_transition(old, new))
                old = new

    def test_accented_beat_schedules_change_after_minimum_segment(self):
        generator = TerrainGenerator((Beat(3.0, 1.0, True),), seed=1)
        self.assertIsNone(generator.advance(1.0, 30))
        self.assertIsNotNone(generator.advance(3.0, 30))

    def test_difficulty_gradually_changes_multiple_values(self):
        early, late = difficulty_at(0, 100), difficulty_at(100, 100)
        self.assertLess(early.speed, late.speed)
        self.assertGreater(early.min_segment, late.min_segment)
        self.assertGreater(early.transition_window, late.transition_window)

    def test_stamina_grace_and_damage(self):
        stamina = Stamina()
        stamina.update(1, 1, False, True)
        self.assertEqual(stamina.value, 100)
        stamina.update(2, 1, False, False)
        self.assertLess(stamina.value, 100)

    def test_sidecar_rejects_stale_and_malformed_files(self):
        with TemporaryDirectory() as temp:
            audio = Path(temp) / "song.wav"; audio.write_bytes(b"x")
            sidecar_path_for(audio).write_text(json.dumps({"schema_version": SCHEMA_VERSION, "source": {"file": "song.wav", "size": 1, "mtime_ns": audio.stat().st_mtime_ns}, "duration": 3, "tempo_bpm": 120, "beats": []}))
            self.assertIsNotNone(load_song(audio))
            audio.write_bytes(b"xx")
            self.assertIsNone(load_song(audio))
            sidecar_path_for(audio).write_text("not json")
            self.assertIsNone(load_song(audio))

    def test_song_uses_existing_bundle_title_when_sidecar_has_no_title(self):
        with TemporaryDirectory() as temp:
            bundle = Path(temp) / "ziv-1"; bundle.mkdir()
            audio = bundle / "song.wav"; audio.write_bytes(b"x")
            (bundle / "song.json").write_text('{"title": "A Real Song"}')
            sidecar_path_for(audio).write_text(json.dumps({"schema_version": SCHEMA_VERSION, "source": {"file": "song.wav", "size": 1, "mtime_ns": audio.stat().st_mtime_ns}, "duration": 3, "tempo_bpm": 120, "beats": []}))
            self.assertEqual(load_song(audio).title, "A Real Song")
