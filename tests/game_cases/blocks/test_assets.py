from pathlib import Path

import pygame


BACKGROUND_DIRECTORY = Path(__file__).resolve().parents[3] / "src/games/blocks/assets/backgrounds"


def test_backgrounds_are_present_at_the_logical_canvas_size():
    for name in ("splash", "game", "result"):
        image = pygame.image.load(BACKGROUND_DIRECTORY / f"{name}.png")
        assert image.get_size() == (427, 240)
        # Screens are retained and partially redrawn.  Their background must
        # replace old pixels rather than alpha-blending stale gameplay below.
        assert image.get_masks()[3] == 0
