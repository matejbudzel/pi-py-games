import unittest

from pi_dance.charts import Note
from pi_dance.gameplay import Judgement, Session


class LiftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.note = Note(1, "left", 3, is_lift=True)

    def test_release_edge_outweighs_full_interval_without_release(self) -> None:
        precise = Session((self.note,))
        precise.press("left", 2.8)
        result = precise.release("left", 3)
        self.assertAlmostEqual(result.credit, 0.73)
        held = Session((self.note,))
        held.press("left", 0)
        self.assertEqual(held.expire(3), [])
        self.assertAlmostEqual(held.expire(3.3)[0].credit, 0.3)
        self.assertGreater(result.credit, held.judgements[0].credit)

    def test_early_press_and_correct_release_earn_full_credit(self) -> None:
        session = Session((self.note,))
        session.press("left", 0)
        result = session.release("left", 3)
        self.assertEqual(result.credit, 1)
        self.assertIs(result.judgement, Judgement.GREAT)
        self.assertEqual(session.expire(4), [])
        self.assertEqual(len(session.judgements), 1)

    def test_partial_and_outside_intervals_keep_only_intersection_credit(self) -> None:
        for start, end, expected in ((0, 2, 0.15), (2, 4, 0.15), (0, 4, 0.3),
                                      (1.5, 2, 0.075), (-1, 0, 0), (4, 5, 0)):
            with self.subTest(start=start, end=end):
                session = Session((self.note,))
                session.press("left", start)
                session.release("left", end)
                session.expire(6)
                self.assertAlmostEqual(session.judgements[0].credit, expected)
                self.assertEqual(len(session.judgements), 1)

    def test_repressing_does_not_double_count_overlap(self) -> None:
        session = Session((self.note,))
        session.press("left", 1)
        session.release("left", 1.5)
        session.press("left", 2)
        session.press("left", 2.5)
        result = session.release("left", 3)
        self.assertAlmostEqual(result.credit, 0.925)

    def test_release_after_arrow_still_has_a_timing_window(self) -> None:
        session = Session((self.note,))
        session.press("left", 1)
        self.assertEqual(session.expire(3.1), [])
        self.assertAlmostEqual(session.release("left", 3.2).credit, 0.65)

    def test_unmatched_release_cannot_score_a_lift(self) -> None:
        session = Session((self.note,))
        self.assertIsNone(session.release("left", 3))
        self.assertEqual(session.expire(3.3)[0].credit, 0)

    def test_short_lift_cannot_score_without_any_overlap(self) -> None:
        session = Session((Note(1, "left", 1.1, is_lift=True),))
        session.press("left", 0.8)
        self.assertIsNone(session.release("left", 0.9))
        self.assertEqual(session.expire(2)[0].credit, 0)

    def test_hold_also_counts_press_before_and_release_after_interval(self) -> None:
        session = Session((Note(1, "left", 3),))
        session.press("left", 0)
        session.expire(1)
        self.assertIn("left", session.active_holds)
        session.release("left", 4)
        self.assertAlmostEqual(session.judgements[0].credit, 0.3)

    def test_held_panel_crossing_two_notes_only_scores_each_once(self) -> None:
        session = Session((Note(1, "left", 2), Note(3, "left", 4, is_lift=True)))
        session.press("left", 1)
        self.assertEqual(session.expire(2)[0].credit, 1)
        self.assertEqual(session.release("left", 4).credit, 1)
        self.assertEqual(session.expire(5), [])
        self.assertEqual(len(session.judgements), 2)
