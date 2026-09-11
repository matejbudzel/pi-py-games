"""Pygame frontend for a deliberately compact, mat-first 2048."""

from __future__ import annotations

import pygame

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
    pygame.init()
    pygame.display.set_caption("2048")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 17)
    joystick = JoystickInput()
    board = Board.new()
    running = True
    directions = {Action.LEFT: "left", Action.RIGHT: "right", Action.UP: "up", Action.DOWN: "down"}
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue
                joystick.handle_event(event)
                for action in actions_from_event(event):
                    if action is Action.SELECT:
                        running = False
                    elif action is Action.START:
                        board = Board.new()
                    elif action in directions and not board.game_over:
                        board.move(directions[action])
            _draw(screen, board, font)
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
