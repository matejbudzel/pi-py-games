"""Pygame shell for Shadow Run. Rendering stays intentionally primitive/cached."""
from __future__ import annotations

from contextlib import nullcontext
from enum import Enum, auto
from pathlib import Path
import time

import pygame

from common.assets import SWEET16_FONT_PATH
from common.console_input import ConsoleInput
from common.display import DisplaySettings, GameDisplay, initialize_pygame
from common.input import Action, DeviceEvent, Release, actions_from_event
from common.joystick_input import JoystickInput

from .config import FPS, HEIGHT, OUTPUT_SIZE, WIDTH, Settings
from .core import Lane, Stamina, TerrainTimeline, difficulty_at, is_valid_stance, lane_contacts
from .songs import Song, discover_songs

MIXER_FREQUENCY, MIXER_BUFFER = 22050, 2048
LANE_X, TILE, TOP, PLAYER_Y = 166, 30, 18, 202
PREPLAY_SECONDS = 3.0
SAFE_TILE = (37, 105, 62)       # dark grass shadow
DANGER_TILE = (104, 178, 83)   # sunlit grass
VISIBLE_SONG_ROWS = 10


def visible_song_window(first_visible: int, selected: int, song_count: int) -> int:
    """Return the first list index while keeping the selected row on-screen."""
    if song_count <= VISIBLE_SONG_ROWS:
        return 0
    if selected < first_visible:
        return selected
    if selected >= first_visible + VISIBLE_SONG_ROWS:
        return selected - VISIBLE_SONG_ROWS + 1
    return first_visible


class Screen(Enum):
    LIST = auto()
    PLAYING = auto()
    RESULT = auto()


