import unittest

from common.performance import FrameTiming, PerformanceTracker


class PerformanceTrackerTests(unittest.TestCase):
    def test_report_includes_average_maximum_and_latest_timings(self) -> None:
        tracker = PerformanceTracker(started_at=10.0)
        tracker.record(FrameTiming(render_ms=5.0, frame_ms=20.0))
        tracker.record(FrameTiming(render_ms=9.0, frame_ms=40.0))

        report = tracker.report(now=12.0)

        self.assertIn("average_fps=1.00", report)
        self.assertIn("average_render_ms=7.000", report)
        self.assertIn("maximum_render_ms=9.000", report)
        self.assertIn("last_frame_ms=40.000", report)
