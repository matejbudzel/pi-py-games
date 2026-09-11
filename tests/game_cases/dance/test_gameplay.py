import unittest

from pi_dance.charts import Note
from pi_dance.gameplay import Judgement, Session


class SessionTests(unittest.TestCase):
    def test_hold_scores_once_at_tail_with_immediate_head_feedback(self) -> None:
        session = Session((Note(1, "left", 3),))
        self.assertIs(session.press("left", 1).judgement, Judgement.GREAT)
        self.assertEqual(session.judgements, [])
        self.assertEqual(session.expire(2), [])
        self.assertIs(session.expire(3)[0].judgement, Judgement.GREAT)
        self.assertEqual(len(session.judgements), 1)
        self.assertIsNone(session.release("left", 3.1))

    def test_early_release_earns_partial_credit_and_tail_tolerance_is_allowed(self) -> None:
        for release, expected, credit in ((2, Judgement.OK, 0.85), (2.9, Judgement.GREAT, 1)):
            session = Session((Note(1, "left", 3),))
            session.press("left", 1)
            self.assertIs(session.release("left", release).judgement, expected)
            session.expire(4)
            self.assertEqual(len(session.judgements), 1)
            self.assertEqual(session.judgements[0].credit, credit)

    def test_missed_head_remains_available_for_late_partial_hold(self) -> None:
        note = Note(1, "left", 5)
        session = Session((note,))
        self.assertEqual(session.expire(2), [])
        self.assertEqual(session.pending, [note])
        self.assertIs(session.press("left", 3).judgement, Judgement.OK)
        result = session.expire(5)[0]
        self.assertAlmostEqual(result.credit, 0.15)
        self.assertEqual(session.stars(), 2)

    def test_regrabbing_accumulates_only_time_actually_held(self) -> None:
        session = Session((Note(1, "left", 5),))
        session.press("left", 1)
        session.release("left", 2)
        self.assertEqual(session.judgements, [])
        session.press("left", 3)
        self.assertAlmostEqual(session.expire(5)[0].credit, 0.925)
        self.assertEqual(len(session.judgements), 1)
        self.assertEqual(session.stars(), 5)

    def test_unplayed_hold_expires_at_tail_without_blocking_tap_misses(self) -> None:
        hold, tap = Note(1, "left", 5), Note(2, "right")
        session = Session((hold, tap))
        self.assertEqual([result.note for result in session.expire(3)], [tap])
        self.assertEqual(session.pending, [hold])
        self.assertIs(session.expire(5)[0].judgement, Judgement.MISS)
        self.assertEqual(session.expire(6), [])
        self.assertIsNone(session.press("left", 6))

    def test_short_late_hold_gets_less_credit_than_long_late_hold(self) -> None:
        credits = []
        for start in (2, 3, 4.5):
            session = Session((Note(1, "left", 5),))
            session.press("left", start)
            credits.append(session.expire(5)[0].credit)
        for actual, expected in zip(credits, [0.225, 0.15, 0.0375]):
            self.assertAlmostEqual(actual, expected)

    def test_hold_does_not_block_other_lane_or_repeat_score(self) -> None:
        session = Session((Note(1, "left", 3), Note(2, "right")))
        session.press("left", 1)
        self.assertIsNone(session.press("left", 1.5))
        self.assertTrue(session.last_press_was_ignored)
        self.assertIs(session.press("right", 2).judgement, Judgement.GREAT)
        session.expire(3)
        self.assertEqual(session.stars(), 5)

    def test_judges_directional_notes_using_audio_time(self) -> None:
        session = Session((Note(1.0, "left"), Note(1.2, "right")))

        judgement = session.press("left", 1.08)

        self.assertIsNotNone(judgement)
        self.assertIs(judgement.judgement, Judgement.GREAT)
        self.assertEqual(len(session.pending), 1)

    def test_accepts_a_more_forgiving_ok_timing_window(self) -> None:
        session = Session((Note(1.0, "left"),))

        judgement = session.press("left", 1.26)

        self.assertIsNotNone(judgement)
        self.assertIs(judgement.judgement, Judgement.OK)

    def test_ignores_a_bounce_after_a_successful_hit(self) -> None:
        session = Session((Note(1.0, "left"),))

        session.press("left", 1.0)
        bounce = session.press("left", 1.06)

        self.assertIsNone(bounce)
        self.assertTrue(session.last_press_was_ignored)
        self.assertEqual(len(session.judgements), 1)

    def test_keeps_very_close_chart_notes_playable(self) -> None:
        session = Session((Note(1.0, "left"), Note(1.12, "right")))

        session.press("left", 1.0)
        close_note = session.press("right", 1.12)

        self.assertIsNotNone(close_note)
        self.assertFalse(session.last_press_was_ignored)

    def test_late_notes_become_misses(self) -> None:
        session = Session((Note(1.0, "left"), Note(2.0, "up")))

        misses = session.expire(1.29)

        self.assertEqual([result.judgement for result in misses], [Judgement.MISS])
        self.assertEqual([note.direction for note in session.pending], ["up"])

    def test_stars_are_always_at_least_one(self) -> None:
        session = Session((Note(1.0, "left"),))
        session.expire(2.0)

        self.assertEqual(session.stars(), 1)

    def test_perfect_song_earns_five_stars(self) -> None:
        session = Session((Note(1.0, "left"), Note(2.0, "up")))
        session.press("left", 1.0)
        session.press("up", 2.0)

        self.assertEqual(session.stars(), 5)
