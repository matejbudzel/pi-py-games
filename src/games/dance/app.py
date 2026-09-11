"""Application state coordination and action handling."""

from __future__ import annotations

from contextlib import nullcontext
from enum import Enum, auto
import logging
from pathlib import Path

import pygame

from .assets import Assets
from .charts import Chart, difficulty_key, load_sm
from .config import APP_HEIGHT, APP_WIDTH, BACKGROUND, SETTINGS, SONG_DIRECTORY, TARGET_FPS, WINDOW_TITLE
from .gameplay import JudgedNote, Judgement, Session
from common.fbdev import FbdevPresenter
from common.console_input import ConsoleInput
from common.input import Action, DeviceEvent, Release, actions_from_event
from common.joystick_input import JoystickInput
from common.display_monitor import DisplayMonitor
from common.performance import FrameTiming, PerformanceTracker
from .songs import Song, discover_songs
from . import views


class Screen(Enum):
    SPLASH = auto()
    SONG_LIST = auto()
    EXIT_CONFIRMATION = auto()
    DIFFICULTY = auto()
    COUNTDOWN = auto()
    PLAYING = auto()
    PAUSED = auto()
    SONG_EXIT_CONFIRMATION = auto()
    RESULT = auto()


COUNTDOWN_SECONDS = 3
FEEDBACK_DURATION_SECONDS = 0.45
RECEPTOR_GLOW_DURATION_MS = 110
MIXER_FREQUENCY = 22050
MIXER_BUFFER_SAMPLES = 2048

ACTION_DIRECTIONS = {
    Action.LEFT: "left",
    Action.DOWN: "down",
    Action.UP: "up",
    Action.RIGHT: "right",
}
DEBUG_RESULT_STARS = {
    Action.DEBUG_RESULT_1: 1,
    Action.DEBUG_RESULT_2: 2,
    Action.DEBUG_RESULT_3: 3,
    Action.DEBUG_RESULT_4: 4,
    Action.DEBUG_RESULT_5: 5,
}


