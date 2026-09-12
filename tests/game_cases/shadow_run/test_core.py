from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

import pygame
from unittest.mock import patch

from games.shadow_run.core import Beat, Lane, Stamina, TerrainGenerator, TerrainTimeline, difficulty_at, is_safe_transition, is_valid_stance, lane_contacts, scroll_distance, time_at_scroll_distance
from games.shadow_run.songs import SCHEMA_VERSION, load_song, sidecar_path_for
from common.input import Action, actions_from_event
from common.console_input import KEY_SEQUENCES
from games.shadow_run.main import command_arguments
from games.shadow_run.app import App, visible_song_window
from games.shadow_run.config import load_settings


class CoreTests(unittest.TestCase):
    def test_cardinal_actions_become_wide_lanes(self):
        self.assertEqual(lane_contacts({"left", "up", "down"}), {Lane.LEFT, Lane.CENTER})

    def test_three_by_three_debug_keyboard_layout_uses_broad_lanes(self):
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q)), [Action.LEFT])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x)), [Action.UP])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c)), [Action.RIGHT])

    def test_framebuffer_keyboard_uses_the_same_three_column_layout(self):
        self.assertEqual(KEY_SEQUENCES[b"q"], Action.LEFT)
        self.assertEqual(KEY_SEQUENCES[b"x"], Action.UP)
        self.assertEqual(KEY_SEQUENCES[b"c"], Action.RIGHT)

    def test_individual_pad_buttons_preserve_broad_contacts_until_each_releases(self):
        app = object.__new__(App)
        app.pad_buttons, app.held, app.keyboard_until = set(), set(), {}
        app._record_pad_button(6, True)
        app._record_pad_button(0, True)
        app._record_pad_button(3, True)
        self.assertEqual(lane_contacts(app._contact_actions()), {Lane.LEFT, Lane.RIGHT})
        app._record_pad_button(6, False)
        self.assertEqual(lane_contacts(app._contact_actions()), {Lane.LEFT, Lane.RIGHT})
        app._record_pad_button(0, False)
        self.assertEqual(lane_contacts(app._contact_actions()), {Lane.RIGHT})

    def test_every_outer_pad_column_maps_to_one_broad_lane(self):
        self.assertTrue(all(actions_from_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=button)) == [Action.LEFT] for button in (6, 0, 4)))
        self.assertTrue(all(actions_from_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=button)) == [Action.RIGHT] for button in (7, 3, 5)))
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=2)), [Action.UP])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1)), [Action.DOWN])

    def test_f1_uses_the_shared_select_action(self):
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)), [Action.SELECT])
        self.assertIs(KEY_SEQUENCES[b"\x1bOP"], Action.SELECT)

    def test_pause_and_leave_text_are_configurable(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "shadow-run.ini"
            path.write_text("[gameplay]\npause_text = Stop\nexit_confirmation_text = Leave?\nexit_confirm_button = Yes\nexit_cancel_button = No\n")
            settings = load_settings(path)
        self.assertEqual((settings.pause_text, settings.exit_confirmation_text), ("Stop", "Leave?"))
        self.assertEqual((settings.exit_confirm_button, settings.exit_cancel_button), ("Yes", "No"))

    def test_provider_runner_arguments_are_not_parsed_as_game_arguments(self):
        with patch("games.shadow_run.main.sys.argv", ["/x/runner.py", "shadow-run", "games.shadow_run.main"]):
            self.assertEqual(command_arguments(), [])
        self.assertEqual(command_arguments(["--seed", "4"]), ["--seed", "4"])

    def test_song_window_keeps_wrapped_selection_visible(self):
        self.assertEqual(visible_song_window(0, 10, 19), 1)
        self.assertEqual(visible_song_window(9, 0, 19), 0)
        self.assertEqual(visible_song_window(4, 7, 8), 0)

    def test_transitions_keep_a_lane_occupied(self):
        self.assertTrue(is_safe_transition((Lane.LEFT, Lane.CENTER), (Lane.CENTER, Lane.RIGHT)))
        self.assertFalse(is_safe_transition((Lane.LEFT, Lane.LEFT), (Lane.RIGHT, Lane.RIGHT)))

    def test_stance_requires_no_extra_danger_contact(self):
        self.assertTrue(is_valid_stance({Lane.LEFT, Lane.CENTER}, (Lane.LEFT, Lane.CENTER)))
        self.assertFalse(is_valid_stance({Lane.LEFT, Lane.CENTER, Lane.RIGHT}, (Lane.LEFT, Lane.CENTER)))

    def test_single_lane_stance_requires_two_physical_contacts(self):
        self.assertFalse(is_valid_stance({Lane.LEFT: 1}, (Lane.LEFT, Lane.LEFT)))
        self.assertTrue(is_valid_stance({Lane.LEFT: 2}, (Lane.LEFT, Lane.LEFT)))

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

    def test_timeline_plans_future_change_without_activating_it_early(self):
        timeline = TerrainTimeline((Beat(3.0, 1.0, True),), seed=1)
        timeline.plan_to(4.0, 30)
        self.assertEqual(timeline.stance_at(2.0), (Lane.LEFT, Lane.CENTER))
        self.assertNotEqual(timeline.stance_at(3.1), (Lane.LEFT, Lane.CENTER))
        self.assertTrue(timeline.in_transition_window(3.0, 30))

    def test_prepared_timeline_is_fixed_and_uses_exact_beat_time(self):
        timeline = TerrainTimeline((Beat(3.037, 1.0, True),), seed=1)
        timeline.prepare_song(8.0)
        self.assertEqual(timeline.changes[0].time, 3.037)
        planned = tuple(timeline.changes)
        self.assertEqual(tuple(timeline.changes), planned)

    def test_prepared_tile_rows_are_immutable_and_follow_scroll_distance(self):
        timeline = TerrainTimeline((Beat(3.037, 1.0, True),), seed=1)
        timeline.prepare_song(8.0)
        rows = timeline.tile_stances(8.0, 30)
        self.assertEqual(rows, timeline.tile_stances(8.0, 30))
        self.assertEqual(time_at_scroll_distance(scroll_distance(3.0, 8.0), 8.0), 3.0)
        self.assertEqual(rows[0], timeline.initial_stance)

    def test_timeline_reports_the_boundary_that_has_crossed_the_receptor(self):
        timeline = TerrainTimeline((Beat(3.0, 1.0, True),), seed=1)
        timeline.prepare_song(8.0)
        self.assertIsNone(timeline.latest_change_at(2.9))
        self.assertEqual(timeline.latest_change_at(3.1).time, 3.0)

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

    def test_song_uses_dance_bundle_cover_when_present(self):
        with TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"; bundle.mkdir()
            audio = bundle / "song.wav"; audio.write_bytes(b"x")
            cover = bundle / "jacket.bmp"; cover.write_bytes(b"x")
            (bundle / "song.json").write_text('{"title": "Cover", "cover": "jacket.bmp"}')
            sidecar_path_for(audio).write_text(json.dumps({"schema_version": SCHEMA_VERSION, "source": {"file": "song.wav", "size": 1, "mtime_ns": audio.stat().st_mtime_ns}, "duration": 3, "tempo_bpm": 120, "beats": []}))
            self.assertEqual(load_song(audio).cover_path, cover)
