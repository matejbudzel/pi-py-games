# pi-py-games

A small monorepo of retro-like, dance-mat-first Python/Pygame games for the Raspberry Pi 1 B+ (256 MB). It is a provider for the sibling [`pi-games-launcher`](../pi-games-launcher): the launcher owns the appliance console, framebuffer and menu; a selected game owns Pygame, audio, and its physical input until it exits.

Games live in `src/games/`, with their code, assets, and game-specific configuration kept together. `src/common/` contains the small shared layer: canonical keyboard/dance-pad actions, joystick lifecycle, framebuffer/display support, console input, and lightweight performance timing. There is no workspace tool or generated monorepo setup.

Included games are **pi-dance**, the original small DDR-style rhythm game, **2048**, and **Shadow Run**, a beat-aware three-lane floor-is-danger runner. Future games add one package under `src/games/` and one registry entry; the launcher continues to use the same provider contract.

## Shadow Run

Shadow Run renders at 427×240 and `GameDisplay` scales that canvas exactly 2× to 854×480 with nearest-neighbour pixels. It uses the same shared keyboard/pad actions as the other games: arrows map to broad LEFT/CENTER/RIGHT mat lanes (Up and Down are CENTER), Enter/Space starts, and Escape returns/exits. For desktop mat simulation, hold `Q/A/Z` for left, `W/X` for centre, and `E/D/C` for right; arrows remain available. `--seed 1234 --debug` makes terrain reproducible and exposes the detected contacts.

It is deliberately a procedural runner rather than a fixed chart. A terrain state is a two-foot lane stance. Every normal generated change shares at least one occupied lane with its predecessor, so it never asks both feet to change lanes at once. Short transition windows forgive one or zero contacts; otherwise unsafe/missing contacts drain stamina. Valid play regenerates stamina after a short delay. The game ends at zero stamina or at natural audio completion, then keeps its star result visible until Start or Select.

Songs are external recursive `*.wav` files paired with `*.shadow.json`; songs missing a valid, current sidecar are hidden. Prepare on a desktop, never on the Pi:

```bash
python -m tools.prepare_shadow_songs /path/to/music
# or after installation:
prepare-shadow-songs /path/to/music
```

The stable sidecar suffix is `.shadow.json`. It stores schema version, source filename/size/mtime, duration, estimated BPM, and beat objects (`time`, normalized `strength`, `accent`). A current sidecar is skipped; use `--force` to regenerate. The optional desktop-only `librosa` package improves beat detection. Without it, the tool validates PCM WAV and writes a conservative 120-BPM fallback timeline. Runtime needs only Pygame and JSON.

Configure `[shadow-run] config=config/shadow-run.ini` in the provider config and set `[songs] directory` in that file. Launch locally with `pi-shadow-run --seed 1234`, or through `pi-py-games run shadow-run`.

The Pi-specific assumptions remain those shared by the repository: 22.05 kHz/16-bit stereo PCM WAV is preferred, the 2048-sample mixer buffer trades latency for Pi 1 stability, and `fbdev` uses the existing console and framebuffer paths. Physical pad layouts that expose only four D-pad events cannot distinguish diagonal corners; their left/right/up/down events are intentionally collapsed to the broad three lanes described above. This has not been verified on target hardware.

## Launcher provider

Install the project so the `pi-py-games` and `pi-dance` commands are on `PATH`, then copy `pi-py-games.ini.example` to ignored `pi-py-games.ini`:

```ini
[display]
# pygame on desktops; fbdev uses an off-screen SDL canvas and /dev/fb0 on Pi 1.
backend=pygame
framebuffer=/dev/fb0

[pi-dance]
config=/path/to/config/dance.ini

[2048]
# 2048 has no settings yet; this entry may be omitted.
config=/path/to/pi-2048.ini
```

Configure `pi-games-launcher` with a provider command such as:

```ini
[provider pygame]
manifest_command=pi-py-games --config /path/to/pi-py-games.ini manifest
```

