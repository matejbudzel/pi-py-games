"""Pygame frontend for a deliberately compact, mat-first 2048."""

from __future__ import annotations

import pygame

from common.console_input import ConsoleInput
from common.display import GameDisplay, display_settings, prepare_pygame_display
from common.input import Action, actions_from_event
from common.joystick_input import JoystickInput
from .game import Board, SIZE


WIDTH, HEIGHT, FPS = 320, 240, 30
BOARD_X, BOARD_Y, CELL, GAP = 80, 32, 36, 4
BACKGROUND = (24, 30, 48)
TILE_COLORS = {
    0: (51, 65, 85), 2: (109, 190, 160), 4: (255, 205, 105), 8: (244, 140, 91),
    16: (228, 91, 107), 32: (185, 104, 201), 64: (107, 141, 235), 128: (99, 206, 225),
    256: (255, 239, 150), 512: (255, 177, 100), 1024: (255, 111, 97), 2048: (255, 81, 131),
}


def _tile_color(value: int) -> tuple[int, int, int]:
    return TILE_COLORS.get(value, (255, 81, 131))


def _draw(screen: pygame.Surface, board: Board, font: pygame.font.Font) -> None:
    screen.fill(BACKGROUND)
    pygame.draw.rect(screen, (72, 85, 108), pygame.Rect(BOARD_X - 4, BOARD_Y - 4, CELL * SIZE + GAP * 3 + 8, CELL * SIZE + GAP * 3 + 8), border_radius=4)
    for row, values in enumerate(board.cells):
        for column, value in enumerate(values):
            rectangle = pygame.Rect(BOARD_X + column * (CELL + GAP), BOARD_Y + row * (CELL + GAP), CELL, CELL)
            pygame.draw.rect(screen, _tile_color(value), rectangle, border_radius=3)
            if value:
                text = font.render(str(value), False, (20, 25, 38))
                screen.blit(text, text.get_rect(center=rectangle.center))
    if board.game_over:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 145))
        screen.blit(overlay, (0, 0))
        pygame.draw.polygon(screen, (255, 219, 109), [(151, 101), (160, 92), (169, 101), (160, 110)])


def main() -> None:
    platform_display = display_settings()
    prepare_pygame_display(platform_display)
    pygame.init()
    pygame.display.set_caption("2048")
    display = GameDisplay(platform_display, (WIDTH, HEIGHT))
    screen = display.canvas
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 17)
    joystick = JoystickInput() if platform_display.backend == "pygame" else None
    console_input = ConsoleInput() if platform_display.backend == "fbdev" else None
    board = Board.new()
    running = True
    directions = {Action.LEFT: "left", Action.RIGHT: "right", Action.UP: "up", Action.DOWN: "down"}
    try:
        with console_input or _NullContext():
            while running:
                actions = []
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        continue
                    if joystick is not None:
                        joystick.handle_event(event)
                    actions.extend(actions_from_event(event))
                if console_input is not None:
                    actions.extend(action for action in console_input.poll_actions() if isinstance(action, Action))
                for action in actions:
                    if action is Action.SELECT:
                        running = False
                    elif action is Action.START:
                        board = Board.new()
                    elif action in directions and not board.game_over:
                        board.move(directions[action])
                _draw(screen, board, font)
                display.present()
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
