# AGENTS.md

## Product goal

Build small, kid-friendly, dance-pad-first Pygame games that are pleasant to
play on the Raspberry Pi 1 B+. Prefer a working, understandable MVP over
completeness or abstraction. Game-specific product rules belong in that game's
package, for example `src/games/dance/AGENTS.md`.

## Repository workflow

This is a single-developer repository.

- Keep commits focused and understandable; do not mix unrelated cleanup into a
  feature change.
- For a coherent completed change, run practical relevant tests, commit it to
  `main`, and push it. Do not rewrite published history or force-push `main`
  unless explicitly requested.
- Deploy completed game changes to `pi286` by fast-forwarding
  `/home/dietpi/pi-py-games` with `git pull --ff-only`, then run a safe,
  targeted smoke check when practical. Preserve device-local changes and never
  restart or launch an active game without the user's approval.
- The Pi is an optional target check, not the normal development loop. Do not
  make progress depend on it or change unrelated device configuration.
- Register a runnable game intended for `pi-games-launcher` in
  `src/pi_py_games/provider.py`; never register a missing or broken entry
  point.

## Platform and shared code

- Primary target: Raspberry Pi 1 B+ with 256 MB RAM. Develop normally on
  desktop macOS or Linux.
- Use Python and Pygame. Reuse `src/common/` rather than creating per-game
  variants of input, framebuffer, logging, or performance code.
- Use `display_settings`, `initialize_pygame`, and `GameDisplay` for display
  ownership. fbdev games use `ConsoleInput`; desktop games use Pygame events
  and `JoystickInput`.
- Keep platform-specific display, joystick, audio-latency, and framebuffer
  details out of core game logic.
- The sibling `pi-games-launcher` repository is the authoritative operational
  reference for the Pi/DietPi hardware and guest-process lifecycle.

## Display and performance

- New pixel-art games default to a 427×240 logical canvas presented as an
  854×480 output canvas through `GameDisplay(..., logical_size=(427, 240))`.
  Use integer nearest-neighbour scaling. A native 854×480 canvas is an explicit
  exception for a game that genuinely needs it.
- At 1280×720, center the 854×480 output 1:1 with borders; do not add a second
  responsive layout.
- Target 30 FPS on the Pi. Preload assets; avoid runtime decoding, per-frame
  filesystem access, unnecessary full-screen alpha work, and expensive pixel
  pipelines.
- Static screens must not redraw or present every frame. Track logical dirty
  rectangles and call `display.present(rectangles)` so scaling and fbdev copies
  affect only changed areas. Use one full redraw for transitions, scrolling, or
  other changes that invalidate a cached scene.
- Every new game exposes the F8 developer performance overlay using
  `common.performance.PerformanceTracker`. It shows FPS/frame cost and the
  relevant render/scale/present timings, and writes a report on normal exit
  beside `PI_PY_GAMES_ERROR_LOG`.

## Input and interaction

Keyboard input is a first-class controller. Translate raw device events to
`common.input.Action` before game-state handling; never make game state depend
on raw Pygame keys or joystick events.

- Arrow keys map to LEFT/RIGHT/UP/DOWN.
- Enter and Space map to START.
- Escape and F1 map to SELECT.
- Dance-pad input and keyboard input use the same action model.
- SELECT opens a localized confirmation before a destructive or leave action.
  Its default focus is cancel; START confirms and SELECT cancels.

## UI, language, and configuration

- Keep normal player UI text-light. Prefer icons, highlighting, colors, and
  simple symbols over instructions or technical labels.
- Slovak is the default language for player-facing UI. Source code, comments,
  identifiers, tests, commits, and documentation are English.
- Player-facing strings, external-content paths, and game tuning live in a
  game-specific INI file at `config/<game>.ini`. Keep an English-named template
  next to the game as `src/games/<game>/config.example.ini`; local `config/`
  files are device/user state and must stay out of Git.
- The result/end state remains until a player action unless the game-specific
  contract explicitly says otherwise.

## Testing, content, and scope

- Keep modules small and game logic testable without a Pi or dance pad. Add
  focused tests for new state transitions and performance-sensitive rendering.
- Do not commit copyrighted audio, downloaded charts, or other unlicensed game
  content. External content paths belong in local configuration.
- Do not add accounts, online services, persistent scores, multiplayer, a
  settings UI, or text-heavy tutorials unless a task explicitly requires them.
