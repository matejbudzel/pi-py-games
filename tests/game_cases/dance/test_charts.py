import unittest

from pi_dance.charts import parse_sm


SM = """
#OFFSET:1.0;
#BPMS:0.0=120.0,4.0=60.0;
#NOTES:
     dance-single:
     :
     Beginner:
     1:
     0:
1000
0100
0010
0001
,
1000
0000
0000
0000
;
#NOTES:
     dance-single:
     :
     Hard:
     8:
     0:
0000
0001
0000
0000
;
"""


class StepManiaChartTests(unittest.TestCase):
    def test_returns_every_dance_single_chart(self) -> None:
        charts = parse_sm(SM)

        self.assertEqual([chart.difficulty for chart in charts.charts], ["Beginner", "Hard"])
        self.assertEqual([chart.meter for chart in charts.charts], [1, 8])

    def test_converts_rows_and_bpm_changes_to_absolute_timestamps(self) -> None:
        beginner = parse_sm(SM).charts[0]

        self.assertEqual([note.direction for note in beginner.notes], ["left", "down", "up", "right", "left"])
        self.assertEqual([note.timestamp for note in beginner.notes], [1.0, 1.5, 2.0, 2.5, 3.0])

    def test_parses_holds_and_ignores_rolls_and_mines(self) -> None:
        charts = parse_sm("#BPMS:0=120; #NOTES:dance-single::Easy:2:0:2000\n3000\n4000\nM000;")

        self.assertEqual(len(charts.charts[0].notes), 1)
        self.assertEqual(charts.charts[0].notes[0].timestamp, 0)
        self.assertEqual(charts.charts[0].notes[0].end_timestamp, 0.5)

    def test_lifts_get_a_one_beat_lead_in_and_release_arrow(self) -> None:
        chart = parse_sm("#BPMS:0=120; #NOTES:dance-single::Hard:7:0:L000;").charts[0]
        self.assertEqual(chart.notes[0].direction, "left")
        self.assertEqual(chart.notes[0].timestamp, -0.5)
        self.assertEqual(chart.notes[0].end_timestamp, 0)
        self.assertTrue(chart.notes[0].is_lift)
        self.assertEqual(chart.notes[0].arrow_timestamp, 0)

    def test_lift_lead_in_stops_at_previous_same_lane_note(self) -> None:
        chart = parse_sm("#BPMS:0=120; #NOTES:dance-single::Hard:7:0:0000\n1000\nL000\n0000\n0000\n0000\n0000\n0000;").charts[0]
        lift = next(note for note in chart.notes if note.is_lift)
        self.assertEqual(lift.timestamp, 0.25)
        self.assertEqual(lift.end_timestamp, 0.5)

    def test_lift_lead_in_uses_bpm_timing_and_notes_stay_sorted(self) -> None:
        chart = parse_sm("#OFFSET:1; #BPMS:0=120,4=60; #NOTES:dance-single::Hard:7:0:0000,0000\nL100\n0000\n0000\n0000\n0000\n0000\n0000;").charts[0]
        lift = chart.notes[0]
        self.assertTrue(lift.is_lift)
        self.assertEqual(lift.timestamp, 2.75)
        self.assertEqual(lift.end_timestamp, 3.5)
        self.assertEqual([note.timestamp for note in chart.notes], sorted(note.timestamp for note in chart.notes))

    def test_hold_crosses_measure_and_bpm_change(self) -> None:
        chart = parse_sm("#OFFSET:1; #BPMS:0=120,4=60; #NOTES:dance-single::Easy:2:0:2000,0000\n3000;").charts[0]
        self.assertEqual(chart.notes[0].timestamp, 1)
        self.assertEqual(chart.notes[0].end_timestamp, 5)
