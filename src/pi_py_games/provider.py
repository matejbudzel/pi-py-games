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
    ("pi-dance", "Tancuj, tancuj, vykrúcaj!", "games.dance.main", "PI_DANCE_CONFIG", "config/dance.ini"),
    ("2048", "2048", "games.twenty48.main", "PI_2048_CONFIG", "pi-2048.ini"),
    ("shadow-run", "Shadow Run", "games.shadow_run.main", "PI_SHADOW_RUN_CONFIG", "config/shadow-run.ini"),
    ("fb-grid-test", "Test LED framebufferu", "games.fb_grid_test.main", "PI_FB_GRID_TEST_CONFIG", "fb-grid-test.ini"),
)


def _settings(path: Path, section: str, default: str) -> Path:
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    value = parser.get(section, "config", fallback=default).strip()
    game_config = Path(value).expanduser()
    return game_config if game_config.is_absolute() else path.parent / game_config


def _display_environment(path: Path) -> dict[str, str]:
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return {
        "PI_PY_GAMES_DISPLAY_BACKEND": parser.get("display", "backend", fallback="pygame").strip().lower() or "pygame",
        "PI_PY_GAMES_FRAMEBUFFER": parser.get("display", "framebuffer", fallback="/dev/fb0").strip() or "/dev/fb0",
    }


def _game_title(provider_config: Path, game_id: str, default_title: str, default_config: str) -> str:
    """Read the game's user-facing title without importing its Pygame package."""
    parser = ConfigParser(interpolation=None)
    parser.read(_settings(provider_config, game_id, default_config), encoding="utf-8")
    return parser.get("game", "title", fallback=default_title).strip() or default_title


def _logging_environment(path: Path) -> dict[str, str]:
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    value = parser.get("diagnostics", "error_log", fallback="~/.local/state/pi-py-games/errors.log").strip()
    return {"PI_PY_GAMES_ERROR_LOG": str(Path(value).expanduser())}


def manifest(config_path: Path | None = None) -> dict:
    """Return only launcher-contract fields; game details stay in its package."""
    return {
        "version": MANIFEST_VERSION,
        "games": [{
            "id": game_id,
            "title": _game_title(config_path, game_id, title, default_config) if config_path else title,
            "testing_tool": game_id == "fb-grid-test",
            "command": [sys.executable, "-m", "pi_py_games.provider", "--config", str(config_path) if config_path else "pi-py-games.ini", "run", game_id],
        } for game_id, title, _, _, default_config in GAMES],
    }


def run(game_id: str, config_path: Path) -> int:
    game = next((game for game in GAMES if game[0] == game_id), None)
    if game is None:
        raise ValueError("unknown game: %s" % game_id)
    # The child is the game process: after launch, it owns its direct Pygame,
    # framebuffer, audio and physical input resources.
    _, _, module, environment_key, default_config = game
    return subprocess.call([sys.executable, "-m", "pi_py_games.runner", game_id, module], env={
        **__import__("os").environ,
        **_display_environment(config_path),
        **_logging_environment(config_path),
        environment_key: str(_settings(config_path, game_id, default_config)),
    })


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
