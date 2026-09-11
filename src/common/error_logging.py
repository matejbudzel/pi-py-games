"""Bounded persistent diagnostics shared by every game process."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


DEFAULT_ERROR_LOG = Path("~/.local/state/pi-py-games/errors.log").expanduser()


def error_log_path() -> Path:
    return Path(os.environ.get("PI_PY_GAMES_ERROR_LOG", str(DEFAULT_ERROR_LOG))).expanduser()


def configure_logging(path: Path | None = None) -> None:
    """Send diagnostics from shared code and all games to one rotating log."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if any(getattr(handler, "_pi_py_games_log", False) for handler in logger.handlers):
        return
    for candidate in (path or error_log_path(), Path("/tmp/pi-py-games-errors.log")):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(candidate, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        except OSError:
            continue
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler._pi_py_games_log = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logging.getLogger("pi_py_games").info("Logging to %s", candidate)
        return
    logger.addHandler(logging.StreamHandler())