The provider emits manifest schema version 1 and supports `pi-py-games run pi-dance`. The launcher runs that command as an external guest, so no input, display, audio, framebuffer, or game exit conventions are proxied through the launcher.

## pi-dance

The first goal is not to build a complete StepMania clone. The MVP exists to answer a simpler question: **will the kids actually want to use the dance pad?**

## MVP

The application flow is intentionally small:

```text
BOOT -> SPLASH -> SONG SELECT -> PLAYING <-> PAUSED -> RESULT -> SONG SELECT
```

- Select a song with Up/Down.
- Start with the dance-pad Start button or Enter/Space on a keyboard.
- Follow scrolling directional notes.
- Correct steps score points.
- Start pauses/resumes during a song.
- Select / Escape returns to the song list.
- Every completed song ends with a small celebratory result screen, regardless of score.
- Results are expressed as a simple star rating. No persistent high scores in the MVP.
- The result screen never auto-dismisses. It remains visible until the player explicitly presses Start or Select, after which the game returns to the song list.

## UI philosophy

The player-facing MVP UI should use as little text as possible.

The only required text is:

- the game title on the splash screen
- song titles in the song list

Do not add labels such as `START`, `SELECT`, `PAUSED`, `GREAT`, `MISS`, `SONG COMPLETE`, percentages, instructions or other explanatory text unless later user testing demonstrates a need.

Navigation, progress and feedback should be communicated with layout, icons, highlights and simple symbols instead of words.

### Song list

The song list is left-aligned. Each song title begins on the same vertical text axis.

The currently selected song is indicated by a chevron placed in a fixed column to the left of the titles. Moving Up/Down moves only the chevron vertically; it should not shift horizontally because of varying song-title lengths.

Conceptually:

```text
  > Love Story
    Let It Go
    Shake It Off
    Into the Unknown
```

The exact spacing and styling can evolve, but the fixed left alignment and single chevron axis are part of the MVP interaction design.

### In-game step feedback

Each judged step produces immediate visual feedback using one of three small reaction images:

- heart: best / very good hit
- thumbs-up: acceptable hit
- shrug: missed or poor hit

These are the primary in-game judgement indicators. Do not duplicate them with textual labels in the normal player UI.

The most recent reaction may remain visible briefly after judgement before disappearing or being replaced by the next one. The exact timing can be tuned during playtesting.

### Result screen

The result screen shows the final star rating and a small celebratory visual/fanfare regardless of performance. It should not display a failure state.

The result screen is modal: it remains on screen indefinitely until Start or Select is pressed. There is no timeout and no automatic return to the song list.

## Display model

The application canvas is **854x480**.

HUD, menus, text and result screens render natively at 854x480 so they can use the full output resolution and remain readable.

Gameplay graphics use a lower-resolution pixel-art coordinate system and are scaled by an integer factor with nearest-neighbour scaling. The exact gameplay viewport size is intentionally not fixed yet; it should follow from the HUD layout rather than constrain it.

For displays that reject 854x480 and run at 1280x720, the 854x480 application canvas should be shown 1:1 and centered with black borders. The application does not require a responsive 720p layout.

## Target hardware and development environment

The deployment/performance target is:

- Raspberry Pi 1 B+
- 256 MB RAM
- DietPi / Raspberry Pi OS-class Linux environment
- USB dance pad
- HDMI display
- 30 FPS minimum target

The Raspberry Pi is **not** the primary development surface. The game must run normally on desktop macOS and Linux so almost all development, testing and iteration can happen there.

Keyboard input is a **first-class controller**, not a debug fallback. Everything required to play and navigate the MVP must be possible from the keyboard.

The sibling `pi-games-launcher` repository is the authoritative reference for the target Raspberry Pi 1 B+ / DietPi device, display environment, deployment conventions and known hardware constraints. This project should reuse that operational knowledge where applicable, but should not take ownership of appliance lifecycle.

## Audio and songs

Runtime audio is 22.05 kHz, 16-bit PCM stereo WAV. This is deliberately a
low-bandwidth format for the Pi while avoiding MP3 decoding during gameplay.
The mixer uses the same format with a 2048-sample buffer to reduce Pi 1 audio
underruns; use the configurable timing offset if the extra buffer needs small
input calibration.

