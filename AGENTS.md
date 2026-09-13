# AGENTS.md

## Product goal

Build the smallest useful kid-friendly DDR-style game that can validate whether the dance pad is fun enough to justify further work.

Prefer a working, understandable MVP over completeness or abstraction.

## Repository workflow

This is a single-developer repository.

- Agents may commit coherent completed changes directly to `main` and push them without opening a pull request.
- Keep commits focused and understandable; do not mix unrelated cleanup into feature work.
- Before pushing, run the relevant tests/lint/smoke checks that are practical on the development host.
- Do not rewrite published history or force-push `main` unless explicitly requested.
- If a change is intentionally incomplete or known to break an existing entry point, do not push it merely to checkpoint work.

For optional target-device smoke testing, agents may try `ssh pi286`. The expected repository clone on that device is:

`/home/dietpi/pi-py-games`

If the device is reachable, a normal deployment check may pull the current `main` in that clone and run safe, non-destructive smoke tests. Do not make availability of the Pi a prerequisite for normal development, and do not change unrelated device configuration during a game deployment check.

Games intended for the external `pi-games-launcher` must be registered through `src/pi_py_games/provider.py` once their entry point is runnable. Do not expose a provider manifest entry that points to a missing/broken module.

## Platform contract

- Primary deployment target: Raspberry Pi 1 B+ with 256 MB RAM.
- Primary development surface: desktop macOS and Linux.
- Python + Pygame is the default implementation stack.
- Do not make the Raspberry Pi the normal development loop.
- Do not introduce Raspberry-Pi-specific architecture unless profiling on the real device demonstrates a need.
- Keep platform-specific display, joystick and latency configuration isolated from core game logic.

The sibling `pi-games-launcher` repository is the authoritative operational reference for the target Pi/DietPi hardware, display setup, and guest-process ownership. Reuse its hardware knowledge where appropriate, but do not take ownership of launcher hardware lifecycle.

## Input contract

Keyboard input is a first-class controller, not a fallback.

Every MVP action must work both from the keyboard and from the dance pad through a shared action model.

Canonical actions:

- LEFT
- RIGHT
- UP
- DOWN
- START
- SELECT

Default keyboard mapping:

- Arrow keys -> directions
- Enter or Space -> START
- Escape -> SELECT

Do not let game states depend directly on raw Pygame key or joystick events. Translate device input into game actions first.

## UI contract

The MVP is intentionally text-light.

Normal player-facing text should be limited to:

- the game title on the splash screen
- song titles in the song-selection screen

Do not add explanatory labels such as `START`, `SELECT`, `PAUSED`, `GREAT`, `MISS`, `SONG COMPLETE`, percentages or control instructions unless explicitly requested later.

Prefer icons, highlights, progress bars and simple symbols over written explanations.

### Song selection

- Song titles are left-aligned.
- All song titles begin on the same fixed x coordinate.
- The current selection is shown with a chevron in a separate fixed column to the left of the song titles.
- Up/Down moves the chevron vertically along a single x axis.
- Do not horizontally shift the chevron or song titles based on title length.

### Step judgement feedback

Each judged note must produce immediate non-textual feedback using one of three reaction images:

- heart -> best / very good hit
- thumbs-up -> acceptable hit
- shrug -> miss / poor hit

These icons are the normal in-game judgement feedback. Do not duplicate them with textual judgement labels.

Keep the implementation simple: preload the assets and briefly show the latest judgement before it disappears or is replaced by the next one.

### Result screen

- Show a simple final 1-5 star result.
- Celebrate song completion regardless of performance.
- Do not show a fail state.
- Do not auto-dismiss the result screen.
- The result remains visible indefinitely until the player explicitly presses START or SELECT.
- START and SELECT both return to the song list in the MVP.

## Display contract

- Application canvas: 854x480.
- Menus, HUD, text and results render natively at 854x480.
- Gameplay art may render to a lower-resolution logical surface and scale up using integer nearest-neighbour scaling.
- Do not force UI text through the low-resolution gameplay surface.
- 1280x720 output should center the 854x480 application canvas 1:1 with borders rather than introduce a second responsive layout.

## Performance approach

Target smooth 30 FPS on Raspberry Pi 1 B+.

Prefer simple portable code first. Do not pre-emptively add custom framebuffer code, C extensions, NumPy pixel pipelines, custom audio threads or similar complexity.

Avoid obviously expensive runtime work:

- no per-frame filesystem access
- no runtime image decoding during songs
- no unnecessary full-screen alpha effects
- preload small assets
- keep gameplay sprites simple

Profile on the actual Pi before optimizing further.

## Timing contract

Audio playback is the authoritative song clock. Never derive note timing from frame count.

Charts should be parsed into a format independent of StepMania source syntax, ideally absolute note timestamps plus direction/type.

Support configurable timing offsets for real-device calibration.

## Song content

Do not commit copyrighted audio or downloaded community charts.

Songs live in an external configurable directory as metadata + WAV + chart bundles.

The repository may contain synthetic/example metadata and charts only when they are safe to redistribute.

## Scope discipline

Do not implement these unless the current task explicitly requires them:

- persistent high scores
- accounts/profiles
- multiplayer
- combo systems
- fail/life mechanics
- online services
- cover art/video backgrounds
- lyrics
- MP3 decoding
- chart editor
- auto-chart generation
- exhaustive StepMania compatibility
- settings UI
- text-heavy tutorial or judgement UI

When integrating community charts, support the smallest useful subset of the format that handles the selected Beginner/Easy songs.

## Code style

- Keep modules small and responsibilities obvious.
- Prefer plain functions/dataclasses and simple state objects over framework-heavy patterns.
- Keep game logic testable without a physical dance pad or Raspberry Pi.
- Comments in source code should be in English.
