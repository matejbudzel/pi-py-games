import argparse
import logging
import os
import shutil
import sys
import time

from .config import SETTINGS
from .error_logging import configure_logging


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-rpi-launcher",
        action="store_true",
        help="show the Raspberry Pi launcher loading screen and suppress terminal output",
    )
    return parser.parse_args(argv)


def _show_launcher_splash() -> None:
    """Draw a temporary terminal screen until the game takes over the display."""
    if not sys.stdout.isatty():
        return
    columns, rows = shutil.get_terminal_size(fallback=(80, 24))
    message = "[ ... spúšťam ... ]"
    padding = " " * max(0, (columns - len(message)) // 2)
    before = "\n" * max(0, rows // 2 - 1)
    sys.stdout.write(f"\033[2J\033[H{before}{padding}{message}\n")
    sys.stdout.flush()


def _sink_terminal_output() -> None:
    """Keep SDL and Python diagnostics out of the launcher's terminal."""
    sys.stdout.flush()
    sys.stderr.flush()
    descriptor = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(descriptor, sys.stdout.fileno())
        os.dup2(descriptor, sys.stderr.fileno())
    finally:
        os.close(descriptor)


def _application_types():
    """Import Pygame only after a launcher loading screen has been painted."""
    from .app import App, Screen
    return App, Screen


def main(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(argv)
    if arguments.from_rpi_launcher:
        _show_launcher_splash()
        _sink_terminal_output()
    configure_logging(SETTINGS.error_log)
    app_type, screen_type = _application_types()
    restarting = False
    retry_delay = 1
    try:
        while True:
            started_at = time.monotonic()
            try:
                app = app_type()
                if restarting:
                    app.current_screen = screen_type.SONG_LIST
                app.run()
                return
            except Exception:
                logging.getLogger(__name__).exception("Application failed; restarting at song list")
                app = None
                restarting = True
                if time.monotonic() - started_at > 60:
                    retry_delay = 1
                time.sleep(retry_delay)
                retry_delay = min(30, retry_delay * 2)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped by keyboard interrupt")


if __name__ == "__main__":
    main()
