import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from pi_dance.app import App, Screen
from pi_dance.charts import Chart, Note, SongCharts
from pi_dance.input import Action
from pi_dance.songs import Song, fallback_cover_path


class DifficultySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = App()
        self.song = Song("Example", Path("."), (255, 100, 150), Path("song.wav"),
                         Path("chart.sm"), fallback_cover_path(), 30)
        self.app.assets.covers[self.song.path] = pygame.image.load(fallback_cover_path()).convert()
        self.easy = Chart("Beginner", 1, (Note(1, "left"),))
        self.hard = Chart("Hard", 8, (Note(2, "right"),))

    def tearDown(self) -> None:
        pygame.quit()

    def prepare(self, charts: tuple[Chart, ...]) -> None:
        with patch("pi_dance.app.load_sm", return_value=SongCharts(0, charts)), \
             patch("pi_dance.app.pygame.mixer.music.load"):
            self.app._prepare_song(self.song)

    def test_easiest_is_focused_and_music_waits_for_confirmation(self) -> None:
        with patch("pi_dance.app.pygame.mixer.music.play") as play:
            self.prepare((self.hard, self.easy))
            self.app._update()
            self.assertIs(self.app.current_screen, Screen.DIFFICULTY)
            self.assertEqual(self.app.available_charts, (self.easy, self.hard))
            self.assertEqual(self.app.selected_difficulty, 0)
            self.assertIsNone(self.app.session)
            self.app._handle_action(Action.RIGHT)
            with patch("pi_dance.app.pygame.time.get_ticks", return_value=10000):
                self.app._handle_action(Action.START)
            self.assertIs(self.app.active_chart, self.hard)
            self.assertEqual(tuple(self.app.session.pending), self.hard.notes)
            self.assertIs(self.app.current_screen, Screen.COUNTDOWN)
            self.assertEqual(self.app.countdown_started_at, 10000)
            play.assert_not_called()
            with patch("pi_dance.app.pygame.time.get_ticks", return_value=13000):
                self.app._update()
            play.assert_called_once()
            self.assertIs(self.app.current_screen, Screen.PLAYING)

    def test_one_chart_skips_selection_and_no_charts_stays_in_menu(self) -> None:
        self.app.current_screen = Screen.SONG_LIST
        self.prepare(())
        self.assertIs(self.app.current_screen, Screen.SONG_LIST)
        self.prepare((self.easy,))
        self.assertIs(self.app.current_screen, Screen.COUNTDOWN)
        self.assertIs(self.app.active_chart, self.easy)

    def test_navigation_wraps_and_reentering_resets_focus(self) -> None:
        self.prepare((self.hard, self.easy))
        self.app._handle_action(Action.LEFT)
        self.assertEqual(self.app.selected_difficulty, 1)
        self.app._handle_action(Action.RIGHT)
        self.assertEqual(self.app.selected_difficulty, 0)
        self.app._handle_action(Action.RIGHT)
        self.prepare((self.hard, self.easy))
        self.assertEqual(self.app.selected_difficulty, 0)

    def test_exit_modal_cancel_preserves_focus_and_confirm_leaves_song(self) -> None:
        self.prepare((self.hard, self.easy))
        self.app._handle_action(Action.RIGHT)
        with patch("pi_dance.app.pygame.mixer.music.pause") as pause, \
             patch("pi_dance.app.pygame.mixer.music.unpause") as unpause:
            for cancel in (Action.SELECT, Action.START):
                self.app._handle_action(Action.SELECT)
                self.assertIs(self.app.current_screen, Screen.SONG_EXIT_CONFIRMATION)
                self.app._render()
                self.app._handle_action(cancel)
                self.assertIs(self.app.current_screen, Screen.DIFFICULTY)
                self.assertEqual(self.app.selected_difficulty, 1)
            pause.assert_not_called()
            unpause.assert_not_called()
        self.app._handle_action(Action.SELECT)
        self.app._handle_action(Action.RIGHT)
        self.app._handle_action(Action.START)
        self.assertIs(self.app.current_screen, Screen.SONG_LIST)
        self.assertIsNone(self.app.active_song)
        self.assertEqual(self.app.available_charts, ())

    def test_selector_replaces_receptors_and_focus_redraws_framebuffer(self) -> None:
        self.prepare((self.hard, self.easy))
        with patch("pi_dance.app.views.render_gameplay") as gameplay:
            self.app._render()
            gameplay.assert_not_called()
        self.assertTrue(self.app._dirty_rectangles())
        self.assertEqual(self.app._dirty_rectangles(), [])
        self.app._handle_action(Action.RIGHT)
        self.assertTrue(self.app._dirty_rectangles())
