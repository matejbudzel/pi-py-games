"""Blocks-specific translation for the pad's two upper diagonal panels."""
from __future__ import annotations

import pygame

from common.input import Action, Release, actions_from_event


def actions_from_blocks_event(event: pygame.event.Event) -> list[Action | Release]:
    """Keep shared input broad, then give Blocks its two requested rotations."""
    actions = actions_from_event(event)
    if event.type == pygame.JOYBUTTONDOWN and event.button == 6:
        return [Action.LEFT_UP]
    if event.type == pygame.JOYBUTTONDOWN and event.button == 7:
        return [Action.RIGHT_UP]
    return actions


def action_for_pad_button(action: Action, button: int) -> Action:
    """Apply the same translation to ConsoleInput's already-decoded actions."""
    if button == 6 and action is Action.LEFT:
        return Action.LEFT_UP
    if button == 7 and action is Action.RIGHT:
        return Action.RIGHT_UP
    return action
