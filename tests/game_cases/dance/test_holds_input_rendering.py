import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from pi_dance.app import App, Screen
from pi_dance.charts import Note
from pi_dance.gameplay import Judgement, Session
from pi_dance.input import Action, Release, actions_from_event
from pi_dance.songs import Song, fallback_cover_path
from pi_dance import views


class HoldInputRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = App()

    def tearDown(self) -> None:
        pygame.quit()

    def test_keyboard_and_pad_share_press_and_release_actions(self) -> None:
        for down, up, fields in ((pygame.KEYDOWN, pygame.KEYUP, {"key": pygame.K_LEFT}),
                                 (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, {"button": 0})):
            self.assertEqual(actions_from_event(pygame.event.Event(down, **fields)), [Action.LEFT])
            self.assertEqual(actions_from_event(pygame.event.Event(up, **fields)), [Release(Action.LEFT)])
        self.assertEqual(actions_from_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN)), [])

    def test_release_action_finishes_active_hold(self) -> None:
        self.app.current_screen = Screen.PLAYING
        self.app.session = Session((Note(0, "left", 10),))
        self.app._handle_action(Action.LEFT)
        self.app._handle_action(Release(Action.LEFT))
        self.assertEqual(self.app.session.active_holds, {})
        self.assertIs(self.app.feedback, Judgement.OK)

    def test_lift_scores_through_shared_release_action(self) -> None:
        self.app.current_screen = Screen.PLAYING
        self.app.session = Session((Note(1, "left", 3, is_lift=True),))
        with patch.object(self.app, "_song_position_seconds", return_value=1):
            self.app._handle_action(Action.LEFT)
        with patch.object(self.app, "_song_position_seconds", return_value=3):
            self.app._handle_action(Release(Action.LEFT))
        self.assertIs(self.app.feedback, Judgement.GREAT)
        self.assertEqual(self.app.session.judgements[0].credit, 1)

    def test_framebuffer_receives_tail_cleanup_after_release(self) -> None:
        song = Song("Example", Path("."), (255, 100, 150), Path("song.wav"),
                    Path("chart.sm"), fallback_cover_path(), 30)
        self.app.assets.covers[song.path] = pygame.image.load(fallback_cover_path()).convert()
        self.app.active_song = song
        self.app.current_screen = Screen.PLAYING
        self.app.framebuffer = object()
        self.app.session = Session((Note(0, "left", 3),))
        displayed = self.app.screen.copy()
        for time in (0, 0.5, 1):
            with patch.object(self.app, "_audio_position_seconds", return_value=time):
                if time == 0:
                    self.app._handle_action(Action.LEFT)
                elif time == 0.5:
                    self.app._handle_action(Release(Action.LEFT))
                self.app._render()
                for rectangle in self.app._dirty_rectangles():
                    displayed.blit(self.app.screen, rectangle, rectangle)
                self.assertTrue(pygame.image.tobytes(displayed, "RGB") == pygame.image.tobytes(self.app.screen, "RGB"), time)

    def test_cached_render_matches_full_render_for_moving_and_held_tails(self) -> None:
        self._compare_hold_frames({30: [("press", "left"), ("press", "right")]})

    def test_missed_and_regrabbed_tails_flow_and_clean_up(self) -> None:
        self._compare_hold_frames({45: [("press", "left")], 60: [("release", "left")],
                                   75: [("press", "left")]})

    def test_lift_tails_and_release_arrows_clean_up(self) -> None:
        self._compare_hold_frames({15: [("press", "left")], 90: [("release", "left")]},
                                  (Note(1, "left", 3, is_lift=True), Note(1, "right", 30, is_lift=True)))

    def test_tail_strip_matches_original_dots(self) -> None:
        colors = ((255, 75, 125), (255, 160, 65), (255, 225, 70), (80, 225, 130), (55, 225, 255), (175, 110, 255))
        expected = self.app.screen.copy()
        actual = expected.copy()
        clip = pygame.Rect(0, views.HEADER_HEIGHT, 854, 480 - views.HEADER_HEIGHT)
        expected.set_clip(clip)
        actual.set_clip(clip)
        # Include short tails, every colour phase, long offscreen tails,
        # fractional positions and the receptor clamp for active holds.
        for end in (1.01, 3, 30):
            note = Note(1, "left", end)
            for active in (False, True):
                for time in (0, 0.125, 0.5, 0.75, 1, 1.125, end - 0.01, end):
                    expected.fill((23, 34, 45))
                    actual.fill((23, 34, 45))
                    rectangle = views._hold_rectangle(note, time, active)
                    tail_y = 132 + (end - time) * 182
                    first = max(0, int((tail_y - 480 - 8) // 12))
                    for index in range(first, first + 40):
                        y = round(tail_y - index * 12)
                        if y < rectangle.top:
                            break
                        pygame.draw.circle(expected, colors[index % 6], (rectangle.centerx, y), 4)
                    views._render_hold_tail(actual, self.app.assets.hold_tail, rectangle, tail_y)
                    self.assertEqual(pygame.image.tobytes(actual, "RGB"), pygame.image.tobytes(expected, "RGB"),
                                     (end, active, time))

    def _compare_hold_frames(self, actions: dict[int, list[tuple[str, str]]], notes: tuple[Note, ...] | None = None) -> None:
        song = Song("Example", Path("."), (255, 100, 150), Path("song.wav"),
                    Path("chart.sm"), fallback_cover_path(), 30)
        self.app.assets.covers[song.path] = pygame.image.load(fallback_cover_path()).convert()
        session = Session(notes or (Note(1, "left", 3), Note(1, "right", 30)))
        base = views.create_gameplay_base(self.app.screen, self.app.assets, song)
        cached = base.copy()
        full = base.copy()
        previous = []
        for frame in [*range(121), *range(870, 940)]:
            time = frame / 30
            for operation, direction in actions.get(frame, []):
                getattr(session, operation)(direction, time)
            session.expire(time)
            arguments = (self.app.assets, song, session, time, time, None, 0,
                         self.app.receptor_glow_until, 10000)
            full.fill((0, 0, 0))
            views.render_gameplay(full, *arguments)
            previous, _ = views.render_cached_gameplay(cached, base, *arguments, None, previous)
            self.assertTrue(pygame.image.tobytes(cached, "RGB") == pygame.image.tobytes(full, "RGB"), time)
            if frame == 44:
                self.assertTrue(any(note.direction == "left" for note, _ in views._visible_holds(session, time)))
