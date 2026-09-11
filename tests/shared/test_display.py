import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from common.display import DisplaySettings, GameDisplay, display_settings, prepare_pygame_display


class DisplaySettingsTests(unittest.TestCase):
    def test_provider_environment_overrides_portable_defaults(self):
        with patch.dict(os.environ, {
            "PI_PY_GAMES_DISPLAY_BACKEND": "fbdev",
            "PI_PY_GAMES_FRAMEBUFFER": "/dev/fb1",
        }, clear=False):
            settings = display_settings()

        self.assertEqual(settings, DisplaySettings("fbdev", Path("/dev/fb1")))

    def test_fbdev_session_uses_dummy_sdl_and_presents_canvas(self):
        presenter = Mock()
        presenter.canvas = Mock()
        with patch.dict(os.environ, {}, clear=False), patch("common.display.pygame.display.set_mode") as set_mode:
            prepare_pygame_display(DisplaySettings("fbdev"))
            display = GameDisplay(DisplaySettings("fbdev"), (320, 240), presenter_factory=Mock(return_value=presenter))
            display.present()
            display.close()

        set_mode.assert_called_once_with((1, 1))
        presenter.present.assert_called_once_with(presenter.canvas, None)
        presenter.close.assert_called_once()
