import unittest

from common.assets import SWEET16_FONT_PATH
from games.dance.config import FONT_PATH


class SharedAssetsTests(unittest.TestCase):
    def test_sweet16_is_a_shared_font_used_by_dance(self):
        self.assertTrue(SWEET16_FONT_PATH.is_file())

    def test_shadow_run_song_list_background_is_shipped(self):
        from games.shadow_run.app import FOOT_LEFT_PATH, FOOT_RIGHT_PATH, GAMEPLAY_BACKGROUND_PATH, MENU_BACKGROUND_PATH, PICNIC_FINISH_PATH, RESULT_FAILED_PATH, RESULT_SUCCESS_PATH, RUNNER_HAPPY_PATH, RUNNER_JUMP_PATH, RUNNER_READY_PATH, RUNNER_STRUGGLING_PATH, RUNNER_TIRED_PATH, TERRAIN_LAWN_PATH
        self.assertTrue(all(path.is_file() for path in (MENU_BACKGROUND_PATH, GAMEPLAY_BACKGROUND_PATH, TERRAIN_LAWN_PATH, PICNIC_FINISH_PATH, FOOT_LEFT_PATH, FOOT_RIGHT_PATH, RUNNER_READY_PATH, RUNNER_JUMP_PATH, RUNNER_HAPPY_PATH, RUNNER_STRUGGLING_PATH, RUNNER_TIRED_PATH, RESULT_FAILED_PATH, RESULT_SUCCESS_PATH)))
        self.assertEqual(FONT_PATH, SWEET16_FONT_PATH)
