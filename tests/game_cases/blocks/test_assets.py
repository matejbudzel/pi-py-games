from pathlib import Path

import pygame


BACKGROUND_DIRECTORY = Path(__file__).resolve().parents[3] / "src/games/blocks/assets/backgrounds"


def test_backgrounds_are_present_at_the_logical_canvas_size():
    for name in ("splash", "game", "result"):
        assert pygame.image.load(BACKGROUND_DIRECTORY / f"{name}.png").get_size() == (427, 240)
