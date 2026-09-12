"""854x480 native LED-grid diagnostic for the legacy framebuffer path."""
from __future__ import annotations

from contextlib import nullcontext
import os
from pathlib import Path
import time

import pygame

from common.console_input import ConsoleInput
from common.display import GameDisplay, display_settings, initialize_pygame
from common.input import Action, actions_from_event
from common.joystick_input import JoystickInput
from common.performance import FrameTiming, PerformanceTracker

WIDTH, HEIGHT, FPS, CELL = 854, 480, 30, 24
REPORT_PATH = Path(os.environ.get("PI_PY_GAMES_ERROR_LOG", "~/.local/state/pi-py-games/errors.log")).expanduser().parent / "fb-grid-test-performance.txt"


def _pattern(surface: pygame.Surface, hue: int) -> None:
    """Build a cached LED field; changing hue is the only expensive redraw."""
    surface.fill((8, 10, 16))
    for row, y in enumerate(range(0, HEIGHT, CELL)):
        for column, x in enumerate(range(0, WIDTH, CELL)):
            color = pygame.Color(0)
            color.hsva = ((hue + row * 7 + column * 3) % 360, 72, 92, 100)
            pygame.draw.rect(surface, color, (x + 2, y + 2, CELL - 4, CELL - 4), border_radius=3)


def _write_report(tracker: PerformanceTracker) -> None:
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(tracker.report(), encoding="utf-8")
    except OSError:
        pass


def main() -> None:
    """Run a native-canvas test: no 427x240-to-854x480 scale occurs here."""
    platform = display_settings()
    initialize_pygame(platform)
    if platform.backend == "pygame":
        pygame.display.set_caption("Test LED framebufferu")
    display = GameDisplay(platform, (WIDTH, HEIGHT))
    screen = display.canvas
    clock = pygame.time.Clock()
    joystick = JoystickInput() if platform.backend == "pygame" else None
    console = ConsoleInput() if platform.backend == "fbdev" else None
    pattern = pygame.Surface((WIDTH, HEIGHT), depth=screen.get_bitsize(), masks=screen.get_masks())
    hue, running, tracker = 128, True, PerformanceTracker()
    _pattern(pattern, hue)
    try:
        with console or nullcontext():
            while running:
                frame_started = time.perf_counter()
                actions = []
                if console is not None:
                    actions = [action for action in console.poll_actions() if isinstance(action, Action)]
                else:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False
                        if joystick is not None:
                            joystick.handle_event(event)
                        actions.extend(actions_from_event(event))
                input_finished = time.perf_counter()
                for action in actions:
                    if action is Action.SELECT:
                        running = False
                    elif action in (Action.LEFT, Action.DOWN):
                        hue = (hue - 24) % 360; _pattern(pattern, hue)
                    elif action in (Action.RIGHT, Action.UP):
                        hue = (hue + 24) % 360; _pattern(pattern, hue)
                update_finished = time.perf_counter()
                offset = int(time.monotonic() * 30) % CELL
                screen.blit(pattern, (0, offset))
                screen.blit(pattern, (0, offset - HEIGHT))
                render_finished = time.perf_counter()
                display.present()
                present_finished = time.perf_counter()
                clock.tick(FPS)
                frame_finished = time.perf_counter()
                tracker.record(FrameTiming(
                    input_ms=(input_finished - frame_started) * 1000,
                    update_ms=(update_finished - input_finished) * 1000,
                    render_ms=(render_finished - update_finished) * 1000,
                    present_ms=(present_finished - render_finished) * 1000,
                    work_ms=(present_finished - frame_started) * 1000,
                    frame_ms=(frame_finished - frame_started) * 1000,
                ))
    finally:
        _write_report(tracker)
        display.close()
        pygame.quit()


if __name__ == "__main__":
    main()