No copyrighted music or community chart files belong in this repository. The game loads song bundles from a configurable external directory.

A downloaded bundle may retain its original files, but the preparation script
creates these runtime files alongside them:

```text
love-story/
  song.wav
  song.bmp
  song.json
  Love Story.sm
```

Example metadata:

```json
{
  "title": "Love Story",
  "artist": "Taylor Swift",
  "audio": "song.wav",
  "chart": "chart.sm",
  "duration_seconds": 120
}
```

`song.json` is the authoritative application metadata. It includes the displayed
title, artist, duration, generated WAV filename, source `.sm` filename,
256×256 cover filename, and the download URL retained
from the original `.txt` file. The cover is picked from a downloaded jacket
image when possible; otherwise a bundled generic cover is used.

Running the tool again is safe: it fills each missing WAV, cover, and metadata
field independently, while retaining existing metadata values so locally edited
titles remain intact. Existing WAVs in another codec, sample rate, or channel
layout are automatically regenerated to the runtime format. Use `--overwrite`
only to regenerate every derived file regardless of its current format.

Prepare downloaded bundles on a desktop machine with ffmpeg installed:

```bash
python3 src/games/dance/scripts/prepare_songs.py ~/pi-dance-songs --dry-run
python3 src/games/dance/scripts/prepare_songs.py ~/pi-dance-songs
```

To download and prepare songs directly from Zenius-I-vanisher, keep a text file
outside this repository, for example `~/pi-dance-simfile-ids.txt`, with one ID
per line. Blank lines, `#` comments, and repeated IDs are allowed:

```text
# Favourite songs
49836
```

Run the importer on your desktop with `ffmpeg`, `ffprobe`, and ImageMagick's
`magick` installed (the same conversion tools used above):

```bash
python3 src/games/dance/scripts/import_ziv_songs.py ~/pi-dance-simfile-ids.txt ~/pi-dance-songs
```

