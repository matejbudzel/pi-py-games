"""Pygame shell for Shadow Run. Rendering stays intentionally primitive/cached."""
from __future__ import annotations

from contextlib import nullcontext
from enum import Enum, auto
import logging
import os
from pathlib import Path
import time

import pygame

from common.assets import SWEET16_FONT_PATH
from common.console_input import ConsoleInput
from common.display import DisplaySettings, GameDisplay, initialize_pygame
from common.input import Action, DeviceEvent, PAD_ACTIONS, Release, actions_from_event
from common.joystick_input import JoystickInput
from common.performance import FrameTiming, PerformanceTracker

from .config import FPS, HEIGHT, OUTPUT_SIZE, WIDTH, Settings
from .core import Lane, Stamina, TerrainTimeline, difficulty_at, is_valid_stance, lane_contacts, scroll_distance
from .songs import Song, discover_songs

MIXER_FREQUENCY, MIXER_BUFFER = 22050, 2048
LANE_X, TILE, PLAYER_Y = 166, 30, 202
PREPLAY_SECONDS = 3.0
SAFE_TILE = (37, 105, 62)       # dark grass shadow
DANGER_TILE = (104, 178, 83)   # sunlit grass
VISIBLE_SONG_ROWS = 10
PREVIEW_SIZE = 128
PREVIEW_RECT = pygame.Rect(282, 76, PREVIEW_SIZE, PREVIEW_SIZE)
TITLE_RECT = pygame.Rect(34, 0, PREVIEW_RECT.left - 46, 16)
MENU_BACKGROUND_PATH = Path(__file__).parent / "assets" / "menu-lawn.png"
RESULT_FAILED_PATH = Path(__file__).parent / "assets" / "result-failed.png"
RESULT_SUCCESS_PATH = Path(__file__).parent / "assets" / "result-success.png"
GAMEPLAY_BACKGROUND_PATH = Path(__file__).parent / "assets" / "gameplay-lawn.png"
PERFORMANCE_REPORT_PATH = Path(os.environ.get("PI_PY_GAMES_ERROR_LOG", "~/.local/state/pi-py-games/errors.log")).expanduser().parent / "shadow-run-performance.txt"
# Rows can partially enter above the display and leave below the receptor. Keep the
# complete vertical lane strip dirty so no old tile edge survives a scroll.
GRID_RECT = pygame.Rect(LANE_X - 10, 0, TILE * 3 + 20, HEIGHT)
STAMINA_RECT = pygame.Rect(57, 75, 14, 110)
LEFT_HUD_RECT = pygame.Rect(43, 65, 42, 130)
PROGRESS_RECT = pygame.Rect(307, 68, 82, 6)
RIGHT_HUD_RECT = pygame.Rect(295, 45, 106, 48)
DEBUG_RECT = pygame.Rect(0, 216, WIDTH, 24)


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
    PAUSED = auto()
    LEAVE_CONFIRMATION = auto()
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
        self.font = pygame.font.Font(SWEET16_FONT_PATH, 16)
        self.big_font = pygame.font.Font(SWEET16_FONT_PATH, 24)
        self.modal_font = pygame.font.Font(SWEET16_FONT_PATH, 16)
        self.modal_font.set_bold(True)
        self.joystick = JoystickInput() if self.platform.backend == "pygame" else None
        self.console = ConsoleInput() if self.platform.backend == "fbdev" else None
        self.songs = discover_songs(settings.song_directory)
        self.menu_background = self._load_menu_background()
        self.gameplay_background = self._load_scene(GAMEPLAY_BACKGROUND_PATH, (24, 58, 42))
        self.result_failed_background = self._load_scene(RESULT_FAILED_PATH, (38, 80, 55))
        self.result_success_background = self._load_scene(RESULT_SUCCESS_PATH, (38, 80, 55))
        self.song_covers = {song.audio_path: self._load_cover_preview(song) for song in self.songs}
        self.song_labels = {song.audio_path: self._ellipsize_title(song.title) for song in self.songs}
        self.selected, self.first_visible, self.screen, self.running = 0, 0, Screen.LIST, True
        self.held: set[str] = set()
        self.pad_buttons: set[int] = set()
        self.keyboard_until: dict[str, float] = {}
        self.song: Song | None = None
        self.timeline: TerrainTimeline | None = None
        self.stamina = Stamina()
        self.started_at = 0.0
        self.preplay_started_at = 0.0
        self.music_started = False
        self.pause_started_at = 0.0
        self.leave_return_screen = Screen.PLAYING
        self.leave_confirm_selected = False
        self.last_time = 0.0
        self.active_stance = None
        self.score = 0
        self.clean_transitions = 0
        self.result_success = False
        self.performance = PerformanceTracker()
        self.max_audio_step_ms = 0.0
        self.audio_jump_count = 0
        self.max_boundary_lateness_ms = 0.0
        self.report_written = False
        self.presentation_frames = 0
        self.total_scale_ms = 0.0
        self.max_scale_ms = 0.0
        self.total_backend_present_ms = 0.0
        self.max_backend_present_ms = 0.0
        self.gameplay_base: pygame.Surface | None = None
        self.gameplay_needs_full_present = False
        self.terrain_rows: tuple[tuple[Lane, Lane], ...] = ()

    def close(self) -> None:
        if getattr(self, "song", None) is not None and not self.report_written:
            self._write_performance_report("interrupted")
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
        self.display.close()
        pygame.quit()

    def run(self) -> None:
        try:
            with self.console or nullcontext():
                while self.running:
                    frame_started = time.perf_counter()
                    self._events()
                    input_finished = time.perf_counter()
                    self._update()
                    update_finished = time.perf_counter()
                    dirty_rectangles = self._draw()
                    render_finished = time.perf_counter()
                    self.display.present(dirty_rectangles)
                    present_finished = time.perf_counter()
                    self.presentation_frames += 1
                    self.total_scale_ms += self.display.last_scale_ms
                    self.max_scale_ms = max(self.max_scale_ms, self.display.last_scale_ms)
                    self.total_backend_present_ms += self.display.last_backend_present_ms
                    self.max_backend_present_ms = max(self.max_backend_present_ms, self.display.last_backend_present_ms)
                    self.clock.tick(FPS)
                    frame_finished = time.perf_counter()
                    self.performance.record(FrameTiming(
                        input_ms=(input_finished - frame_started) * 1000,
                        update_ms=(update_finished - input_finished) * 1000,
                        render_ms=(render_finished - update_finished) * 1000,
                        present_ms=(present_finished - render_finished) * 1000,
                        work_ms=(present_finished - frame_started) * 1000,
                        frame_ms=(frame_finished - frame_started) * 1000,
                    ))
        finally:
            self.close()

    def _events(self) -> None:
        actions: list[Action | Release] = []
        keyboard_action_count = 0
        if self.console:
            console_events = self.console.poll_actions()
            for button, pressed in self.console.pad_button_events:
                self._record_pad_button(button, pressed)
            if DeviceEvent.PAD_DISCONNECTED in console_events:
                self.pad_buttons.clear()
            actions = [event for event in console_events if isinstance(event, (Action, Release))]
            keyboard_action_count = self.console.keyboard_action_count
        else:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
                    self._record_pad_button(event.button, event.type == pygame.JOYBUTTONDOWN)
                if self.joystick:
                    device = self.joystick.handle_event(event)
                    if device is DeviceEvent.PAD_DISCONNECTED:
                        self.held.clear()
                        self.pad_buttons.clear()
                actions.extend(actions_from_event(event))
        for index, action in enumerate(actions):
            if isinstance(action, Release):
                self.held.discard(self._direction(action.action))
                continue
            if action is Action.SELECT:
                if self.screen is Screen.PLAYING:
                    self._open_leave_confirmation()
                elif self.screen is Screen.PAUSED:
                    self._open_leave_confirmation()
                elif self.screen is Screen.LEAVE_CONFIRMATION:
                    self._cancel_leave_confirmation()
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
            elif self.screen is Screen.PLAYING and action is Action.START:
                self._pause()
            elif self.screen is Screen.PAUSED and action is Action.START:
                self._resume()
            elif self.screen is Screen.LEAVE_CONFIRMATION:
                self._handle_leave_confirmation(action)
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

    def _record_pad_button(self, button: int, pressed: bool) -> None:
        """Keep individual pad contacts through menus, pauses, and modals."""
        if button not in (0, 1, 2, 3, 4, 5, 6, 7):
            return
        if pressed:
            self.pad_buttons.add(button)
        else:
            self.pad_buttons.discard(button)

    def _start(self, song: Song) -> None:
        self.song, self.timeline = song, TerrainTimeline(song.beats, self.seed)
        self.stamina, self.score, self.clean_transitions = Stamina(), 0, 0
        self.preplay_started_at = time.monotonic()
        self.performance = PerformanceTracker()
        self.max_audio_step_ms = 0.0
        self.audio_jump_count = 0
        self.max_boundary_lateness_ms = 0.0
        self.report_written = False
        self.presentation_frames = 0
        self.total_scale_ms = 0.0
        self.max_scale_ms = 0.0
        self.total_backend_present_ms = 0.0
        self.max_backend_present_ms = 0.0
        self.started_at = 0.0
        self.music_started = False
        self.pause_started_at = 0.0
        self.last_time = 0.0; self.active_stance = self.timeline.initial_stance; self.held.clear(); self.keyboard_until.clear()
        self.timeline.prepare_song(song.duration)
        self.terrain_rows = self.timeline.tile_stances(song.duration, TILE)
        self.gameplay_base = None
        self.gameplay_needs_full_present = True
        # Decode before the start line reaches the receptor, but remain silent.
        pygame.mixer.music.load(str(song.audio_path))
        self.screen = Screen.PLAYING

    def _pause(self) -> None:
        if self.screen is not Screen.PLAYING:
            return
        self.pause_started_at = time.monotonic()
        if self.music_started:
            pygame.mixer.music.pause()
        self.screen = Screen.PAUSED
        self.gameplay_needs_full_present = True

    def _resume(self) -> None:
        if self.screen is not Screen.PAUSED:
            return
        paused_for = time.monotonic() - self.pause_started_at
        if self.music_started:
            pygame.mixer.music.unpause()
        else:
            self.preplay_started_at += paused_for
        self.screen = Screen.PLAYING
        self.gameplay_needs_full_present = True

    def _open_leave_confirmation(self) -> None:
        self.leave_return_screen = self.screen
        self.leave_confirm_selected = False
        if self.screen is Screen.PLAYING:
            self._pause()
        self.screen = Screen.LEAVE_CONFIRMATION
        self.gameplay_needs_full_present = True

    def _cancel_leave_confirmation(self) -> None:
        if self.leave_return_screen is Screen.PLAYING:
            self.screen = Screen.PAUSED
            self._resume()
        else:
            self.screen = self.leave_return_screen
            self.gameplay_needs_full_present = True

    def _handle_leave_confirmation(self, action: Action) -> None:
        if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
            self.leave_confirm_selected = not self.leave_confirm_selected
        elif action is Action.START:
            if self.leave_confirm_selected:
                pygame.mixer.music.stop()
                self._write_performance_report("cancelled")
                self.screen = Screen.LIST
            else:
                self._cancel_leave_confirmation()

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
        raw_audio_step = max(0.0, now - self.last_time)
        if self.last_time > 0:
            self.max_audio_step_ms = max(self.max_audio_step_ms, raw_audio_step * 1000)
            if raw_audio_step > 0.125:
                self.audio_jump_count += 1
        delta = min(0.1, raw_audio_step); self.last_time = now
        speed = difficulty_at(now, self.song.duration).speed
        expected = self.timeline.stance_at(now)
        if expected != self.active_stance:
            self.active_stance = expected
            change = self.timeline.latest_change_at(now)
            if change is not None:
                self.max_boundary_lateness_ms = max(self.max_boundary_lateness_ms, (now - change.time) * 1000)
            self.clean_transitions += 1
            self.score += 50 + self.clean_transitions * 3
        contacts = lane_contacts(self._contact_actions())
        valid = is_valid_stance(contacts, expected)
        self.stamina.update(now, delta, valid, self.timeline.in_transition_window(now, self.song.duration))
        if valid:
            self.score += int(delta * 10)
        if self.stamina.value <= 0 or now >= self.song.duration or (not pygame.mixer.music.get_busy() and now > 0.5):
            self.result_success = self.stamina.value > 0
            pygame.mixer.music.stop()
            self._write_performance_report("complete" if self.result_success else "stamina")
            self.screen = Screen.RESULT

    def _write_performance_report(self, outcome: str) -> None:
        if self.report_written:
            return
        self.report_written = True
        report = self.performance.report() + (
            f"outcome={outcome}\n"
            f"maximum_audio_clock_step_ms={self.max_audio_step_ms:.3f}\n"
            f"audio_clock_steps_over_125ms={self.audio_jump_count}\n"
            f"maximum_terrain_boundary_lateness_ms={self.max_boundary_lateness_ms:.3f}\n"
            f"average_scale_ms={self.total_scale_ms / max(1, self.presentation_frames):.3f}\n"
            f"maximum_scale_ms={self.max_scale_ms:.3f}\n"
            f"average_backend_present_ms={self.total_backend_present_ms / max(1, self.presentation_frames):.3f}\n"
            f"maximum_backend_present_ms={self.max_backend_present_ms:.3f}\n"
        )
        try:
            PERFORMANCE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            PERFORMANCE_REPORT_PATH.write_text(report, encoding="utf-8")
            logging.getLogger(__name__).info("Shadow Run performance report: %s", PERFORMANCE_REPORT_PATH)
        except OSError:
            logging.getLogger(__name__).warning("Could not write Shadow Run performance report", exc_info=True)

    def _contact_actions(self) -> set[str]:
        now = time.monotonic()
        self.keyboard_until = {direction: until for direction, until in self.keyboard_until.items() if until > now}
        pad_directions = {self._direction(PAD_ACTIONS[button]) for button in self.pad_buttons}
        return self.held | set(self.keyboard_until) | pad_directions

    def _draw(self) -> list[pygame.Rect] | None:
        surface = self.screen_surface
        if self.screen is Screen.LIST:
            surface.blit(self.menu_background, (0, 0))
            surface.blit(self.big_font.render(self.settings.title, False, (255, 225, 122)), (22, 22))
            if not self.songs:
                surface.blit(self.font.render("No prepared WAV songs", False, (220, 220, 230)), (22, 72))
            for row, song in enumerate(self.songs[self.first_visible:self.first_visible + VISIBLE_SONG_ROWS]):
                index = self.first_visible + row
                y = 52 + row * 18
                if index == self.selected: surface.blit(self.font.render(">", False, (255, 210, 80)), (20, y))
                if index == self.selected:
                    self._draw_focused_title(song, y)
                else:
                    surface.blit(self.font.render(self.song_labels[song.audio_path], False, (240, 242, 255)), (TITLE_RECT.x, y))
            if self.songs:
                preview = self.song_covers[self.songs[self.selected].audio_path]
                pygame.draw.rect(surface, (255, 225, 122), PREVIEW_RECT.inflate(4, 4), 1)
                surface.blit(preview, PREVIEW_RECT.topleft)
            return None
        if self.screen is Screen.RESULT:
            surface.blit(self.result_success_background if self.result_success else self.result_failed_background, (0, 0))
            if self.result_success:
                score = self.big_font.render(str(self.score), False, (255, 235, 109))
                shadow = self.big_font.render(str(self.score), False, (24, 48, 40))
                score_rect = score.get_rect(center=(WIDTH // 2, 55))
                surface.blit(shadow, score_rect.move(1, 1))
                surface.blit(score, score_rect)
            return None
        if self.gameplay_base is None:
            self.gameplay_base = self._create_gameplay_base()
            surface.blit(self.gameplay_base, (0, 0))
        elif self.gameplay_needs_full_present:
            # A modal shades the whole logical canvas. Restore every pixel
            # once on both entry and dismissal before dirty updates resume.
            surface.blit(self.gameplay_base, (0, 0))
        else:
            for rectangle in self._gameplay_dirty_rectangles():
                surface.blit(self.gameplay_base, rectangle, rectangle)
        self._draw_game()
        if self.screen is Screen.PAUSED:
            self._draw_modal(self.settings.pause_text)
        elif self.screen is Screen.LEAVE_CONFIRMATION:
            self._draw_modal(self.settings.exit_confirmation_text, confirmation=True)
        if self.debug:
            surface.blit(self.font.render(f"held={','.join(sorted(self._contact_actions()))} stance={self.active_stance or ''}", False, (255, 255, 255)), (4, 220))
        if self.screen in (Screen.PAUSED, Screen.LEAVE_CONFIRMATION):
            return [pygame.Rect(0, 0, WIDTH, HEIGHT)]
        if self.gameplay_needs_full_present:
            self.gameplay_needs_full_present = False
            return [pygame.Rect(0, 0, WIDTH, HEIGHT)]
        return self._gameplay_dirty_rectangles()

    def _create_gameplay_base(self) -> pygame.Surface:
        base = pygame.Surface((WIDTH, HEIGHT), depth=self.screen_surface.get_bitsize(), masks=self.screen_surface.get_masks())
        base.blit(self.gameplay_background, (0, 0))
        return base

    def _draw_modal(self, message: str, confirmation: bool = False) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 165))
        self.screen_surface.blit(shade, (0, 0))
        frame = pygame.Rect(76, 78, 275, 84 if confirmation else 56)
        pygame.draw.rect(self.screen_surface, (18, 35, 42), frame)
        pygame.draw.rect(self.screen_surface, (240, 245, 255), frame, 1)
        message_surface = self.modal_font.render(message, False, (255, 235, 109))
        if not confirmation:
            self.screen_surface.blit(message_surface, message_surface.get_rect(center=frame.center))
            return
        choices = ((self.settings.exit_confirm_button, self.leave_confirm_selected), (self.settings.exit_cancel_button, not self.leave_confirm_selected))
        labels = [(self.font.render(label, False, (255, 210, 80) if selected else (225, 230, 236)), selected) for label, selected in choices]
        gap = 36
        content_height = message_surface.get_height() + 14 + max(label.get_height() for label, _ in labels)
        content_top = frame.centery - content_height // 2
        self.screen_surface.blit(message_surface, message_surface.get_rect(midtop=(frame.centerx, content_top)))
        button_y = content_top + message_surface.get_height() + 14
        block_width = sum(label.get_width() for label, _ in labels) + gap
        x = frame.centerx - block_width // 2
        for label, selected in labels:
            if selected:
                self.screen_surface.blit(self.font.render(">", False, (255, 210, 80)), (x - 12, button_y))
            self.screen_surface.blit(label, (x, button_y))
            x += label.get_width() + gap

    def _load_menu_background(self) -> pygame.Surface:
        """Keep menu art separate from gameplay and decode it only once."""
        return self._load_scene(MENU_BACKGROUND_PATH, (17, 48, 43))

    def _load_scene(self, path: Path, fallback: tuple[int, int, int]) -> pygame.Surface:
        """Decode a logical-resolution scene once, using a safe solid fallback."""
        background = pygame.Surface((WIDTH, HEIGHT), depth=self.screen_surface.get_bitsize(), masks=self.screen_surface.get_masks())
        try:
            image = pygame.image.load(path)
            converted = pygame.Surface(image.get_size(), depth=background.get_bitsize(), masks=background.get_masks())
            converted.blit(image, (0, 0))
            pygame.transform.scale(converted, background.get_size(), background)
        except (OSError, pygame.error):
            logging.getLogger(__name__).warning("Cannot load Shadow Run scene %s", path)
            background.fill(fallback)
        return background

    def _load_cover_preview(self, song: Song) -> pygame.Surface:
        """Load once at menu startup; missing covers get original pixel art."""
        preview = pygame.Surface((PREVIEW_SIZE, PREVIEW_SIZE), depth=self.screen_surface.get_bitsize(), masks=self.screen_surface.get_masks())
        if song.cover_path is not None:
            try:
                cover = pygame.image.load(song.cover_path)
                converted = pygame.Surface(cover.get_size(), depth=preview.get_bitsize(), masks=preview.get_masks())
                converted.blit(cover, (0, 0))
                return pygame.transform.scale(converted, preview.get_size())
            except (OSError, pygame.error):
                logging.getLogger(__name__).warning("Cannot load song cover %s", song.cover_path)
        hue = sum(song.title.encode("utf-8")) % 80
        preview.fill((35 + hue // 3, 45, 92 + hue))
        pygame.draw.rect(preview, (255, 225, 122), (8, 8, 112, 112), 4)
        pygame.draw.circle(preview, (80, 210, 150), (64, 56), 28)
        pygame.draw.rect(preview, (50, 125, 90), (20, 92, 88, 20))
        return preview

    def _ellipsize_title(self, title: str) -> str:
        if self.font.size(title)[0] <= TITLE_RECT.width:
            return title
        ellipsis = "..."
        end = len(title)
        while end and self.font.size(title[:end] + ellipsis)[0] > TITLE_RECT.width:
            end -= 1
        return title[:end] + ellipsis

    def _draw_focused_title(self, song: Song, y: int) -> None:
        rendered = self.font.render(song.title, False, (255, 210, 80))
        title_rect = TITLE_RECT.move(0, y)
        if rendered.get_width() <= title_rect.width:
            self.screen_surface.blit(rendered, title_rect.topleft)
            return
        # A small gap between repetitions makes a looping marquee readable.
        offset = int(time.monotonic() * 24) % (rendered.get_width() + 20)
        old_clip = self.screen_surface.get_clip()
        self.screen_surface.set_clip(title_rect)
        x = title_rect.x - offset
        self.screen_surface.blit(rendered, (x, y))
        self.screen_surface.blit(rendered, (x + rendered.get_width() + 20, y))
        self.screen_surface.set_clip(old_clip)

    def _gameplay_dirty_rectangles(self) -> list[pygame.Rect]:
        rectangles = [GRID_RECT, LEFT_HUD_RECT, RIGHT_HUD_RECT]
        if self.debug:
            rectangles.append(DEBUG_RECT)
        return rectangles

    def _draw_game(self) -> None:
        assert self.song and self.timeline
        now = self._song_time()
        preplay_now = self.pause_started_at if self.screen in (Screen.PAUSED, Screen.LEAVE_CONFIRMATION) else time.monotonic()
        preplay_elapsed = min(PREPLAY_SECONDS, preplay_now - self.preplay_started_at)
        # Countdown terrain moves at the song's initial speed.  That makes the
        # start line reach the receptor after exactly three seconds without a
        # visible speed drop when audio begins.
        initial_speed = difficulty_at(0.0, self.song.duration).speed
        start_line_y = round(PLAYER_Y - (PREPLAY_SECONDS - preplay_elapsed) * initial_speed)
        if self.music_started:
            distance = int(scroll_distance(now, self.song.duration))
            first_row = max(0, (PLAYER_Y + distance - HEIGHT) // TILE)
            last_row = min(len(self.terrain_rows), (PLAYER_Y + distance + TILE) // TILE + 1)
            rows = ((row, PLAYER_Y + distance - row * TILE, set(self.terrain_rows[row])) for row in range(first_row, last_row))
            start_line_y = PLAYER_Y + distance
        else:
            # Row zero is the start line.  Safe ground remains below it while
            # the fixed map above it approaches the player during countdown.
            rows = (
                (row, start_line_y - row * TILE, set(Lane) if row <= 0 else set(self.terrain_rows[row]))
                for row in range(-4, min(len(self.terrain_rows), 12))
            )
        for row, y, safe in rows:
            for lane in Lane:
                color = SAFE_TILE if lane in safe else DANGER_TILE
                pygame.draw.rect(self.screen_surface, color, (LANE_X + lane.value * TILE + 1, y + 1, TILE - 2, TILE - 2))
        # Row zero is the start boundary.  It enters during countdown, crosses
        # the receptor at music start, then remains visible as it flows away.
        for lane in Lane:
            x = LANE_X + lane.value * TILE
            pygame.draw.line(self.screen_surface, (255, 235, 109), (x, start_line_y), (x + TILE, start_line_y), 2)
        contacts = lane_contacts(self._contact_actions())
        for lane in Lane:
            receptor = pygame.Rect(LANE_X + lane.value * TILE + 3, PLAYER_Y - 6, TILE - 6, 12)
            pygame.draw.rect(self.screen_surface, (255, 226, 100) if lane in contacts else (31, 43, 68), receptor)
            pygame.draw.rect(self.screen_surface, (240, 245, 255), receptor, 1)
        pygame.draw.rect(self.screen_surface, (42, 43, 43), STAMINA_RECT)
        pygame.draw.rect(self.screen_surface, (83, 220, 130), (STAMINA_RECT.x, STAMINA_RECT.bottom - int(self.stamina.value), STAMINA_RECT.width, int(self.stamina.value)))
        pygame.draw.rect(self.screen_surface, (223, 237, 205), STAMINA_RECT, 1)
        progress = self._song_time() / self.song.duration
        pygame.draw.rect(self.screen_surface, (49, 86, 87), PROGRESS_RECT)
        pygame.draw.rect(self.screen_surface, (255, 210, 90), (PROGRESS_RECT.x, PROGRESS_RECT.y, int(PROGRESS_RECT.width * progress), PROGRESS_RECT.height))
        score = self.font.render(str(self.score), False, (30, 68, 61))
        self.screen_surface.blit(score, score.get_rect(center=(PROGRESS_RECT.centerx, 60)))
        if self.timeline.in_transition_window(now, self.song.duration):
            pygame.draw.rect(self.screen_surface, (230, 240, 255), (LANE_X - 6, PLAYER_Y - 5, TILE * 3 + 12, 15), 1)
        if not self.music_started:
            remaining = max(1, int(PREPLAY_SECONDS - preplay_elapsed - 0.001) + 1)
            countdown = self.big_font.render(str(remaining), False, (255, 235, 109))
            self.screen_surface.blit(countdown, countdown.get_rect(center=(WIDTH // 2, 70)))
