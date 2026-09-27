"""Pygame shell for Blocks, designed around the shared dance-pad actions."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time

import pygame

from common.assets import SWEET16_FONT_PATH
from common.console_input import ConsoleInput
from common.display import GameDisplay, display_settings, initialize_pygame
from common.error_logging import configure_logging
from common.input import Action, Release
from common.joystick_input import JoystickInput
from common.performance import FrameTiming, PerformanceTracker
from .config import Settings, load_settings
from .core import BOARD_HEIGHT, BOARD_WIDTH, Game, PIECES
from .input import action_for_pad_button, actions_from_blocks_event
from .progress import HighScoreStore


WIDTH, HEIGHT, FPS = 427, 240, 30
OUTPUT_SIZE = (854, 480)
BACKGROUND, PANEL, GRID, WHITE, MUTED, GOLD = (17, 21, 37), (30, 38, 61), (45, 55, 82), (241, 244, 250), (150, 164, 190), (255, 218, 83)
COLORS = {"I": (91, 214, 238), "O": (255, 218, 83), "T": (183, 126, 255), "S": (104, 221, 133), "Z": (255, 105, 112), "J": (94, 184, 255), "L": (255, 167, 72)}
CELL, BOARD_X, BOARD_Y = 10, 164, 18
BOARD_RECT = pygame.Rect(BOARD_X, BOARD_Y, BOARD_WIDTH * CELL, BOARD_HEIGHT * CELL)
FULL_RECT = pygame.Rect(0, 0, WIDTH, HEIGHT)
LEFT_HUD_RECT = pygame.Rect(8, 8, 148, 92)
RIGHT_HUD_RECT = pygame.Rect(280, 8, WIDTH - 288, 200)
PERFORMANCE_REPORT_PATH = Path(os.environ.get("PI_PY_GAMES_ERROR_LOG", "~/.local/state/pi-py-games/errors.log")).expanduser().parent / "blocks-performance.txt"


class App:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.screen_name = "splash"
        self.modal: str | None = None
        self.modal_yes = False  # cancel is deliberately focused first.
        self.game: Game | None = None
        self.countdown_until = 0.0
        self.paused = False
        self.next_fall = 0.0
        self.soft_drop_held = False
        self.next_soft_drop = 0.0
        self.high_scores = HighScoreStore(self.settings.high_score_path)
        self.new_high_score = False
        self.running = True
        self.dirty = True
        self.game_board_dirty = False
        self.game_hud_dirty = False
        self.game_cell_dirty: set[tuple[int, int]] = set()
        self.show_performance_hud = False
        self.performance_rect: pygame.Rect | None = None
        self.performance = PerformanceTracker()
        self.presentation_frames = 0
        self.total_scale_ms = self.max_scale_ms = 0.0
        self.total_backend_present_ms = self.max_backend_present_ms = 0.0
        self.last_scale_ms = 0.0
        self._last_countdown = None

    def start_game(self) -> None:
        self.game = Game.new()
        self.screen_name, self.modal, self.paused = "game", None, False
        self.new_high_score = False
        self._begin_countdown()
        self.dirty = True

    def _begin_countdown(self) -> None:
        self.countdown_until = time.monotonic() + self.settings.countdown_seconds
        self.next_fall = 0.0
        self.soft_drop_held = False
        self.next_soft_drop = 0.0
        self._last_countdown = None

    def _countdown_value(self, now: float) -> int:
        return max(0, int(self.countdown_until - now + 0.999))

    def _open_modal(self, kind: str) -> None:
        self.modal, self.modal_yes, self.dirty = kind, False, True

    def _close_modal(self) -> None:
        """Restore every pixel hidden by a modal shade or its border."""
        modal_kind = self.modal
        self.modal = None
        if modal_kind == "leave" and self.screen_name == "game":
            # Countdown time is not spent while deciding whether to leave.
            # Returning from this modal should feel like resuming a pause.
            self.paused = False
            self._begin_countdown()
        self.dirty = True

    def handle(self, action: Action, *, can_hold: bool = True) -> None:
        if action is Action.DEBUG_TOGGLE_PERFORMANCE:
            self.show_performance_hud = not self.show_performance_hud
            return
        if self.modal:
            if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
                self.modal_yes = not self.modal_yes
                self.dirty = True
            elif action is Action.SELECT:
                self._close_modal()
            elif action is Action.START:
                accept = self.modal_yes
                if accept:
                    self.modal = None
                    self.running = False
                    self.dirty = True
                else:
                    self._close_modal()
            return
        if self.screen_name == "splash":
            if action is Action.START: self.start_game()
            elif action is Action.SELECT: self.running = False
            return
        if self.screen_name == "result":
            if action is Action.START: self.start_game()
            elif action is Action.SELECT: self.running = False
            return
        if self.paused:
            if action is Action.START:
                self.paused = False
                self._begin_countdown()
                self.dirty = True
            elif action is Action.SELECT:
                self._open_modal("leave")
            return
        if action is Action.SELECT:
            self._open_modal("leave")
        elif action is Action.START:
            self.paused, self.soft_drop_held, self.dirty = True, False, True
        elif self._countdown_value(time.monotonic()) == 0 and self.game:
            before = self._game_snapshot()
            if action is Action.LEFT: self.game.move(-1, 0)
            elif action is Action.RIGHT: self.game.move(1, 0)
            elif action is Action.DOWN: self._soft_drop_pressed(can_hold)
            elif action is Action.LEFT_UP: self.game.rotate(-1)
            elif action in (Action.UP, Action.RIGHT_UP): self.game.rotate(1)
            if action is not Action.DOWN: self._check_game_over()
            self._mark_game_change(before)

    def release(self, released: Release) -> None:
        if released.action is Action.DOWN:
            self.soft_drop_held = False
            self.next_soft_drop = 0.0

    def _soft_drop_pressed(self, can_hold: bool) -> None:
        assert self.game is not None
        self.game.soft_drop()
        self._check_game_over()
        if can_hold and self.screen_name == "game":
            self.soft_drop_held = True
            self.next_soft_drop = time.monotonic() + self.settings.soft_drop_hold_delay_seconds

    def _check_game_over(self) -> None:
        if self.game and self.game.game_over:
            self.new_high_score = self.high_scores.record(self.game.score)
            self.screen_name = "result"
            self.dirty = True

    def _game_snapshot(self) -> tuple[tuple[tuple[int, int], ...], list[list[str | None]], tuple[int, int, int, str]]:
        """Capture the small mutable state needed to decide what must repaint."""
        assert self.game is not None
        piece_cells = self._piece_positions()
        board = [row[:] for row in self.game.board]
        return piece_cells, board, (self.game.score, self.game.lines, self.game.level, self.game.next_name)

    def _piece_positions(self) -> tuple[tuple[int, int], ...]:
        if not self.game or not self.game.current:
            return ()
        return tuple((x + self.game.current.x, y + self.game.current.y) for x, y in self.game.current.cells)

    def _mark_game_change(self, before: tuple[tuple[tuple[int, int], ...], list[list[str | None]], tuple[int, int, int, str]]) -> None:
        """Mark only the scene regions altered by a move, lock, or score change."""
        if self.screen_name != "game" or not self.game:
            self.dirty = True
            return
        old_cells, old_board, old_stats = before
        if old_board != self.game.board:
            self.game_board_dirty = True
        else:
            self.game_cell_dirty.update(old_cells)
            self.game_cell_dirty.update(self._piece_positions())
        if old_stats != (self.game.score, self.game.lines, self.game.level, self.game.next_name):
            self.game_hud_dirty = True

    def update(self, now: float) -> None:
        if self.screen_name != "game" or self.modal or self.paused or not self.game:
            return
        countdown = self._countdown_value(now)
        if countdown != self._last_countdown:
            self._last_countdown, self.dirty = countdown, True
        if countdown:
            return
        if self.next_fall == 0.0:
            self.next_fall = now + self.game.fall_seconds
        if self.soft_drop_held and now >= self.next_soft_drop:
            before = self._game_snapshot()
            self.game.soft_drop()
            self.next_soft_drop = now + self.settings.soft_drop_repeat_seconds
            self._check_game_over()
            self._mark_game_change(before)
            if self.screen_name != "game":
                return
        if now >= self.next_fall:
            before = self._game_snapshot()
            self.game.tick()
            self.next_fall = now + self.game.fall_seconds
            self._check_game_over()
            self._mark_game_change(before)

    def _text(self, font: pygame.font.Font, text: str, position: tuple[int, int], color=WHITE, *, center=False) -> None:
        image = font.render(text, False, color)
        self.screen.blit(image, image.get_rect(center=position) if center else position)

    def draw(self, font: pygame.font.Font, large: pygame.font.Font) -> None:
        background = {"splash": "splash", "game": "game", "result": "result"}[self.screen_name]
        self.screen.blit(self.backgrounds[background], (0, 0))
        if self.screen_name == "splash": self._draw_splash(font, large)
        elif self.screen_name == "game": self._draw_game(font, large)
        else: self._draw_result(font, large)
        if self.modal: self._draw_modal(font, large)

    def _draw_splash(self, font, large) -> None:
        self._text(large, self.settings.title, (WIDTH // 2, 84), GOLD, center=True)
        for index, name in enumerate(("I", "O", "T", "S", "Z", "J", "L")):
            pygame.draw.rect(self.screen, COLORS[name], pygame.Rect(127 + index * 25, 120 + (index % 2) * 11, 18, 18))
        self._text(font, self.settings.splash_text, (WIDTH // 2, 178), WHITE, center=True)

    def _draw_game(self, font, large) -> None:
        assert self.game is not None
        self._draw_game_board(full=True)
        self._draw_game_hud(font, large)
        if self.paused:
            self._shade(); self._text(large, self.settings.pause_text, (WIDTH // 2, HEIGHT // 2), GOLD, center=True)
        elif (value := self._countdown_value(time.monotonic())):
            self._shade(); self._text(large, str(value), (WIDTH // 2, HEIGHT // 2), GOLD, center=True)

    def _draw_game_board(self, *, full: bool, cells: set[tuple[int, int]] | None = None) -> None:
        assert self.game is not None
        if full:
            pygame.draw.rect(self.screen, PANEL, BOARD_RECT.inflate(8, 8), border_radius=3)
            pygame.draw.rect(self.screen, WHITE, BOARD_RECT.inflate(8, 8), 1, border_radius=3)
            cells = {(x, y) for y in range(BOARD_HEIGHT) for x in range(BOARD_WIDTH)}
        for x, y in cells or ():
            if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
                self._draw_cell(x, y, self.game.board[y][x])
        if self.game.current:
            for x, y in self.game.current.cells:
                self._draw_cell(x + self.game.current.x, y + self.game.current.y, self.game.current.name)

    def _draw_game_hud(self, font, large, *, restore: bool = False) -> None:
        assert self.game is not None
        if restore:
            for rectangle in (LEFT_HUD_RECT, RIGHT_HUD_RECT):
                self.screen.blit(self.backgrounds["game"], rectangle.topleft, rectangle)
        self._text(large, self.settings.title, (17, 19), GOLD)
        self._text(font, "REKORD", (17, 54), MUTED)
        self._text(large, str(self.high_scores.high_score), (17, 69), GOLD if self.game.score >= self.high_scores.high_score and self.game.score else WHITE)
        self._text(font, "SKÓRE", (285, 19), MUTED)
        self._text(large, str(self.game.score), (285, 33), WHITE)
        self._text(font, "ÚROVEŇ", (285, 66), MUTED)
        self._text(large, str(self.game.level), (285, 80), WHITE)
        self._text(font, "RIADKY", (285, 113), MUTED)
        self._text(large, str(self.game.lines), (285, 127), WHITE)
        self._text(font, "ĎALŠÍ", (285, 159), MUTED)
        self._draw_preview(self.game.next_name, 313, 181)

    def _draw_game_pending(self, font, large) -> list[pygame.Rect]:
        """Refresh retained gameplay pixels without touching the whole canvas."""
        dirty: list[pygame.Rect] = []
        if self.game_board_dirty:
            self._draw_game_board(full=True)
            self.game_board_dirty = False
            self.game_cell_dirty.clear()
            dirty.append(BOARD_RECT.inflate(8, 8))
        elif self.game_cell_dirty:
            cells = self.game_cell_dirty.copy()
            self._draw_game_board(full=False, cells=cells)
            self.game_cell_dirty.clear()
            cell_rectangles = [pygame.Rect(BOARD_X + x * CELL, BOARD_Y + y * CELL, CELL, CELL) for x, y in cells if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT]
            if cell_rectangles:
                changed = cell_rectangles[0].copy()
                for rectangle in cell_rectangles[1:]:
                    changed.union_ip(rectangle)
                dirty.append(changed)
        if self.game_hud_dirty:
            self._draw_game_hud(font, large, restore=True)
            self.game_hud_dirty = False
            dirty.extend((LEFT_HUD_RECT, RIGHT_HUD_RECT))
        return dirty

    def _draw_cell(self, x: int, y: int, name: str | None) -> None:
        rect = pygame.Rect(BOARD_X + x * CELL, BOARD_Y + y * CELL, CELL, CELL)
        # Partial redraws must actively erase an old falling-block interior;
        # a grid outline alone leaves its previous colour behind.
        pygame.draw.rect(self.screen, PANEL, rect)
        pygame.draw.rect(self.screen, GRID, rect, 1)
        if name:
            pygame.draw.rect(self.screen, COLORS[name], rect.inflate(-2, -2))

    def _draw_preview(self, name: str, cx: int, cy: int) -> None:
        cells = PIECES[name][0]
        min_x, max_x = min(x for x, _ in cells), max(x for x, _ in cells)
        min_y, max_y = min(y for _, y in cells), max(y for _, y in cells)
        for x, y in cells:
            rect = pygame.Rect(cx + (x - (min_x + max_x) / 2) * 8 - 3, cy + (y - (min_y + max_y) / 2) * 8 - 3, 7, 7)
            pygame.draw.rect(self.screen, COLORS[name], rect)

    def _draw_result(self, font, large) -> None:
        assert self.game is not None
        self._text(large, "KONIEC HRY", (WIDTH // 2, 30), GOLD, center=True)
        values = (("SKÓRE", self.game.score), ("RIADKY", self.game.lines), ("ÚROVEŇ", self.game.level), ("REKORD", self.high_scores.high_score))
        # Center the entire stats group between the heading and the action
        # labels.  A new-record message is its first row, not a loose banner.
        grid_top = 94 if self.new_high_score else 82
        if self.new_high_score:
            self._text(font, self.settings.new_high_score_text, (WIDTH // 2, grid_top - 26), (104, 221, 133), center=True)
        for index, (label, value) in enumerate(values):
            # Two columns, centered together rather than anchored to the left.
            x = WIDTH // 2 + (-48 if index % 2 == 0 else 48); y = grid_top + (index // 2) * 48
            self._text(font, label, (x, y), MUTED, center=True)
            self._text(large, str(value), (x, y + 22), WHITE, center=True)
        self._text(font, "ŠTART -> NOVÁ HRA", (WIDTH // 2, 203), GOLD, center=True)
        self._text(font, "SELECT -> KONIEC", (WIDTH // 2, 221), MUTED, center=True)

    def _shade(self) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); shade.fill((0, 0, 0, 165)); self.screen.blit(shade, (0, 0))

    def _draw_modal(self, font, large) -> None:
        self._shade()
        question = self.settings.leave_question
        rect = pygame.Rect(114, 85, 199, 70)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=4); pygame.draw.rect(self.screen, WHITE, rect, 1, border_radius=4)
        question_image = large.render(question, False, WHITE)
        yes_image = font.render(self.settings.yes, False, GOLD if self.modal_yes else WHITE)
        no_image = font.render(self.settings.no, False, GOLD if not self.modal_yes else WHITE)
        gap = 24
        content_height = question_image.get_height() + 8 + max(yes_image.get_height(), no_image.get_height())
        top = rect.centery - content_height // 2
        self.screen.blit(question_image, question_image.get_rect(center=(rect.centerx, top + question_image.get_height() // 2)))
        buttons_width = yes_image.get_width() + gap + no_image.get_width()
        buttons_x = rect.centerx - buttons_width // 2
        buttons_y = top + question_image.get_height() + 8
        self.screen.blit(yes_image, (buttons_x, buttons_y))
        self.screen.blit(no_image, (buttons_x + yes_image.get_width() + gap, buttons_y))

    def _draw_performance(self, surface: pygame.Surface, font) -> pygame.Rect:
        timing = self.performance.latest
        lines = (f"{timing.frames_per_second:4.1f} FPS {timing.frame_ms:4.1f}", f"r{timing.render_ms:3.1f} s{self.last_scale_ms:3.1f} p{timing.present_ms:3.1f}")
        images = [font.render(line, False, (180, 255, 180)) for line in lines]
        rect = pygame.Rect(4, HEIGHT - sum(image.get_height() for image in images) - 8, max(image.get_width() for image in images) + 8, sum(image.get_height() for image in images) + 6)
        pygame.draw.rect(surface, (0, 0, 0), rect); pygame.draw.rect(surface, (90, 150, 90), rect, 1)
        for index, image in enumerate(images): surface.blit(image, (rect.x + 4, rect.y + 3 + index * image.get_height()))
        return rect

    def _draw_pending(self, font, large) -> list[pygame.Rect]:
        """Copy only changed retained-scene areas to the display canvas."""
        if self.dirty:
            self.draw(font, large)
            self.dirty = False
            self.game_board_dirty = self.game_hud_dirty = False
            self.game_cell_dirty.clear()
            dirty = [FULL_RECT]
        elif self.screen_name == "game" and self.modal is None and not self.paused and self._countdown_value(time.monotonic()) == 0:
            dirty = self._draw_game_pending(font, large)
        else:
            dirty = []
        for rectangle in dirty:
            self.canvas.blit(self.screen, rectangle.topleft, rectangle)
        # The HUD is drawn on the display canvas, never on the retained scene.
        # It therefore measures normal rendering behaviour plus only its own
        # small dirty rectangle instead of forcing a full-frame path.
        previous_performance_rect = self.performance_rect
        if previous_performance_rect is not None:
            self.canvas.blit(self.screen, previous_performance_rect.topleft, previous_performance_rect)
            self.performance_rect = None
        if self.show_performance_hud:
            self.performance_rect = self._draw_performance(self.canvas, font)
            dirty.append(previous_performance_rect.union(self.performance_rect) if previous_performance_rect else self.performance_rect)
        elif previous_performance_rect is not None:
            dirty.append(previous_performance_rect)
        return dirty

    def _write_performance_report(self) -> None:
        report = self.performance.report() + f"average_scale_ms={self.total_scale_ms / max(1, self.presentation_frames):.3f}\nmaximum_scale_ms={self.max_scale_ms:.3f}\naverage_backend_present_ms={self.total_backend_present_ms / max(1, self.presentation_frames):.3f}\nmaximum_backend_present_ms={self.max_backend_present_ms:.3f}\n"
        try:
            PERFORMANCE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            PERFORMANCE_REPORT_PATH.write_text(report, encoding="utf-8")
        except OSError:
            logging.getLogger(__name__).warning("Could not write Blocks performance report", exc_info=True)

    def run(self) -> None:
        platform = display_settings(); initialize_pygame(platform)
        if platform.backend == "pygame": pygame.display.set_caption(self.settings.title)
        display = GameDisplay(platform, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT))
        self.canvas = display.canvas
        self.screen = pygame.Surface(
            (WIDTH, HEIGHT), depth=self.canvas.get_bitsize(), masks=self.canvas.get_masks()
        )
        asset_directory = Path(__file__).with_name("assets") / "backgrounds"
        # Keep these at the logical resolution so no runtime scaling or
        # decoding work is needed while the game is playing.
        self.backgrounds = {name: pygame.image.load(asset_directory / f"{name}.png") for name in ("splash", "game", "result")}
        # All type is deliberately sized on the 427×240 logical canvas: a
        # legible 16px base and 24px for score/result emphasis.
        font, large = pygame.font.Font(SWEET16_FONT_PATH, 16), pygame.font.Font(SWEET16_FONT_PATH, 24)
        joystick = JoystickInput() if platform.backend == "pygame" else None; console = ConsoleInput() if platform.backend == "fbdev" else None; clock = pygame.time.Clock()
        try:
            with console or _NullContext():
                while self.running:
                    started = time.perf_counter(); actions = []
                    if console:
                        polled = console.poll_actions()
                        keyboard_count = getattr(console, "keyboard_action_count", 0)
                        # A TTY has no key-up stream.  Its repeated bytes remain
                        # independent taps rather than becoming a stuck hold.
                        for action in polled[:keyboard_count]:
                            if isinstance(action, Action): self.handle(action, can_hold=False)
                        # ConsoleInput keeps this matching raw button identity only
                        # as metadata; game state still receives Action values.
                        for action, button in getattr(console, "pad_action_events", ()):
                            self.handle(action_for_pad_button(action, button))
                        for item in polled[keyboard_count:]:
                            if isinstance(item, Release): self.release(item)
                    else:
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT: self.running = False
                            if joystick: joystick.handle_event(event)
                            actions.extend(actions_from_blocks_event(event))
                    for action in actions:
                        if isinstance(action, Action): self.handle(action)
                        elif isinstance(action, Release): self.release(action)
                    input_done = time.perf_counter(); self.update(time.monotonic()); update_done = time.perf_counter()
                    dirty_rectangles = self._draw_pending(font, large)
                    render_done = time.perf_counter()
                    if dirty_rectangles:
                        display.present(dirty_rectangles); self.presentation_frames += 1
                        self.last_scale_ms = display.last_scale_ms; self.total_scale_ms += self.last_scale_ms; self.max_scale_ms = max(self.max_scale_ms, self.last_scale_ms)
                        self.total_backend_present_ms += display.last_backend_present_ms; self.max_backend_present_ms = max(self.max_backend_present_ms, display.last_backend_present_ms)
                    present_done = time.perf_counter(); clock.tick(FPS); finished = time.perf_counter()
                    self.performance.record(FrameTiming(input_ms=(input_done-started)*1000, update_ms=(update_done-input_done)*1000, render_ms=(render_done-update_done)*1000, present_ms=(present_done-render_done)*1000, work_ms=(present_done-started)*1000, frame_ms=(finished-started)*1000))
        finally:
            self._write_performance_report(); display.close(); pygame.quit()


class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *unused): return False


def main() -> None:
    configure_logging(); App(load_settings()).run()


if __name__ == "__main__": main()
