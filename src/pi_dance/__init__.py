"""Compatibility namespace for code that still imports the former package.

The game implementation lives in :mod:`games.dance`; this shim can be removed
after downstream configurations have migrated.
"""

from games import dance as _dance
import sys

from common import console_input, display_monitor, error_logging, fbdev, input, joystick_input, performance

__path__ = _dance.__path__

for _name, _module in {
    "console_input": console_input,
    "display_monitor": display_monitor,
    "error_logging": error_logging,
    "fbdev": fbdev,
    "input": input,
    "joystick_input": joystick_input,
    "performance": performance,
}.items():
    sys.modules[f"{__name__}.{_name}"] = _module
