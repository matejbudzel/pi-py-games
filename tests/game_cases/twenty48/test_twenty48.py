import random
import unittest

from games.twenty48.game import Board


class Twenty48BoardTests(unittest.TestCase):
    def test_move_merges_each_pair_once_and_adds_score(self):
        board = Board(cells=[[2, 2, 2, 2], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], random_source=random.Random(1))

        self.assertTrue(board.move("left"))

        self.assertEqual(board.cells[0][:3], [4, 4, 0])
        self.assertEqual(board.score, 8)

    def test_move_records_the_tile_paths_needed_by_the_animation(self):
        board = Board(cells=[[0, 2, 2, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], random_source=random.Random(1))

        board.move("left")

        self.assertEqual(
            [(motion.source, motion.destination, motion.value, motion.merged) for motion in board.last_moves],
            [((0, 1), (0, 0), 2, True), ((0, 2), (0, 0), 2, True)],
        )
        self.assertIsNotNone(board.last_spawn)

    def test_full_board_without_equal_neighbours_is_over(self):
        board = Board(cells=[
            [2, 4, 2, 4],
            [4, 2, 4, 2],
            [2, 4, 2, 4],
            [4, 2, 4, 2],
        ])

        self.assertTrue(board.game_over)
