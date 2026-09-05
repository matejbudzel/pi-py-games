"""Pygame joystick lifetime and hotplug events, isolated from game states."""

import logging

import pygame

from .input import DeviceEvent


class JoystickInput:
    def __init__(self) -> None:
        self.devices = {}
        for index in range(pygame.joystick.get_count()):
            self._open(index)

    def _open(self, index: int) -> None:
        try:
            joystick = pygame.joystick.Joystick(index)
            self.devices[joystick.get_instance_id()] = joystick
        except pygame.error:
            logging.getLogger(__name__).warning("Cannot open joystick %s", index, exc_info=True)

    def handle_event(self, event: pygame.event.Event) -> DeviceEvent | None:
        if event.type == pygame.JOYDEVICEADDED:
            previous = set(self.devices)
            self._open(event.device_index)
            if set(self.devices) != previous:
                return DeviceEvent.PAD_CONNECTED
        elif event.type == pygame.JOYDEVICEREMOVED:
            joystick = self.devices.pop(event.instance_id, None)
            if joystick is not None:
                joystick.quit()
                return DeviceEvent.PAD_DISCONNECTED
        return None
