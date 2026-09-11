import os
from pathlib import Path
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


ASSET_DIRECTORY = Path(__file__).parents[1] / "src" / "games" / "dance" / "assets" / "gameplay"


class GameplayAssetTests(unittest.TestCase):
    def test_gameplay_sprites_use_their_expected_sizes(self) -> None:
        for name, size in (("arrow.png", 32), ("arrow-flow.png", 32), ("star.png", 32), ("heart.png", 128), ("thumb.png", 128), ("shrug.png", 128), ("fallback-cover.bmp", 256)):
            with self.subTest(name=name):
                self.assertEqual(pygame.image.load(ASSET_DIRECTORY / name).get_size(), (size, size))
