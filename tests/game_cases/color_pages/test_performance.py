from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from common.input import Action
from common.performance import FrameTiming
from games.color_pages.main import App


class PixelColorsPerformanceTests(unittest.TestCase):
    def test_f8_action_toggles_the_developer_performance_hud(self) -> None:
        app = App()

        app.handle(Action.DEBUG_TOGGLE_PERFORMANCE)

        self.assertTrue(app.show_performance_hud)

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