class App:
    def __init__(self) -> None:
        try:
            self._initialize()
        except BaseException:
            self.close()
            raise

    def _initialize(self) -> None:
        pygame.mixer.pre_init(MIXER_FREQUENCY, -16, 2, MIXER_BUFFER_SAMPLES)
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.joystick_input = JoystickInput() if SETTINGS.display_backend == "pygame" else None
        if SETTINGS.display_backend == "fbdev":
            pygame.display.set_mode((1, 1))
            self.framebuffer = self._open_framebuffer_presenter()
            self.screen = self.framebuffer.canvas
        else:
            self.screen = pygame.display.set_mode((APP_WIDTH, APP_HEIGHT))
            self.framebuffer = None
        self.display_monitor = DisplayMonitor(legacy=self.framebuffer is not None, cec=SETTINGS.display_cec)
        self.display_connected: bool | None = None
        self.paused_from = Screen.PLAYING
        self.clock = pygame.time.Clock()
        self.running = True
        self.current_screen = Screen.SPLASH
        self.songs: list[Song] = discover_songs(SONG_DIRECTORY)
        self.assets = Assets(self.songs, self.screen)
        self.selected = 0
        self.first_visible_row = 0
        self.exit_confirmation_selected = False
        self.song_exit_confirmation_selected = False
        self.song_exit_return_screen = Screen.COUNTDOWN
        self.countdown_remaining_on_modal = 0
        self.active_song: Song | None = None
        self.active_chart: Chart | None = None
        self.available_charts: tuple[Chart, ...] = ()
        self.selected_difficulty = 0
        self.session: Session | None = None
        self.feedback: Judgement | None = None
        self.feedback_until = 0.0
        self.receptor_glow_until = {direction: 0 for direction in ACTION_DIRECTIONS.values()}
        self.playback_started = False
        self.result_started_at = 0
        self.result_stars = 0
        self.countdown_started_at = 0
        self.show_performance_hud = False
        self.performance = PerformanceTracker()
        self.modal_snapshot: pygame.Surface | None = None
        self.gameplay_base: pygame.Surface | None = None
        self.gameplay_base_song: Song | None = None
        self.gameplay_needs_full_restore = False
        self.gameplay_dynamic_rectangles: list[pygame.Rect] = []
        self.gameplay_present_rectangles: list[pygame.Rect] = []
        self._last_visual_signature: tuple[object, ...] | None = None

    def run(self) -> None:
        console_input = ConsoleInput() if self.framebuffer is not None else None
        try:
            with console_input or nullcontext():
                self.console_input = console_input
                self.display_monitor.start()
                recovering = False
                while self.running:
                    try:
                        self._run_frame()
                        recovering = False
                    except Exception:
                        logging.getLogger(__name__).exception("Frame failed in %s", self.current_screen.name)
                        if recovering or (SETTINGS.display_backend == "fbdev" and self.framebuffer is None):
                            raise
                        recovering = True
                        self._return_to_song_list()
                        self._last_visual_signature = None
        finally:
            self.close()

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        cleanups = []
        if hasattr(self, "display_monitor"):
            cleanups.append(self.display_monitor.close)
        if hasattr(self, "performance"):
            cleanups.append(lambda: self.performance.write_report(Path("/tmp/last-pi-dance-run.txt")))
        if pygame.mixer.get_init():
            cleanups.append(pygame.mixer.music.stop)
        if getattr(self, "framebuffer", None) is not None:
            cleanups.append(self.framebuffer.close)
        cleanups.append(pygame.quit)
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception:
                logging.getLogger(__name__).exception("Application cleanup failed")

    def _run_frame(self) -> None:
        frame_started = pygame.time.get_ticks()
        self._handle_events()
        if not self.running:
            return
        input_finished = pygame.time.get_ticks()
        self._update()
        update_finished = pygame.time.get_ticks()
        self._render()
        render_finished = pygame.time.get_ticks()
        if self.display_connected is not False:
            if self.framebuffer is not None:
                self.framebuffer.present(self.screen, self._dirty_rectangles())
            else:
                pygame.display.flip()
        present_finished = pygame.time.get_ticks()
        self.clock.tick(TARGET_FPS)
        frame_finished = pygame.time.get_ticks()
        self.performance.record(
            FrameTiming(
                input_ms=input_finished - frame_started,
                update_ms=update_finished - input_finished,
                render_ms=render_finished - update_finished,
                present_ms=present_finished - render_finished,
                work_ms=present_finished - frame_started,
                frame_ms=frame_finished - frame_started,
            )
        )

    @staticmethod
    def _open_framebuffer_presenter() -> FbdevPresenter | None:
        if SETTINGS.display_backend == "pygame":
            return None
        if SETTINGS.display_backend == "fbdev":
            return FbdevPresenter(SETTINGS.framebuffer_device, (APP_WIDTH, APP_HEIGHT))
        raise ValueError(f"unknown display backend: {SETTINGS.display_backend}")

    def _handle_events(self) -> None:
        actions = []
        device_events = self.display_monitor.poll_events()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if self.joystick_input is not None:
                device_event = self.joystick_input.handle_event(event)
                if device_event is not None:
                    device_events.append(device_event)
            actions.extend(actions_from_event(event))
        if getattr(self, "console_input", None) is not None:
            for action in self.console_input.poll_actions():
                if isinstance(action, DeviceEvent):
                    device_events.append(action)
                else:
                    actions.append(action)
        for event in device_events:
            self._handle_device_event(event)
        # A queued START must not immediately undo an automatic pause.
        if any(event in (DeviceEvent.PAD_DISCONNECTED, DeviceEvent.DISPLAY_DISCONNECTED) for event in device_events):
            return
        if device_events and self.current_screen is Screen.PAUSED:
            return
        for action in actions:
            self._handle_action(action)

    def _handle_device_event(self, event: DeviceEvent) -> None:
        logging.getLogger(__name__).info("Hardware: %s", event.name)
        if event is DeviceEvent.DISPLAY_CONNECTED:
            if self.display_connected is False and self.framebuffer is not None:
                self.framebuffer.close()
                self.framebuffer = None
                self.framebuffer = self._open_framebuffer_presenter()
                self.screen = self.framebuffer.canvas
                self.gameplay_base = None
            self.display_connected = True
            self._last_visual_signature = None
            self._invalidate_modal_snapshot()
        elif event is DeviceEvent.DISPLAY_DISCONNECTED:
            self.display_connected = False
        if event in (DeviceEvent.PAD_DISCONNECTED, DeviceEvent.DISPLAY_DISCONNECTED):
            self._pause_song()
            if event is DeviceEvent.PAD_DISCONNECTED and self.session is not None:
                self.session.clear_pressed(self._song_position_seconds())
            if self.current_screen is Screen.SONG_EXIT_CONFIRMATION and self.song_exit_return_screen in (Screen.PLAYING, Screen.COUNTDOWN):
                self.paused_from = self.song_exit_return_screen
                self.song_exit_return_screen = Screen.PAUSED

    def _pause_song(self) -> None:
        if self.current_screen not in (Screen.PLAYING, Screen.COUNTDOWN):
            return
        self.paused_from = self.current_screen
        if self.current_screen is Screen.COUNTDOWN:
            self.countdown_remaining_on_modal = self._countdown_remaining()
        else:
            pygame.mixer.music.pause()
        self.current_screen = Screen.PAUSED
        self._invalidate_modal_snapshot()

    def _handle_action(self, action: Action | Release) -> None:
        if isinstance(action, Release):
            if self.session is not None and self.current_screen in (Screen.PLAYING, Screen.PAUSED, Screen.SONG_EXIT_CONFIRMATION):
                result = self.session.release(ACTION_DIRECTIONS[action.action], self._song_position_seconds())
                if result is not None:
                    self._show_feedback(result.judgement)
                    self._invalidate_modal_snapshot()
            return
        if action is Action.DEBUG_TOGGLE_PERFORMANCE:
            self.show_performance_hud = not self.show_performance_hud
        elif action in DEBUG_RESULT_STARS and self.current_screen in (Screen.COUNTDOWN, Screen.PLAYING, Screen.PAUSED):
            self._show_debug_result(DEBUG_RESULT_STARS[action])
        elif action is Action.SELECT:
            self._handle_select()
        elif self.current_screen is Screen.SPLASH and action is Action.START:
            self.current_screen = Screen.SONG_LIST
        elif self.current_screen is Screen.SONG_LIST:
            self._handle_song_list_action(action)
        elif self.current_screen is Screen.DIFFICULTY:
            if action in (Action.LEFT, Action.RIGHT):
                step = -1 if action is Action.LEFT else 1
                self.selected_difficulty = (self.selected_difficulty + step) % len(self.available_charts)
            elif action is Action.START:
                self._start_chart()
        elif self.current_screen is Screen.EXIT_CONFIRMATION:
            self._handle_application_exit_action(action)
        elif self.current_screen is Screen.PLAYING and action is Action.START:
            self._pause_song()
        elif self.current_screen in (Screen.COUNTDOWN, Screen.PLAYING) and action in ACTION_DIRECTIONS:
            self._handle_direction(ACTION_DIRECTIONS[action])
        elif self.current_screen is Screen.PAUSED and action is Action.START:
            if self.display_connected is False:
                return
            if self.paused_from is Screen.COUNTDOWN:
                self.countdown_started_at = pygame.time.get_ticks() - (COUNTDOWN_SECONDS - self.countdown_remaining_on_modal) * 1000
            else:
                pygame.mixer.music.unpause()
            self.current_screen = self.paused_from
            self._invalidate_modal_snapshot()
        elif self.current_screen is Screen.SONG_EXIT_CONFIRMATION:
            self._handle_song_exit_action(action)
        elif self.current_screen is Screen.RESULT and action is Action.START:
            self._return_to_song_list()

    def _handle_select(self) -> None:
        if self.current_screen is Screen.SPLASH:
            self.running = False
        elif self.current_screen is Screen.EXIT_CONFIRMATION:
            self.current_screen = Screen.SONG_LIST
        elif self.current_screen is Screen.SONG_EXIT_CONFIRMATION:
            self._cancel_song_exit()
        elif self.current_screen is Screen.RESULT:
            self._return_to_song_list()
        elif self.current_screen in (Screen.DIFFICULTY, Screen.COUNTDOWN, Screen.PLAYING, Screen.PAUSED):
            self.song_exit_return_screen = self.current_screen
            if self.current_screen is Screen.COUNTDOWN:
                self.countdown_remaining_on_modal = self._countdown_remaining()
            elif self.current_screen is Screen.PLAYING:
                pygame.mixer.music.pause()
            self.song_exit_confirmation_selected = False
            self.current_screen = Screen.SONG_EXIT_CONFIRMATION
            self._invalidate_modal_snapshot()

    def _handle_song_list_action(self, action: Action) -> None:
        if action is Action.UP:
            self.selected = (self.selected - 1) % self._menu_item_count()
            self._scroll_selection_into_view()
        elif action is Action.DOWN:
            self.selected = (self.selected + 1) % self._menu_item_count()
            self._scroll_selection_into_view()
        elif action is Action.START:
            if self.selected == len(self.songs):
                self.exit_confirmation_selected = False
                self.current_screen = Screen.EXIT_CONFIRMATION
            else:
                self._prepare_song(self.songs[self.selected])

    def _handle_application_exit_action(self, action: Action) -> None:
        if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
            self.exit_confirmation_selected = not self.exit_confirmation_selected
        elif action is Action.START:
            self.running = not self.exit_confirmation_selected
            if self.running:
                self.current_screen = Screen.SONG_LIST

    def _handle_song_exit_action(self, action: Action) -> None:
        if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
            self.song_exit_confirmation_selected = not self.song_exit_confirmation_selected
            self._invalidate_modal_snapshot()
        elif action is Action.START:
            if self.song_exit_confirmation_selected:
                self._return_to_song_list()
            else:
                self._cancel_song_exit()

    def _handle_direction(self, direction: str) -> None:
        self.receptor_glow_until[direction] = pygame.time.get_ticks() + RECEPTOR_GLOW_DURATION_MS
        if self.current_screen is Screen.PLAYING and self.session is not None:
            result = self.session.press(direction, self._song_position_seconds())
            if result is None and self.session.last_press_was_ignored:
                return
            self._show_feedback(Judgement.MISS if result is None else result.judgement)

    def _prepare_song(self, song: Song) -> None:
        try:
            parsed = load_sm(song.chart_path)
            charts = tuple(sorted(parsed.charts, key=difficulty_key))
            if not charts:
                return
            pygame.mixer.music.load(str(song.audio_path))
        except (OSError, pygame.error, ValueError):
            logging.getLogger(__name__).exception("Cannot prepare song %s", song.path)
            return
        self.active_song = song
        self.available_charts = charts
        self.selected_difficulty = 0
        self.active_chart = None
        self.session = None
        self.gameplay_base = None
        self.gameplay_base_song = None
        self.gameplay_needs_full_restore = False
        self.gameplay_dynamic_rectangles = []
        self.feedback = None
        self.playback_started = False
        self.receptor_glow_until = {direction: 0 for direction in ACTION_DIRECTIONS.values()}
        self._invalidate_modal_snapshot()
        if len(charts) > 1:
            self.current_screen = Screen.DIFFICULTY
        else:
            self._start_chart()

    def _start_chart(self) -> None:
        self.active_chart = self.available_charts[self.selected_difficulty]
        self.session = Session(self.active_chart.notes)
        self.countdown_started_at = pygame.time.get_ticks()
        self.current_screen = Screen.COUNTDOWN

    def _update(self) -> None:
        if self.display_connected is False:
            self._pause_song()
        if self.current_screen is Screen.COUNTDOWN and self._countdown_remaining() <= 0:
            pygame.mixer.music.play()
            self.playback_started = True
            self.current_screen = Screen.PLAYING
        elif self.current_screen is Screen.PLAYING and self.session is not None:
            song_time = self._song_position_seconds()
            for result in self.session.expire(song_time):
                self._show_feedback(result.judgement)
            if self.playback_started and not pygame.mixer.music.get_busy():
                self.session.expire(float("inf"))
                pygame.mixer.music.stop()
                self.result_stars = self.session.stars()
                self.result_started_at = pygame.time.get_ticks()
                self.current_screen = Screen.RESULT

    def _cancel_song_exit(self) -> None:
        if self.song_exit_return_screen is Screen.COUNTDOWN:
            self.countdown_started_at = pygame.time.get_ticks() - (COUNTDOWN_SECONDS - self.countdown_remaining_on_modal) * 1000
        elif self.song_exit_return_screen is Screen.PLAYING:
            pygame.mixer.music.unpause()
        self.current_screen = self.song_exit_return_screen
        self._invalidate_modal_snapshot()

    def _invalidate_modal_snapshot(self) -> None:
        self.modal_snapshot = None
        self.gameplay_needs_full_restore = True

    def _return_to_song_list(self) -> None:
        selected_path = self.songs[self.selected].path if self.selected < len(self.songs) else None
        self._stop_song()
        self.songs = discover_songs(SONG_DIRECTORY)
        self.assets.reload_covers(self.songs, self.screen)
        self.selected = next(
            (index for index, song in enumerate(self.songs) if song.path == selected_path),
            min(self.selected, max(0, len(self.songs) - 1)),
        )
        self.first_visible_row = 0
        self._scroll_selection_into_view()
        self.current_screen = Screen.SONG_LIST

    def _stop_song(self) -> None:
        pygame.mixer.music.stop()
        self.active_song = None
        self.active_chart = None
        self.available_charts = ()
        self.selected_difficulty = 0
        self.session = None
        self.feedback = None
        self.playback_started = False
        self.result_stars = 0
        self.gameplay_base = None
        self.gameplay_base_song = None
        self.gameplay_dynamic_rectangles = []
        self.gameplay_present_rectangles = []
        self._invalidate_modal_snapshot()

    def _show_debug_result(self, stars: int) -> None:
        pygame.mixer.music.stop()
        self.result_stars = stars
        self.result_started_at = pygame.time.get_ticks()
        self.current_screen = Screen.RESULT

    def _render(self) -> None:
        modal_screen = self.current_screen in (Screen.PAUSED, Screen.SONG_EXIT_CONFIRMATION)
        if modal_screen and self.modal_snapshot is not None:
            self.screen.blit(self.modal_snapshot, (0, 0))
            if self.show_performance_hud:
                views.render_performance_hud(self.screen, self.assets, self.performance.latest)
            return

        difficulty_screen = self.current_screen is Screen.DIFFICULTY or (
            self.current_screen is Screen.SONG_EXIT_CONFIRMATION
            and self.song_exit_return_screen is Screen.DIFFICULTY
        )
        cached_gameplay = not difficulty_screen and self.framebuffer is not None and self.current_screen in (
            Screen.COUNTDOWN,
            Screen.PLAYING,
            Screen.PAUSED,
            Screen.SONG_EXIT_CONFIRMATION,
        )
        if not cached_gameplay:
            self.screen.fill(BACKGROUND)
        now_ms = pygame.time.get_ticks()
        if self.current_screen is Screen.SPLASH:
            views.render_splash(self.screen, self.assets)
        elif self.current_screen is Screen.SONG_LIST:
            views.render_song_list(self.screen, self.assets, self.songs, self.selected, self.first_visible_row, self._visible_rows())
        elif self.current_screen is Screen.EXIT_CONFIRMATION:
            views.render_application_exit_confirmation(self.screen, self.assets, self.exit_confirmation_selected)
        elif self.current_screen is Screen.RESULT:
            views.render_result(self.screen, self.assets, self.active_song, self._audio_position_seconds(), self.result_stars, self.result_started_at, now_ms)
        elif difficulty_screen:
            views.render_difficulty_selection(self.screen, self.assets, self.active_song, len(self.available_charts), self.selected_difficulty)
            if self.current_screen is Screen.SONG_EXIT_CONFIRMATION:
                views.render_song_exit_confirmation(self.screen, self.assets, self.song_exit_confirmation_selected)
        else:
            countdown = self._countdown_remaining() if self.current_screen is Screen.COUNTDOWN else None
            if cached_gameplay and self.active_song is not None:
                if self.gameplay_base is None or self.gameplay_base_song != self.active_song:
                    self.gameplay_base = views.create_gameplay_base(self.screen, self.assets, self.active_song)
                    self.gameplay_base_song = self.active_song
                    self.gameplay_needs_full_restore = True
                full_restore = self.gameplay_needs_full_restore
                if full_restore:
                    self.screen.blit(self.gameplay_base, (0, 0))
                    self.gameplay_needs_full_restore = False
                    self.gameplay_dynamic_rectangles = []
                    self.gameplay_present_rectangles = [pygame.Rect(0, 0, APP_WIDTH, APP_HEIGHT)]
                self.gameplay_dynamic_rectangles, restored_rectangles = views.render_cached_gameplay(self.screen, self.gameplay_base, self.assets, self.active_song, self.session, self._audio_position_seconds(), self._song_position_seconds(), self.feedback, self.feedback_until, self.receptor_glow_until, now_ms, countdown, self.gameplay_dynamic_rectangles)
                if restored_rectangles and not full_restore:
                    self.gameplay_present_rectangles = restored_rectangles
            else:
                views.render_gameplay(self.screen, self.assets, self.active_song, self.session, self._audio_position_seconds(), self._song_position_seconds(), self.feedback, self.feedback_until, self.receptor_glow_until, now_ms)
                if countdown is not None:
                    views.render_countdown(self.screen, self.assets, countdown)
            if self.current_screen is Screen.PAUSED:
                views.render_modal(self.screen, self.assets, SETTINGS.pause_text)
            elif self.current_screen is Screen.SONG_EXIT_CONFIRMATION:
                views.render_song_exit_confirmation(self.screen, self.assets, self.song_exit_confirmation_selected)
        if modal_screen:
            self.modal_snapshot = self.screen.copy()
        if self.show_performance_hud:
            views.render_performance_hud(self.screen, self.assets, self.performance.latest)

    def _dirty_rectangles(self) -> list[pygame.Rect]:
        signature = (
            self.current_screen,
            self.selected,
            self.selected_difficulty,
            self.first_visible_row,
            self.exit_confirmation_selected,
            self.song_exit_confirmation_selected,
            self.show_performance_hud,
        )
        full_screen = pygame.Rect(0, 0, APP_WIDTH, APP_HEIGHT)
        hud = pygame.Rect(APP_WIDTH - 350, APP_HEIGHT - 80, 350, 80)
        if signature != self._last_visual_signature:
            dirty = [full_screen]
        elif self.current_screen in (Screen.COUNTDOWN, Screen.PLAYING):
            dirty = self.gameplay_present_rectangles
        elif self.current_screen is Screen.RESULT:
            dirty = [pygame.Rect(220, 160, 500, 160)]
        else:
            dirty = []
        if self.show_performance_hud and hud not in dirty:
            dirty.append(hud)
        self._last_visual_signature = signature
        return dirty

    def _song_position_seconds(self) -> float:
        return self._audio_position_seconds() + SETTINGS.timing_offset_ms / 1000

    def _audio_position_seconds(self) -> float:
        return 0.0 if not self.playback_started else max(0, pygame.mixer.music.get_pos()) / 1000

    def _show_feedback(self, judgement: Judgement) -> None:
        self.feedback = judgement
        self.feedback_until = self._song_position_seconds() + FEEDBACK_DURATION_SECONDS

    def _countdown_remaining(self) -> int:
        return max(0, COUNTDOWN_SECONDS - int((pygame.time.get_ticks() - self.countdown_started_at) / 1000))

    def _visible_rows(self) -> int:
        return (APP_HEIGHT - 118 - 30) // 44

    def _menu_item_count(self) -> int:
        return len(self.songs) + 1

    def _scroll_selection_into_view(self) -> None:
        selected_row = self.selected if self.selected < len(self.songs) else len(self.songs) + 1
        if selected_row < self.first_visible_row:
            self.first_visible_row = selected_row
        elif selected_row >= self.first_visible_row + self._visible_rows():
            self.first_visible_row = selected_row - self._visible_rows() + 1
