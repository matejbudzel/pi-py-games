import tempfile
import unittest
from pathlib import Path

from common.selection import visible_window
from games.winter_sports.courses import COURSES, PROFILES
from games.winter_sports.core import Run
from games.winter_sports.gestures import GestureTracker
from games.winter_sports.tuning import DEFAULTS, load, save


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
