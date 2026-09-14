import tempfile
import unittest
from pathlib import Path

from common.selection import visible_window
from games.winter_sports.courses import COURSES, PROFILES
from games.winter_sports.core import Run
from games.winter_sports.gestures import GestureTracker
from games.winter_sports.tuning import DEFAULTS, load, save
from games.winter_sports.speed_skating import LONG_TRACK, SHORT_TRACK, SpeedSkatingRun, point_at


class WinterSportsTests(unittest.TestCase):
    def test_gesture_detects_airborne_and_landing(self):
        tracker = GestureTracker()
        tracker.update({"left", "right"}, 1.0)
        airborne = tracker.update(set(), 1.2)
        landing = tracker.update({"left", "right", "up"}, 1.5)
        self.assertTrue(airborne.airborne)
        self.assertTrue(landing.landed)
        self.assertEqual(landing.row_transition, 1)

    def test_seeded_run_is_reproducible(self):
        args = (COURSES["Bobsleigh"][0], PROFILES["Bobsleigh"], dict(DEFAULTS), 7)
        one, two = Run(*args), Run(*args)
        tracker = GestureTracker()
        for tick in range(20):
            gesture = tracker.update({"left", "right"}, tick / 10)
            one.update(.1, gesture, "Bobsleigh"); two.update(.1, gesture, "Bobsleigh")
        self.assertEqual(one.distance, two.distance)
        self.assertEqual(one.wind, two.wind)

    def test_tuning_load_is_forward_compatible_and_resettable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            self.assertEqual(load(path), DEFAULTS)
            save(path, {**DEFAULTS, "wind": 1.2, "unused": 9})
            self.assertEqual(load(path)["wind"], 1.2)

    def test_shared_list_window_keeps_last_row_visible(self):
        self.assertEqual(visible_window(0, 9, 10, 4), 6)

    def test_oval_geometry_returns_to_its_start(self):
        for oval in (SHORT_TRACK, LONG_TRACK):
            start = point_at(oval, 0)
            finish = point_at(oval, oval.lap_metres)
            self.assertAlmostEqual(start[0], finish[0], places=3)
            self.assertAlmostEqual(start[1], finish[1], places=3)

    def test_both_contacts_brake_and_wall_collision_costs_speed(self):
        run = SpeedSkatingRun(SHORT_TRACK, speed=10, offset=SHORT_TRACK.track_width)
        standing = GestureTracker().update({"left", "right"}, 1)
        run.update(.1, standing)
        self.assertLess(run.speed, 10 * SHORT_TRACK.wall_speed_factor)
        self.assertEqual(run.collisions, 1)
