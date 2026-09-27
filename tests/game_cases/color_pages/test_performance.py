from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pygame

from common.input import Action
from common.performance import FrameTiming
from games.color_pages.art import Page
from games.color_pages.main import ART_BACKGROUND, RAINBOW, App


class PixelColorsPerformanceTests(unittest.TestCase):
    @staticmethod
    def _page() -> Page:
        return Page("test", Path("test.png"), "test", 16, ((255, 0, 0),), tuple((0,) * 16 for _ in range(16)))

    def test_f8_action_toggles_the_developer_performance_hud(self) -> None:
        app = App()

        app.handle(Action.DEBUG_TOGGLE_PERFORMANCE)

        self.assertTrue(app.show_performance_hud)
        self.assertEqual(app.last_scale_ms, 0.0)

    def test_performance_report_includes_display_breakdown(self) -> None:
        app = App()
        app.performance.record(FrameTiming(render_ms=4.0, present_ms=7.0, frame_ms=20.0))
        app.presentation_frames = 2
        app.total_scale_ms = 6.0
        app.max_scale_ms = 4.0
        app.total_backend_present_ms = 10.0
        app.max_backend_present_ms = 7.0
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "pixel-colors-performance.txt"
            with patch("games.color_pages.main.PERFORMANCE_REPORT_PATH", report_path):
                app._write_performance_report()

            report = report_path.read_text(encoding="utf-8")

        self.assertIn("average_render_ms=4.000", report)
        self.assertIn("average_scale_ms=3.000", report)
        self.assertIn("maximum_backend_present_ms=7.000", report)

    def test_performance_hud_uses_the_recorded_scale_time(self) -> None:
        pygame.font.init()
        app = App()
        app.screen = pygame.Surface((427, 240))
        app.performance.record(FrameTiming(render_ms=4.0, frame_ms=20.0))
        app.last_scale_ms = 3.0

        app._performance_hud(pygame.font.Font(None, 16))

        self.assertEqual(app.last_scale_ms, 3.0)

    def test_normal_drawing_move_marks_only_the_old_and_new_cells_and_hud(self) -> None:
        app = App()
        app.pages = (self._page(),)
        app.screen_name = "drawing"
        app._needs_full_redraw = False

        app._track_action_redraw(Action.RIGHT)

        self.assertFalse(app._needs_full_redraw)
        self.assertEqual(len(app._drawing_dirty_rectangles), 2)
        self.assertTrue(app._drawing_hud_dirty)

    def test_modal_state_change_requires_a_single_full_redraw(self) -> None:
        app = App()
        app.pages = (self._page(),)
        app.screen_name = "drawing"
        app._needs_full_redraw = False

        app._track_action_redraw(Action.START)

        self.assertTrue(app._needs_full_redraw)
        self.assertEqual(app.modal_kind, "clear")

    def test_transparent_art_pixels_use_the_light_art_background(self) -> None:
        page = Page("test", Path("test.png"), "test", 16, ((255, 0, 0),), ((-1,) + (0,) * 15,) * 16)
        app = App()
        app.pages = (page,)
        app.screen = pygame.Surface((427, 240))

        preview = app._page_surface(page)
        rectangle = app._draw_drawing_cell(0, 0)

        self.assertEqual(preview.get_at((0, 0))[:3], ART_BACKGROUND)
        self.assertEqual(app.screen.get_at(rectangle.center)[:3], ART_BACKGROUND)
        self.assertEqual(app.screen.get_at((rectangle.x + 3, rectangle.y))[:3], RAINBOW[0])
