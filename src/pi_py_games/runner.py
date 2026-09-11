"""Common crash boundary for games launched through the provider."""

from __future__ import annotations

import argparse
from importlib import import_module
import logging

from common.error_logging import configure_logging


def run(game_id: str, module_name: str) -> int:
    """Run one game and preserve an unexpected Python traceback for diagnosis."""
    configure_logging()
    logger = logging.getLogger("pi_py_games.runner")
    try:
        logger.info("Starting %s", game_id)
        game = import_module(module_name)
        game.main()
        logger.info("Stopped %s normally", game_id)
        return 0
    except KeyboardInterrupt:
        logger.info("Stopped %s by keyboard interrupt", game_id)
        return 0
    except Exception:
        logger.exception("%s stopped unexpectedly", game_id)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a pi-py-games game with common diagnostics")
    parser.add_argument("game_id")
    parser.add_argument("module_name")
    args = parser.parse_args(argv)
    return run(args.game_id, args.module_name)


if __name__ == "__main__":
    raise SystemExit(main())
