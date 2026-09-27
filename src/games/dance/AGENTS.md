# Pi Dance game rules

## Product goal

Build the smallest useful kid-friendly DDR-style game that can validate whether
the dance pad is fun enough to justify further work.

## UI contract

Normal player-facing text is limited to the game title on the splash screen and
song titles in the song-selection screen. Do not add explanatory labels such as
`START`, `SELECT`, `PAUSED`, `GREAT`, `MISS`, `SONG COMPLETE`, percentages, or
control instructions unless explicitly requested. Prefer icons, highlights,
progress bars, and symbols.

### Song selection

- Song titles are left-aligned at one fixed x coordinate.
- The selection chevron has its own fixed column to the left of titles.
- Up/Down moves the chevron vertically along that axis. Never shift it or song
  titles horizontally based on title length.

### Step feedback

Every judged note immediately shows one reaction image: heart for best/very
good, thumbs-up for acceptable, and shrug for miss/poor. Do not duplicate them
with text. Preload the assets and show the latest reaction briefly until it is
replaced or expires.

### Result screen

- Show a celebratory 1–5 star result for every completed song; there is no fail
  state.
- Do not auto-dismiss it. START and SELECT return to the song list.

## Display, timing, and song content

- Pi Dance uses an 854×480 application canvas; menus, HUD, text, and results
  render natively at that size. Gameplay art may use a lower-resolution surface
  with integer nearest-neighbour scaling.
- Audio playback is the authoritative song clock. Never derive note timing from
  frame count. Support configurable timing offsets for device calibration.
- Songs live in an external configurable directory as metadata, WAV, and chart
  bundles. Only safe synthetic/example metadata and charts may be committed.
- Support the smallest useful chart-format subset for selected Beginner/Easy
  songs; do not pursue exhaustive StepMania compatibility.

## Explicit MVP exclusions

Do not add persistent high scores, profiles, multiplayer, combo systems,
fail/life mechanics, online services, cover/video backgrounds, lyrics, MP3
decoding, a chart editor, auto-chart generation, or text-heavy judgement UI
unless explicitly requested.
