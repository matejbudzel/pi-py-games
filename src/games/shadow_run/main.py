from __future__ import annotations

import argparse
from pathlib import Path
import sys

from common.error_logging import configure_logging
from .app import App
from .config import load_settings


def command_arguments(argv: list[str] | None = None) -> list[str]:
    """Keep provider-runner arguments out of the game's own CLI parser."""
    if argv is not None:
        return argv
    if Path(sys.argv[0]).name == "runner.py":
        return []
    return sys.argv[1:]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Three-lane dance-mat runner")
    parser.add_argument("--seed", type=int, help="reproduce procedural terrain")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--config")
    args = parser.parse_args(command_arguments(argv))
    configure_logging()
    App(load_settings(Path(args.config) if args.config else None), args.seed, args.debug).run()


if __name__ == "__main__":
    main()
