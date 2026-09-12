from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass

import pygame


class Action(Enum):
    LEFT = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()
    START = auto()
    SELECT = auto()
    DEBUG_RESULT_1 = auto()
    DEBUG_RESULT_2 = auto()
    DEBUG_RESULT_3 = auto()
    DEBUG_RESULT_4 = auto()
    DEBUG_RESULT_5 = auto()
    DEBUG_TOGGLE_PERFORMANCE = auto()


KEY_ACTIONS = {
    # Physical three-lane debug layout for games such as Shadow Run:
    # q/a/z = left lane, w/x = centre lane, e/d/c = right lane.
    pygame.K_q: Action.LEFT,
    pygame.K_a: Action.LEFT,
    pygame.K_z: Action.LEFT,
    pygame.K_w: Action.UP,
    pygame.K_x: Action.UP,
    pygame.K_e: Action.RIGHT,
    pygame.K_d: Action.RIGHT,
    pygame.K_c: Action.RIGHT,
    pygame.K_LEFT: Action.LEFT,
    pygame.K_RIGHT: Action.RIGHT,
    pygame.K_UP: Action.UP,
    pygame.K_DOWN: Action.DOWN,
    pygame.K_RETURN: Action.START,
    pygame.K_SPACE: Action.START,
    pygame.K_ESCAPE: Action.SELECT,
    pygame.K_F1: Action.SELECT,
    pygame.K_1: Action.DEBUG_RESULT_1,
    pygame.K_2: Action.DEBUG_RESULT_2,
    pygame.K_3: Action.DEBUG_RESULT_3,
    pygame.K_4: Action.DEBUG_RESULT_4,
    pygame.K_5: Action.DEBUG_RESULT_5,
    pygame.K_F8: Action.DEBUG_TOGGLE_PERFORMANCE,
}


@dataclass(frozen=True)
class Release:
    action: Action


class DeviceEvent(Enum):
    PAD_CONNECTED = auto()
    PAD_DISCONNECTED = auto()
    DISPLAY_CONNECTED = auto()
    DISPLAY_DISCONNECTED = auto()


PAD_ACTIONS = {0: Action.LEFT, 1: Action.DOWN, 2: Action.UP, 3: Action.RIGHT, 8: Action.START, 9: Action.SELECT}
DIRECTIONS = {Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN}


def actions_from_event(event: pygame.event.Event) -> list[Action | Release]:
    if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
        action = PAD_ACTIONS.get(event.button)
        released = event.type == pygame.JOYBUTTONUP
    elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
        if event.type == pygame.KEYDOWN and getattr(event, "repeat", False):
            return []
        action = KEY_ACTIONS.get(event.key)
        released = event.type == pygame.KEYUP
    else:
        return []
    if released:
        return [Release(action)] if action in DIRECTIONS else []
    return [action] if action is not None else []
