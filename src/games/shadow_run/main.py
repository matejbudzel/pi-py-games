from __future__ import annotations

import argparse

from common.error_logging import configure_logging
from .app import App
from .config import load_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Three-lane dance-mat runner")
    parser.add_argument("--seed", type=int, help="reproduce procedural terrain")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    configure_logging()
    from pathlib import Path
    App(load_settings(Path(args.config) if args.config else None), args.seed, args.debug).run()


if __name__ == "__main__":
    main()