Point `[songs] directory` in your game configuration to `~/pi-dance-songs`.
Each imported song gets a stable `ziv-<id>/` folder containing the original
files and generated `song.wav`, `song.bmp`, and `song.json`. Metadata includes
the page's song title and artist, source URL, `ziv_simfile_id`, and
`ziv_last_updated_by` (the site's updater credit, which is not necessarily the
chart's original author).

Rerun the same command after adding IDs or after an interrupted import. It
caches page metadata and ZIPs under `<destination>/.ziv-cache/`, restores missing
source files from those ZIPs, and reuses the preparation tool to create missing
runtime files or replace WAVs in the wrong format. Existing metadata edits are
preserved. Interrupted downloads and conversions are retried on the next run.
Cached songs require no network requests; removing an ID from the list does not
delete its song. Existing folders with other names are left alone, so previously
imported manual bundles are not automatically deduplicated.

The importer supports ZIPs containing one `.sm` file and uses the existing
converter's easiest `dance-single` selection. SSC-only bundles and bundles with
multiple `.sm` files are reported as unsupported. A failed song does not stop
the remaining IDs; the command exits with status 1 if any import failed.
Both the ID file and destination must be outside this repository. Keep the
cache to allow offline repairs; delete a song's cache directory to fetch its
page and ZIP again. Existing source files and metadata still remain intact.

Preparation checks for a usable `dance-single` chart without storing difficulty
or meter in metadata. Legacy metadata containing those fields remains compatible;
the game ignores them.

To inspect a library, print an alphabetical inventory of its songs, folders, and
all files in each bundle:

```bash
python3 src/games/dance/scripts/list_songs.py ~/pi-dance-songs
```

Omit the directory to inspect `songs/` in the current working directory. Bundles
without valid metadata are included and marked so incomplete imports are visible.
The game reads all difficulties from the `.sm` file. Songs with multiple charts
open a stacked-bar selector in the gameplay screen, ordered from Beginner through
Challenge/Edit (then by meter within each difficulty), with the easiest focused.
More bars mean a later option in this song's difficulty order, not an absolute meter.
Left/Right moves focus, START confirms and begins the countdown, and SELECT opens
the same song-exit confirmation used during play. Cancelling preserves focus.
Songs with one chart go straight to the countdown.

To copy prepared songs to the Pi, use the runtime-only rsync script. Provide
the source song directory first and an rsync destination second. Either end
can be remote over SSH; at least one end must be local:

```bash
python3 src/games/dance/scripts/sync_songs.py ~/pi-dance-songs matej@raspberrypi:/home/matej/pi-dance-songs/ --dry-run
python3 src/games/dance/scripts/sync_songs.py ~/pi-dance-songs matej@raspberrypi:/home/matej/pi-dance-songs/
```

You can also run it on the receiving machine to pull songs from your desktop:

```bash
python3 src/games/dance/scripts/sync_songs.py matej@devbox:/home/matej/pi-dance-songs ~/pi-dance-songs/ --dry-run
python3 src/games/dance/scripts/sync_songs.py matej@devbox:/home/matej/pi-dance-songs ~/pi-dance-songs/
```

For a remote source, the script runs its metadata scanner over SSH before
starting rsync. That source machine needs Python 3.11+ but does not need the
game or this script installed. Dry runs scan metadata without copying songs.

A local destination directory or an SSH host alias also works. Install rsync 3
or newer on both machines; on macOS, use `brew install rsync` and ensure that
version is on your `PATH`. SSH authentication uses your normal SSH configuration.

The script reads each bundle's `song.json` and copies that metadata plus the
referenced WAV, `.sm` chart, and cover (normally `song.wav` and `song.bmp`).
Custom filenames and nested paths in metadata are respected. Missing covers use
the fallback asset installed with the game. Original compressed audio, extra
images/charts, source-link text files, `list.txt`, and `.ziv-cache` are omitted.
Incomplete or invalid bundles with metadata stop the transfer before rsync runs;
directories without metadata are skipped.

Reruns transfer new or changed files using rsync's usual size/modification-time
checks. Destination files are not deleted, and the source is retained. This
copies only the song library: install the game separately on the Pi and point
its `[songs] directory` at the destination. The destination's parent directory
must already exist.

## Chart philosophy

The MVP should support only the useful subset of StepMania charts rather than attempting complete StepMania compatibility.

The chart loader should translate source files into a small internal representation based on absolute note timestamps. Gameplay, rendering and scoring should not depend directly on the StepMania format.

Initial scope:

- four-panel single-player dance
- tap, hold and lift notes
- BPM and song offset
- Beginner/Easy community charts

More advanced features such as mines, rolls, complex gimmicks and full `.sm`/`.ssc` compatibility are non-goals until real songs require them.
All difficulties support taps, holds and lifts. Holds have rainbow-dot tails matching
their duration; press the arrow and keep the panel down until the tail ends.
The head gives immediate feedback. Missing it leaves the tail flowing so a late
press can still earn credit. Releasing and pressing again accumulates the time
actually held. Lifts reverse the visual: rainbow dots arrive first and the arrow
marks when to release the panel. Since SM's `L` stores only a release timestamp,
the game supplies a one-beat lead-in, shortened to avoid the previous note on
the same panel. Lead-ins follow BPM changes.

Holds and lifts each score once: 70% comes from the important edge (press for
holds, release for lifts), and 30% from the proportion of the interval held.
Edge timing within 130 ms earns full edge credit; within 280 ms earns half.
An accurately hit edge also forgives up to 130 ms of uncovered interval.
Early starts, late ends and interrupted presses count only their intersection
with the interval. Holding through a lift without releasing earns overlap credit
only. No overlap and no correctly timed hold press earns no credit.
Mines, rolls and other non-tap symbols remain ignored.
Desktop keyboards and dance-pad buttons report releases. The legacy framebuffer
TTY keyboard cannot report releases: it cannot judge lift edges and treats a
pressed panel as held for interval credit. Use the pad or desktop keyboard for
the full hold/lift interaction.

## Timing and scoring

Audio playback is the timing authority. Note timing must not depend on rendered frame count.

The MVP needs only a small scoring model such as hits, misses and total notes, converted to a friendly 1-5 star result. There is no fail state: finishing the song is always celebrated.

The internal hit-quality model should be small and map directly to the three visual reaction assets, for example `great`, `ok` and `miss` -> heart, thumbs-up and shrug.

Global audio/input timing offsets should be configurable so HDMI/display/input latency can be tuned on the real Raspberry Pi setup.

## Non-goals for the first MVP

- persistent high scores
- user profiles
- multiplayer
- combo multipliers
- life/fail mechanics
- online services
- cover art or background video
- lyrics
- MP3 playback
- chart editor
- automatic chart generation
- exhaustive StepMania compatibility
- touchscreen/mouse-first UI
- settings UI
- text-heavy instructions or judgement labels

## Installation and first run

Python 3.11+ is required. On Debian, Raspberry Pi OS, or DietPi, install the
small set of system tools first. `ffmpeg` converts the song audio and
ImageMagick provides the `magick` cover-image converter.

```bash
sudo apt update
sudo apt install python3-venv python3-pip ffmpeg imagemagick libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0
```

Clone the repository, create its virtual environment, and install the game:

```bash
git clone https://github.com/matejbudzel/pi-py-games.git
cd pi-py-games
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

Create the device-local configuration once; it is deliberately ignored by Git:

```bash
mkdir config
cp src/games/dance/config.example.ini config/dance.ini
```

Edit `config/dance.ini` to localize or brand the title and point the game at the
external song directory. For example, use the absolute path where you copied
the downloaded song folders:

```ini
[game]
title = Dance, dance, spin around!

[songs]
directory = /home/matej/pi-dance-songs

[exit]
item_title = Exit
confirmation_text = Exit the game?
confirm_button = Yes
cancel_button = No

[gameplay]
pause_text = Paused
exit_confirmation_text = Stop dancing?
exit_confirm_button = Yes
exit_cancel_button = No
timing_offset_ms = 0
```

Prepare the downloaded song bundles. The dry run first shows what will be
created; the second command writes the WAV files, 256×256 covers, and metadata.

```bash
.venv/bin/python src/games/dance/scripts/prepare_songs.py /path/to/pi-dance-songs --dry-run
.venv/bin/python src/games/dance/scripts/prepare_songs.py /path/to/pi-dance-songs
```

Start the game from the project directory so it reads that local configuration:

```bash
.venv/bin/pi-dance
```

When started through `pi-games-launcher`, use the `pi-py-games` provider rather
than a game-specific launcher flag. The generic launcher releases its terminal,
framebuffer and input handles before starting `pi-dance`; the game then owns
them directly until it exits.

Press F8 at any time to show or hide the developer performance overlay.
It displays the most recent frame's input (`i`), update (`u`), render (`r`),
and presentation (`p`) time in milliseconds. When the application exits, its
average, maximum, and final frame timing are written to
`/tmp/last-pi-dance-run.txt`.

### Raspberry Pi display smoke test

Before the first Pi launch, verify that the installed SDL2/Pygame display driver
can draw to the connected screen without loading the game or songs:

```bash
.venv/bin/python src/games/dance/scripts/pygame_display_smoke.py
```

It displays a four-colour grid and prints the selected SDL video driver. Press
any keyboard or joystick button to exit. If no pattern appears, stop with
Ctrl+C and keep the printed driver name: it identifies the display-backend
problem independently of the game.

The Pi 1 legacy setup managed by `pi-games-launcher` exposes `/dev/fb0` instead of an
SDL2 display driver. Test its direct presenter with:

```bash
.venv/bin/python src/games/dance/scripts/pygame_display_smoke.py --fbdev /dev/fb0
```

If the grid appears, set the shared provider display backend in the
device-local `pi-py-games.ini` before launching either game:

```ini
[display]
backend = fbdev
framebuffer = /dev/fb0
```

The user running the game must be allowed to write `/dev/fb0`, normally by
being in the `video` group. Log out and back in after `sudo usermod -aG video
"$USER"`.

With this backend the game also claims the active Linux console while it runs:
the terminal cursor disappears, keyboard input is read directly, and the known
dance pad is read from `/dev/input/js*`. The user needs access to `input` as
well as `video`; log out and back in after `sudo usermod -aG input "$USER"`.
If the pad does not respond, quit the game after pressing a few pad buttons and
inspect `cat /tmp/pi-py-games-input.txt`. It reports every joystick considered,
permission/recognition failures, and received mapped button presses.

## Disconnects and error recovery

Unplugging a dance pad automatically pauses a song or its countdown. The legacy
framebuffer reader closes the disconnected device and retries discovery every
two seconds; the desktop backend uses Pygame hotplug events. Reconnecting never
resumes automatically: press START to continue. Keyboard play still works without
a pad. Disconnecting also clears held panels so they cannot remain stuck.

HDMI monitoring uses Linux DRM connector status when available, or [`tvservice -s`](https://github.com/raspberrypi/userland/blob/master/host_applications/linux/apps/tvservice/tvservice.c)
on the Pi's legacy framebuffer setup. Checks run in a background worker, two
seconds apart, with bounded command timeouts. A detected loss pauses the song;
START can resume after a detected reconnection. The framebuffer is reopened on
reconnection and presentation is suspended while the display is known to be off.
Menus and results remain in their current state.

A TV can keep HDMI connected in standby. The reference Pi setup also uses
`hdmi_force_hotplug=1`, so HDMI status alone is not reliable TV power detection.
For a TV with HDMI-CEC enabled, install `cec-utils` and enable the optional check:

```ini
[display]
cec = true
```

This uses `cec-client -s -d 1` with [`pow 0`](https://github.com/Pulse-Eight/libcec/blob/master/src/cec-client/cec-client.cpp) to query the TV's power status; it does
not send power or source-selection commands. An explicit standby response pauses
play even if HDMI remains connected. Timeouts and unknown responses are not
treated as disconnects. CEC support, permissions, and standby reporting need to
be verified on the actual TV/Pi. Detection can take several seconds. Desktop
systems without a supported status source simply keep working without HDMI
monitoring; an initially unused desktop HDMI socket does not pause keyboard play.

Unexpected Python exceptions in input, update, rendering, or presentation are
logged with a traceback, and the game attempts to stop playback and rebuild the
song list. If recovery fails, it closes resources and restarts the application at
the list, reopening display, audio, and input. Startup failures are retried too,
with delays increasing from one to 30 seconds to avoid a tight restart loop.
Normal exit and Ctrl+C stop the application. Corrupt or disappearing external
covers use the fallback image instead of preventing the list from opening.

Logs include connection events and failed song loads. Every game launched through
the provider shares `~/.local/state/pi-py-games/errors.log`, with two rotated
backups and a 1 MB limit per file. Override it centrally with
`[diagnostics] error_log = /path/to/errors.log` in `pi-py-games.ini`. If that path
cannot be opened, logging falls back to `/tmp/pi-py-games-errors.log`, then stderr.
Files in `/tmp` may disappear on reboot.

This boundary recovers Python exceptions, not native SDL/driver crashes, an OS
out-of-memory kill, power loss, or a hung native call. Those require an external
process supervisor, which is not installed by the game.

### Hardware validation

On the Pi, try unplugging/replugging the pad during a song, countdown, and exit
confirmation, then turn the TV off/on and unplug/replug HDMI. Check that play
stays paused until START, the pad works after reconnection, and the display draws
again. Inspect the error log for connection events and tracebacks. Run the same
song with keyboard input and no pad to check that keyboard-only play still works.

## Font

The included `Sweet16mono` is a pixel-perfect 8×16 bitmap-style font by Martin
Sedlák. It includes Latin Extended-A characters used by Slovak and Czech, and
is licensed under the Boost Software License 1.0; its license notice is retained
in `src/pi_dance/assets/fonts/SWEET16-LICENSE.txt`.
