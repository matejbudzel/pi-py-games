"""Pygame frontend for a deliberately compact, mat-first 2048."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from common.console_input import ConsoleInput
from common.assets import SWEET16_FONT_PATH
from common.display import GameDisplay, display_settings, initialize_pygame
from common.error_logging import configure_logging
from common.input import Action, actions_from_event
from common.joystick_input import JoystickInput
from .game import Board, SIZE, TileMotion


WIDTH, HEIGHT, FPS = 427, 240, 30
OUTPUT_SIZE = (854, 480)
CELL, GAP = 44, 4
BOARD_PIXELS = CELL * SIZE + GAP * (SIZE - 1)
BOARD_X, BOARD_Y = (WIDTH - BOARD_PIXELS) // 2, (HEIGHT - BOARD_PIXELS) // 2
ANIMATION_MS = 130
BACKGROUND = (24, 30, 48)
TILE_COLORS = {
    0: (51, 65, 85), 2: (109, 190, 160), 4: (255, 205, 105), 8: (244, 140, 91),
    16: (228, 91, 107), 32: (185, 104, 201), 64: (107, 141, 235), 128: (99, 206, 225),
    256: (255, 239, 150), 512: (255, 177, 100), 1024: (255, 111, 97), 2048: (255, 81, 131),
}


def _tile_color(value: int) -> tuple[int, int, int]:
    return TILE_COLORS.get(value, (255, 81, 131))


@dataclass(frozen=True)
class MoveAnimation:
    motions: tuple[TileMotion, ...]
    spawned: tuple[int, int] | None
    started_at: int

    def progress(self, now: int) -> float:
        return min(1.0, (now - self.started_at) / ANIMATION_MS)


def _rectangle(row: float, column: float, scale: float = 1.0) -> pygame.Rect:
    size = round(CELL * scale)
    center_x = BOARD_X + column * (CELL + GAP) + CELL / 2
    center_y = BOARD_Y + row * (CELL + GAP) + CELL / 2
    return pygame.Rect(round(center_x - size / 2), round(center_y - size / 2), size, size)


def _draw_tile(screen: pygame.Surface, value: int, rectangle: pygame.Rect, font: pygame.font.Font) -> None:
    pygame.draw.rect(screen, _tile_color(value), rectangle, border_radius=3)
    text = font.render(str(value), False, (20, 25, 38))
    screen.blit(text, text.get_rect(center=rectangle.center))


def _draw(screen: pygame.Surface, board: Board, font: pygame.font.Font, animation: MoveAnimation | None, now: int) -> None:
    screen.fill(BACKGROUND)
    pygame.draw.rect(screen, (72, 85, 108), pygame.Rect(BOARD_X - 4, BOARD_Y - 4, BOARD_PIXELS + 8, BOARD_PIXELS + 8), border_radius=4)
    moving_destinations: set[tuple[int, int]] = set()
    if animation is not None:
        moving_destinations = {motion.destination for motion in animation.motions}
        if animation.spawned is not None:
            moving_destinations.add(animation.spawned)
    for row, values in enumerate(board.cells):
        for column, value in enumerate(values):
            rectangle = _rectangle(row, column)
            pygame.draw.rect(screen, _tile_color(0), rectangle, border_radius=3)
            if value and (row, column) not in moving_destinations:
                _draw_tile(screen, value, rectangle, font)
    if animation is not None:
        progress = animation.progress(now)
        eased = 1 - (1 - progress) * (1 - progress)
        for motion in animation.motions:
            source_row, source_column = motion.source
            target_row, target_column = motion.destination
            row = source_row + (target_row - source_row) * eased
            column = source_column + (target_column - source_column) * eased
            _draw_tile(screen, motion.value, _rectangle(row, column), font)
        # The combined number arrives with a tiny pop rather than appearing abruptly.
        for row, column in moving_destinations:
            value = board.cells[row][column]
            if progress >= 0.65 and value and any(motion.merged and motion.destination == (row, column) for motion in animation.motions):
                arrival = (progress - 0.65) / 0.35
                scale = 1.0 + 0.12 * math.sin(math.pi * arrival)
                _draw_tile(screen, value, _rectangle(row, column, scale), font)
        if animation.spawned is not None:
            row, column = animation.spawned
            value = board.cells[row][column]
            _draw_tile(screen, value, _rectangle(row, column, 0.65 + 0.35 * eased), font)
    if board.game_over:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 145))
        screen.blit(overlay, (0, 0))
        pygame.draw.polygon(screen, (255, 219, 109), [(151, 101), (160, 92), (169, 101), (160, 110)])


def main() -> None:
    configure_logging()
    platform_display = display_settings()
    initialize_pygame(platform_display)
    if platform_display.backend == "pygame":
        pygame.display.set_caption("2048")
    display = GameDisplay(platform_display, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT))
    screen = display.canvas
    clock = pygame.time.Clock()
    font = pygame.font.Font(SWEET16_FONT_PATH, 16)
    joystick = JoystickInput() if platform_display.backend == "pygame" else None
    console_input = ConsoleInput() if platform_display.backend == "fbdev" else None
    board = Board.new()
    running = True
    directions = {Action.LEFT: "left", Action.RIGHT: "right", Action.UP: "up", Action.DOWN: "down"}
    animation: MoveAnimation | None = None
    try:
        with console_input or _NullContext():
            while running:
                actions = []
                if console_input is not None:
                    # In fbdev mode the Linux console is the sole keyboard owner.
                    # Do not let SDL's dummy driver drain terminal key bytes first.
                    actions.extend(action for action in console_input.poll_actions() if isinstance(action, Action))
                else:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False
                            continue
                        if joystick is not None:
                            joystick.handle_event(event)
                        actions.extend(actions_from_event(event))
                for action in actions:
                    if action is Action.SELECT:
                        running = False
                    elif action is Action.START:
                        board = Board.new()
                        animation = None
                    elif action in directions and not board.game_over:
                        if board.move(directions[action]):
                            animation = MoveAnimation(tuple(board.last_moves), board.last_spawn, pygame.time.get_ticks())
                now = pygame.time.get_ticks()
                _draw(screen, board, font, animation, now)
                display.present()
                if animation is not None and animation.progress(now) >= 1.0:
                    animation = None
                clock.tick(FPS)
    finally:
        display.close()
        pygame.quit()


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


if __name__ == "__main__":
    main()
