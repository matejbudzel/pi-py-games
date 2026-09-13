from __future__ import annotations
import argparse
from pathlib import Path
from .app import App
from .config import load_settings
def main(argv: list[str] | None = None) -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--seed",type=int); parser.add_argument("--config"); args=parser.parse_args(argv)
    App(load_settings(Path(args.config) if args.config else None),args.seed).run_loop()
if __name__ == "__main__": main()
