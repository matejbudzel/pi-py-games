import unittest

from common.assets import SWEET16_FONT_PATH
from games.dance.config import FONT_PATH


class SharedAssetsTests(unittest.TestCase):
    def test_sweet16_is_a_shared_font_used_by_dance(self):
        self.assertTrue(SWEET16_FONT_PATH.is_file())

    def test_shadow_run_song_list_background_is_shipped(self):
        from games.shadow_run.app import MENU_BACKGROUND_PATH
        self.assertTrue(MENU_BACKGROUND_PATH.is_file())
        self.assertEqual(FONT_PATH, SWEET16_FONT_PATH)
