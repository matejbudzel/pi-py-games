import unittest

from common.assets import SWEET16_FONT_PATH
from games.dance.config import FONT_PATH


class SharedAssetsTests(unittest.TestCase):
    def test_sweet16_is_a_shared_font_used_by_dance(self):
        self.assertTrue(SWEET16_FONT_PATH.is_file())
        self.assertEqual(FONT_PATH, SWEET16_FONT_PATH)
