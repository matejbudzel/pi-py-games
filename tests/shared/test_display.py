import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pygame

from common.display import DisplaySettings, GameDisplay, display_settings, initialize_pygame


class DisplaySettingsTests(unittest.TestCase):
    def test_provider_environment_overrides_portable_defaults(self):
        with patch.dict(os.environ, {
            "PI_PY_GAMES_DISPLAY_BACKEND": "fbdev",
            "PI_PY_GAMES_FRAMEBUFFER": "/dev/fb1",
        }, clear=False):
            settings = display_settings()

        self.assertEqual(settings, DisplaySettings("fbdev", Path("/dev/fb1")))

    def test_fbdev_session_does_not_open_an_sdl_window_and_presents_canvas(self):
        presenter = Mock()
        presenter.canvas = Mock()
        with patch("common.display.pygame.display.set_mode") as set_mode:
            display = GameDisplay(DisplaySettings("fbdev"), (320, 240), presenter_factory=Mock(return_value=presenter))
            display.present()
            display.close()

        set_mode.assert_not_called()
        presenter.present.assert_called_once_with(presenter.canvas, None)
        presenter.close.assert_called_once()

    def test_fbdev_initializes_fonts_without_sdl_video_or_input(self):
        with patch("common.display.pygame.init") as pygame_init, patch("common.display.pygame.font.init") as font_init:
            initialize_pygame(DisplaySettings("fbdev"))

        pygame_init.assert_not_called()
        font_init.assert_called_once()

    def test_logical_canvas_scales_to_output_before_fbdev_presentation(self):
        presenter = Mock()
        presenter.canvas = pygame.Surface((854, 480))
        display = GameDisplay(
            DisplaySettings("fbdev"), (854, 480), logical_size=(427, 240), presenter_factory=Mock(return_value=presenter)
        )

        with patch("common.display.pygame.transform.scale") as scale:
            display.present()

        self.assertEqual(display.canvas.get_bitsize(), presenter.canvas.get_bitsize())
        self.assertEqual(display.canvas.get_masks(), presenter.canvas.get_masks())
        scale.assert_called_once_with(display.canvas, (854, 480), presenter.canvas)
        presenter.present.assert_called_once_with(presenter.canvas, None)

    def test_logical_dirty_rectangles_scale_and_present_only_their_output_area(self):
        presenter = Mock()
        presenter.canvas = pygame.Surface((854, 480))
        display = GameDisplay(
            DisplaySettings("fbdev"), (854, 480), logical_size=(427, 240), presenter_factory=Mock(return_value=presenter)
        )

        with patch("common.display.pygame.transform.scale") as scale:
            display.present([pygame.Rect(10, 20, 30, 40)])

        self.assertEqual(scale.call_args.args[1], (60, 80))
        presenter.present.assert_called_once_with(presenter.canvas, [pygame.Rect(20, 40, 60, 80)])
