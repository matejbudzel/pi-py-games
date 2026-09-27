# pi-py-games

Small, kid-friendly, dance-pad-first Python/Pygame games for a Raspberry Pi 1
B+. This repository provides games to the sibling
[`pi-games-launcher`](../pi-games-launcher). The launcher owns the appliance
console and menu; a selected game owns its display, audio, and physical input
until it exits.

Games live in `src/games/`. Shared, intentionally small platform code lives in
`src/common/`: action mapping, console and joystick input, display/fbdev
presentation, logging, and frame timing. See `AGENTS.md` for the binding
cross-game rules and a game package's own `AGENTS.md` for its product rules.

Included games are Pi Dance, Pixel Colors, Shadow Run, 2048, Winter Sports, and
the framebuffer grid test. Pi Dance-specific documentation is in
[`src/games/dance/README.md`](src/games/dance/README.md).

## Shared game contract

New pixel-art games use a 427×240 logical canvas, scaled with nearest-neighbour
pixels to an 854×480 output canvas. This is the default because it is much
lighter on the Pi 1. Use the shared display owner rather than Pygame display
calls directly:

```python
from common.display import GameDisplay, display_settings, initialize_pygame

settings = display_settings()
initialize_pygame(settings)
display = GameDisplay(settings, (854, 480), logical_size=(427, 240))
screen = display.canvas
```

At 1280×720 the 854×480 canvas is centered 1:1 with borders; games do not need
a second responsive layout. A game needing native-resolution UI may explicitly
use an 854×480 logical canvas instead.

Use the shared action model in `common.input`, not raw Pygame keys in game
state:

| Keyboard | Action |
|---|---|
| Arrow keys | LEFT / RIGHT / UP / DOWN |
| Enter or Space | START |
| Escape or F1 | SELECT |
| F8 | Developer performance overlay |

Keyboard and dance-pad input must drive the same actions. On the fbdev backend,
use `ConsoleInput`; on a desktop backend, use Pygame events with
`JoystickInput`.

Player-facing UI is Slovak by default. Code, comments, identifiers, tests,
commits, and documentation are English. Keep player UI text-light and put all
player-facing strings, external content paths, and game tuning in
`config/<game>.ini`. Store an editable template in
`src/games/<game>/config.example.ini`; the root `config/` directory is local
device state and is ignored by Git.

For destructive or leave actions, SELECT opens a localized confirmation modal.
Cancel is focused by default; START confirms and SELECT cancels.

## Performance on the Pi

The target is smooth 30 FPS on a Raspberry Pi 1 B+ with 256 MB RAM. Preload
assets; do not decode images/audio or access the filesystem during the frame
loop.

Use `common.performance.PerformanceTracker` and an F8 overlay in every new
game. The overlay should show FPS/frame time plus relevant render, scale, and
present timings. Write the summary report beside `PI_PY_GAMES_ERROR_LOG` on
normal exit.

Do not redraw a static screen every frame. Track logical dirty rectangles, draw
only what changed, and present those same rectangles:

```python
dirty_rectangles = draw_changed_areas()
if dirty_rectangles:
    display.present(dirty_rectangles)
```

`GameDisplay` scales dirty logical rectangles and the fbdev presenter copies
only their output areas. Use a full redraw only for state changes, scrolling,
or other changes that invalidate a cached scene.

## Creating a game

1. Create `src/games/<game>/` with `main.py`, small state/rendering modules,
   assets, and `config.example.ini`.
2. Add its console command to `[project.scripts]` in `pyproject.toml`.
3. Add focused hardware-free tests under `tests/game_cases/<game>/`.
4. Once the entry point works, register it through
   `src/pi_py_games/provider.py` for `pi-games-launcher`.
5. Create the local `config/<game>.ini` file with Slovak defaults and point the
   game at any external content there.

Keep state logic independent of the Pi and pad. Reuse `configure_logging`,
`GameDisplay`, `ConsoleInput`, `JoystickInput`, `Action`, and
`PerformanceTracker` instead of duplicating platform behavior.

## Installation and launcher provider

Python 3.11+ and Pygame are required:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

Copy `pi-py-games.ini.example` to the ignored `pi-py-games.ini` and configure
the display plus each game's local config path:

```ini
[display]
backend = pygame
framebuffer = /dev/fb0

[pixel-colors]
config = config/color_pages.ini
```

For the Pi 1's legacy direct framebuffer, use `backend = fbdev`. The game user
needs access to `/dev/fb0` (usually the `video` group) and `/dev/input/js*`
(usually the `input` group). The framebuffer game claims the active console
while it runs. `cat /tmp/pi-py-games-input.txt` reports mapped keyboard/pad
input and joystick discovery.

Configure `pi-games-launcher` with a provider command such as:

```ini
[provider pygame]
manifest_command = pi-py-games --config /path/to/pi-py-games.ini manifest
```

The provider runs a game as an external guest, so launcher lifecycle details
are not reimplemented by individual games.

## Tests and deployment

Run targeted tests while iterating, then the full suite before a broad change:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Completed coherent changes are committed and pushed to `main`. When `pi286` is
available, deploy without disturbing local device configuration or an active
game:

```bash
ssh pi286 'cd /home/dietpi/pi-py-games && git pull --ff-only'
```

Then run an appropriate non-interactive smoke check, for example a game’s
targeted test module. Do not make Pi availability a prerequisite for normal
desktop development, and do not restart a game without approval.

Logs from provider-launched games normally go to
`~/.local/state/pi-py-games/errors.log`; override that with the provider’s
`[diagnostics] error_log` setting.

## Content and font

Do not commit copyrighted audio, downloaded charts, or other unlicensed content.
Games load external media from configured local directories.

The included Sweet16mono font supports Slovak/Czech Latin Extended-A glyphs and
is licensed under the Boost Software License 1.0; its license notice is kept
with the shared font assets.