class App:
    def __init__(self, settings: Settings, seed: int | None = None, debug: bool = False) -> None:
        pygame.mixer.pre_init(MIXER_FREQUENCY, -16, 2, MIXER_BUFFER)
        self.settings, self.seed, self.debug = settings, seed, debug
        self.platform = DisplaySettings(settings.display_backend, settings.framebuffer_device)
        initialize_pygame(self.platform, audio=True)
        if self.platform.backend == "pygame":
            pygame.display.set_caption(settings.title)
        self.display = GameDisplay(self.platform, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT))
        self.screen_surface, self.clock = self.display.canvas, pygame.time.Clock()
        self.joystick = JoystickInput() if self.platform.backend == "pygame" else None
        self.console = ConsoleInput() if self.platform.backend == "fbdev" else None
        self.songs = discover_songs(settings.song_directory)
        self.selected, self.first_visible, self.screen, self.running = 0, 0, Screen.LIST, True
        self.held: set[str] = set()
        self.keyboard_until: dict[str, float] = {}
        self.song: Song | None = None
        self.timeline: TerrainTimeline | None = None
        self.stamina = Stamina()
        self.started_at = 0.0
        self.preplay_started_at = 0.0
        self.music_started = False
        self.last_time = 0.0
        self.active_stance = None
        self.score = 0
        self.clean_transitions = 0
        self.result_stars = 1

    def close(self) -> None:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self.display.close()
        pygame.quit()

    def run(self) -> None:
        try:
            with self.console or nullcontext():
                while self.running:
                    self._events()
                    self._update()
                    self._draw()
                    self.display.present()
                    self.clock.tick(FPS)
        finally:
            self.close()

    def _events(self) -> None:
        actions: list[Action | Release] = []
        keyboard_action_count = 0
        if self.console:
            actions = [event for event in self.console.poll_actions() if isinstance(event, (Action, Release))]
            keyboard_action_count = self.console.keyboard_action_count
        else:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if self.joystick:
                    device = self.joystick.handle_event(event)
                    if device is DeviceEvent.PAD_DISCONNECTED:
                        self.held.clear()
                actions.extend(actions_from_event(event))
        for index, action in enumerate(actions):
            if isinstance(action, Release):
                self.held.discard(self._direction(action.action))
                continue
            if action is Action.SELECT:
                if self.screen is Screen.PLAYING:
                    pygame.mixer.music.stop(); self.screen = Screen.LIST
                elif self.screen is Screen.RESULT:
                    self.screen = Screen.LIST
                else:
                    self.running = False
            elif self.screen is Screen.LIST:
                if action is Action.UP and self.songs:
                    self.selected = (self.selected - 1) % len(self.songs)
                    self.first_visible = visible_song_window(self.first_visible, self.selected, len(self.songs))
                elif action is Action.DOWN and self.songs:
                    self.selected = (self.selected + 1) % len(self.songs)
                    self.first_visible = visible_song_window(self.first_visible, self.selected, len(self.songs))
                elif action is Action.START and self.songs: self._start(self.songs[self.selected])
            elif self.screen is Screen.RESULT and action is Action.START:
                self.screen = Screen.LIST
            elif self.screen is Screen.PLAYING and action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
                direction = self._direction(action)
                if index < keyboard_action_count:
                    # A Linux TTY has no key-up events. Make each debug key
                    # press a visible short contact while pad buttons remain held.
                    self.keyboard_until[direction] = time.monotonic() + 0.9
                else:
                    self.held.add(direction)

    @staticmethod
    def _direction(action: Action) -> str:
        return {Action.LEFT: "left", Action.RIGHT: "right", Action.UP: "up", Action.DOWN: "down"}.get(action, "")

    def _start(self, song: Song) -> None:
        self.song, self.timeline = song, TerrainTimeline(song.beats, self.seed)
        self.stamina, self.score, self.clean_transitions = Stamina(), 0, 0
        self.preplay_started_at = time.monotonic()
        self.started_at = 0.0
        self.music_started = False
        self.last_time = 0.0; self.active_stance = self.timeline.initial_stance; self.held.clear(); self.keyboard_until.clear()
        self.timeline.prepare_song(song.duration)
        # Decode before the start line reaches the receptor, but remain silent.
        pygame.mixer.music.load(str(song.audio_path))
        self.screen = Screen.PLAYING

    def _song_time(self) -> float:
        if not self.music_started:
            return 0.0
        # get_pos follows mixer playback; monotonic protects startup/platform quirks.
        position = pygame.mixer.music.get_pos()
        fallback = time.monotonic() - self.started_at
        return max(0.0, (position / 1000 if position >= 0 else fallback) + self.settings.timing_offset_ms / 1000)

    def _update(self) -> None:
        if self.screen is not Screen.PLAYING or self.song is None or self.timeline is None:
            return
        if not self.music_started:
            if time.monotonic() - self.preplay_started_at < PREPLAY_SECONDS:
                return
            self.started_at = time.monotonic()
            self.music_started = True
            pygame.mixer.music.play()
            self.last_time = 0.0
        now = min(self.song.duration, self._song_time())
        delta = min(0.1, max(0.0, now - self.last_time)); self.last_time = now
        speed = difficulty_at(now, self.song.duration).speed
        expected = self.timeline.stance_at(now)
        if expected != self.active_stance:
            self.active_stance = expected
            self.clean_transitions += 1
            self.score += 50 + self.clean_transitions * 3
        contacts = lane_contacts(self._contact_actions())
        valid = is_valid_stance(contacts, expected)
        self.stamina.update(now, delta, valid, self.timeline.in_transition_window(now, self.song.duration))
        if valid:
            self.score += int(delta * 10)
        if self.stamina.value <= 0 or now >= self.song.duration or (not pygame.mixer.music.get_busy() and now > 0.5):
            pygame.mixer.music.stop(); self.result_stars = max(1, min(5, round(self.stamina.value / 25) + 1)); self.screen = Screen.RESULT

    def _contact_actions(self) -> set[str]:
        now = time.monotonic()
        self.keyboard_until = {direction: until for direction, until in self.keyboard_until.items() if until > now}
        return self.held | set(self.keyboard_until)

    def _draw(self) -> None:
        surface = self.screen_surface
        surface.fill((25, 30, 58))
        # decorative pixel stars, fixed so no per-frame asset decoding/allocation
        for x, y in ((20, 18), (92, 49), (330, 24), (400, 110), (45, 180)):
            pygame.draw.rect(surface, (72, 88, 145), (x, y, 2, 2))
        # Sweet16's tiny point sizes become illegible after RGB565 framebuffer
        # presentation.  Keep every player-facing glyph at its usable size.
        font = pygame.font.Font(SWEET16_FONT_PATH, 16)
        big = pygame.font.Font(SWEET16_FONT_PATH, 24)
        if self.screen is Screen.LIST:
            surface.blit(big.render(self.settings.title, False, (255, 225, 122)), (22, 22))
            if not self.songs:
                surface.blit(font.render("No prepared WAV songs", False, (220, 220, 230)), (22, 72))
            for row, song in enumerate(self.songs[self.first_visible:self.first_visible + VISIBLE_SONG_ROWS]):
                index = self.first_visible + row
                y = 52 + row * 18
                if index == self.selected: surface.blit(font.render(">", False, (255, 210, 80)), (20, y))
                surface.blit(font.render(song.title[:27], False, (240, 242, 255)), (34, y))
                surface.blit(font.render(f"{song.duration:.0f}s {song.tempo_bpm:.0f}", False, (140, 180, 210)), (286, y))
        elif self.screen is Screen.RESULT:
            surface.blit(big.render("*" * self.result_stars, False, (255, 221, 88)), (150, 94))
            pygame.draw.circle(surface, (94, 220, 155), (213, 138), 18)
            pygame.draw.circle(surface, (25, 30, 58), (207, 133), 2); pygame.draw.circle(surface, (25, 30, 58), (219, 133), 2)
        else:
            self._draw_game(font)
        if self.debug:
            surface.blit(font.render(f"held={','.join(sorted(self._contact_actions()))} stance={self.active_stance or ''}", False, (255, 255, 255)), (4, 220))

    def _draw_game(self, font: pygame.font.Font) -> None:
        assert self.song and self.timeline
        now = self._song_time()
        speed = difficulty_at(now, self.song.duration).speed
        # The row offset advances every frame. Each row asks the planned
        # timeline which stance it will require when it reaches the receptor.
        pygame.draw.rect(self.screen_surface, (45, 12, 38), (LANE_X - 4, TOP - 4, TILE * 3 + 8, 218))
        preplay_elapsed = min(PREPLAY_SECONDS, time.monotonic() - self.preplay_started_at)
        scroll_time = now if self.music_started else preplay_elapsed
        offset = int(scroll_time * speed) % TILE
        start_y = round(TOP + (PLAYER_Y - TOP) * (preplay_elapsed / PREPLAY_SECONDS))
        for row in range(-1, 8):
            y = TOP + offset + row * TILE
            if not self.music_started:
                # Safe terrain has already flowed below the descending start
                # line. Above it, reveal the terrain that will arrive after
                # music begins, giving the player time to take the first pose.
                safe = set(Lane) if y >= start_y else set(self.timeline.stance_at(max(0.0, (start_y - y) / speed)))
            elif y >= PLAYER_Y:
                # Terrain which has crossed the receptor stays harmless rather
                # than being recoloured when a new future segment is planned.
                safe = set(Lane)
            else:
                safe = set(self.timeline.stance_at(now + (PLAYER_Y - y) / speed))
            for lane in Lane:
                color = SAFE_TILE if lane in safe else DANGER_TILE
                pygame.draw.rect(self.screen_surface, color, (LANE_X + lane.value * TILE + 1, y + 1, TILE - 2, TILE - 2))
        contacts = lane_contacts(self._contact_actions())
        for lane in Lane:
            receptor = pygame.Rect(LANE_X + lane.value * TILE + 3, PLAYER_Y - 6, TILE - 6, 12)
            pygame.draw.rect(self.screen_surface, (255, 226, 100) if lane in contacts else (31, 43, 68), receptor)
            pygame.draw.rect(self.screen_surface, (240, 245, 255), receptor, 1)
        pygame.draw.rect(self.screen_surface, (220, 55, 83), (20, 80, 14, 110))
        pygame.draw.rect(self.screen_surface, (83, 220, 130), (20, 190 - int(self.stamina.value), 14, int(self.stamina.value)))
        progress = self._song_time() / self.song.duration
        pygame.draw.rect(self.screen_surface, (70, 80, 114), (48, 80, 80, 6)); pygame.draw.rect(self.screen_surface, (255, 210, 90), (48, 80, int(80 * progress), 6))
        self.screen_surface.blit(font.render(str(self.score), False, (255, 230, 135)), (330, 80))
        if self.timeline.in_transition_window(now, self.song.duration):
            pygame.draw.rect(self.screen_surface, (230, 240, 255), (LANE_X - 6, PLAYER_Y - 5, TILE * 3 + 12, 15), 1)
        if not self.music_started:
            # A striped line visibly flows from the top to the receptor during
            # the silent grace period and becomes the first terrain boundary.
            for lane in Lane:
                x = LANE_X + lane.value * TILE
                pygame.draw.line(self.screen_surface, (255, 235, 109), (x, start_y), (x + TILE, start_y), 2)
            remaining = max(1, int(PREPLAY_SECONDS - preplay_elapsed - 0.001) + 1)
            countdown = pygame.font.Font(SWEET16_FONT_PATH, 24).render(str(remaining), False, (255, 235, 109))
            self.screen_surface.blit(countdown, countdown.get_rect(center=(WIDTH // 2, 70)))
