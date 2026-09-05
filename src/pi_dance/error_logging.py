"""Bounded persistent diagnostics for appliance recovery."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(path: Path) -> None:
    logger = logging.getLogger("pi_dance")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return
    for candidate in (path, Path("/tmp/pi-dance-errors.log")):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(candidate, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        except OSError:
            continue
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.info("Logging to %s", candidate)
        return
    logger.addHandler(logging.StreamHandler())
