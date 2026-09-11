"""pi-games-launcher provider interface for local Pygame games."""
from __future__ import annotations

import argparse
from configparser import ConfigParser
import json
from pathlib import Path
import subprocess
import sys

MANIFEST_VERSION = 1
GAMES = (
    ("pi-dance", "Tancuj, tancuj, vykrúcaj!", "games.dance.main", "PI_DANCE_CONFIG", "pi-dance.ini"),
    ("2048", "2048", "games.twenty48.main", "PI_2048_CONFIG", "pi-2048.ini"),
)


def _settings(path: Path, section: str, default: str) -> Path:
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    value = parser.get(section, "config", fallback=default).strip()
    game_config = Path(value).expanduser()
    return game_config if game_config.is_absolute() else path.parent / game_config


def manifest(config_path: Path | None = None) -> dict:
    """Return only launcher-contract fields; game details stay in its package."""
    return {
        "version": MANIFEST_VERSION,
        "games": [{
            "id": game_id,
            "title": title,
            "command": [sys.executable, "-m", "pi_py_games.provider", "--config", str(config_path) if config_path else "pi-py-games.ini", "run", game_id],
        } for game_id, title, _, _, _ in GAMES],
    }


def run(game_id: str, config_path: Path) -> int:
    game = next((game for game in GAMES if game[0] == game_id), None)
    if game is None:
        raise ValueError("unknown game: %s" % game_id)
    # The child is the game process: after launch, it owns its direct Pygame,
    # framebuffer, audio and physical input resources.
    _, _, module, environment_key, default_config = game
    return subprocess.call([sys.executable, "-m", module], env={**__import__("os").environ, environment_key: str(_settings(config_path, game_id, default_config))})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="pi-py-games launcher provider")
    parser.add_argument("--config", type=Path, default=Path("pi-py-games.ini"))
    parser.add_argument("action", choices=("manifest", "run"))
    parser.add_argument("game_id", nargs="?")
    args = parser.parse_args(argv)
    if args.action == "manifest":
        print(json.dumps(manifest(args.config.resolve()), ensure_ascii=False))
        return 0
    if not args.game_id:
        parser.error("run requires game_id")
    try:
        return run(args.game_id, args.config)
    except (OSError, ValueError) as exc:
        print("pi-py-games: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
