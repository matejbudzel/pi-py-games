#!/usr/bin/env python3
"""Draw a simple Pygame pattern until a keyboard or joystick button is pressed.

Use this on the Pi before launching the game to verify the selected SDL2 video
driver actually reaches the connected display. It deliberately avoids all game
assets, song discovery, audio, and application state.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pygame

from common.fbdev import FbdevPresenter, FramebufferError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=854)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--seconds",
        type=float,
        default=0,
        help="exit automatically after this many seconds (0 means wait for input)",
    )
    parser.add_argument("--fbdev", type=Path, metavar="DEVICE", help="also present frames directly to this legacy framebuffer")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.width <= 0 or args.height <= 0 or args.seconds < 0:
        raise SystemExit("width/height must be positive and seconds cannot be negative")

    pygame.init()
    presenter: FbdevPresenter | None = None
    try:
        screen = pygame.display.set_mode((args.width, args.height))
        if args.fbdev is not None:
            presenter = FbdevPresenter(args.fbdev, screen.get_size())
        print(f"SDL video driver: {pygame.display.get_driver()}")
        print(f"Display surface: {screen.get_width()}x{screen.get_height()}")
        print(f"SDL_VIDEODRIVER: {os.environ.get('SDL_VIDEODRIVER', '(default)')}")
        print("Press any key or joystick button to exit (Ctrl+C also works).")

        _draw_pattern(screen)
        pygame.display.flip()
        if presenter is not None:
            presenter.present(screen)
        clock = pygame.time.Clock()
        started_at = pygame.time.get_ticks()
        while True:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
                    return 0
            if args.seconds and pygame.time.get_ticks() - started_at >= round(args.seconds * 1000):
                return 0
            clock.tick(30)
    except (pygame.error, FramebufferError, OSError) as error:
        print(f"Pygame display error: {error}", file=sys.stderr)
        return 1
    finally:
        if presenter is not None:
            presenter.close()
        pygame.quit()


def _draw_pattern(screen: pygame.Surface) -> None:
    width, height = screen.get_size()
    colors = ((255, 70, 115), (255, 220, 55), (45, 225, 245), (120, 70, 255))
    stripe_width = max(1, width // len(colors))
    for index, color in enumerate(colors):
        pygame.draw.rect(screen, color, (index * stripe_width, 0, stripe_width, height))
    for y in range(0, height, 32):
        pygame.draw.line(screen, (0, 0, 0), (0, y), (width, y), width=2)
    for x in range(0, width, 32):
        pygame.draw.line(screen, (0, 0, 0), (x, 0), (x, height), width=2)
    pygame.draw.rect(screen, (255, 255, 255), (0, 0, width, height), width=6)


if __name__ == "__main__":
    raise SystemExit(main())
