import logging
import time

from .config import SETTINGS
from common.error_logging import configure_logging


def _application_types():
    """Import Pygame only when the game process is ready to own the display."""
    from .app import App, Screen
    return App, Screen


def main(argv: list[str] | None = None) -> None:
    configure_logging()
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
