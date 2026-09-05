import logging
import time

from .app import App, Screen
from .config import SETTINGS
from .error_logging import configure_logging


def main() -> None:
    configure_logging(SETTINGS.error_log)
    restarting = False
    retry_delay = 1
    try:
        while True:
            started_at = time.monotonic()
            try:
                app = App()
                if restarting:
                    app.current_screen = Screen.SONG_LIST
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
