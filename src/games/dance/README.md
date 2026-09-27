# Pi Dance

Pi Dance is the repository’s small DDR-style game. Its product and UI rules are
in [`AGENTS.md`](AGENTS.md); shared platform rules are in the repository root.

The MVP flow is:

```text
BOOT -> SPLASH -> SONG SELECT -> PLAYING <-> PAUSED -> RESULT -> SONG SELECT
```

Songs are selected with Up/Down and started with START. Directional notes are
judged against the audio clock. Every completed song shows a celebratory star
result and returns to the song list only after START or SELECT.

## Local configuration and songs

Create the ignored local config file from the game template:

```bash
mkdir -p config
cp src/games/dance/config.example.ini config/dance.ini
```

Set the external song directory and Slovak player-facing text in that file.
Songs are external bundles containing safe runtime metadata, a PCM WAV, cover,
and chart. Do not commit downloaded songs or community charts.

Prepare selected bundles on a desktop, not the Pi:

```bash
.venv/bin/python src/games/dance/scripts/prepare_songs.py /path/to/pi-dance-songs --dry-run
.venv/bin/python src/games/dance/scripts/prepare_songs.py /path/to/pi-dance-songs
```

The runtime uses 22.05 kHz, 16-bit stereo PCM WAV and a 2048-sample mixer
buffer. Tune `timing_offset_ms` in the local config on the real device when
needed.

## Running and diagnostics

Run locally from the repository root:

```bash
.venv/bin/pi-dance
```

Press F8 for the developer performance overlay. It reports input, update,
render, and presentation cost; on exit it writes `/tmp/last-pi-dance-run.txt`.

Before a first Pi launch, test the display path without songs:

```bash
.venv/bin/python src/games/dance/scripts/pygame_display_smoke.py --fbdev /dev/fb0
```

The `pi-games-launcher` provider should launch Pi Dance as an external guest so
it can own its console, framebuffer, audio, and input for the duration of play.
