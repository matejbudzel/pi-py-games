"""Direct TTY and joystick input for the legacy framebuffer backend."""

from __future__ import annotations

import fcntl
import glob
import logging
import os
import select
import struct
import sys
import termios
import time
import tty
from pathlib import Path

from .input import Action, DeviceEvent, DIRECTIONS, PAD_ACTIONS, Release


KDSETMODE = 0x4B3A
KD_TEXT = 0x00
KD_GRAPHICS = 0x01
JS_EVENT = struct.Struct("IhBB")
JSIOCGNAME = 0x80806A13
JSIOCGAXES = 0x80016A11
JSIOCGBUTTONS = 0x80016A12
PAD_DEVICE_NAME = "WiseGroup.,Ltd X-PAD, Extreme Dance Pad"
INPUT_STATUS_PATH = Path("/tmp/pi-py-games-input.txt")

KEY_SEQUENCES = {
    b"\x1b[A": Action.UP,
    b"\x1bOA": Action.UP,
    b"\x1b[B": Action.DOWN,
    b"\x1bOB": Action.DOWN,
    b"\x1b[C": Action.RIGHT,
    b"\x1bOC": Action.RIGHT,
    b"\x1b[D": Action.LEFT,
    b"\x1bOD": Action.LEFT,
    b"\x1b[19~": Action.DEBUG_TOGGLE_PERFORMANCE,
    b"\r": Action.START,
    b"\n": Action.START,
    b" ": Action.START,
    b"\x1b": Action.SELECT,
    b"1": Action.DEBUG_RESULT_1,
    b"2": Action.DEBUG_RESULT_2,
    b"3": Action.DEBUG_RESULT_3,
    b"4": Action.DEBUG_RESULT_4,
    b"5": Action.DEBUG_RESULT_5,
}
MULTIBYTE_SEQUENCES = tuple(sorted((sequence for sequence in KEY_SEQUENCES if len(sequence) > 1), key=len, reverse=True))


class ConsoleInput:
    """Claim a Linux console and read keyboard plus joystick actions directly."""

    def __enter__(self) -> ConsoleInput:
        self._keyboard_fd = sys.stdin.fileno()
        if not os.isatty(self._keyboard_fd):
            raise RuntimeError("fbdev display requires an interactive Linux console")
        self._terminal_settings = termios.tcgetattr(self._keyboard_fd)
        self._joysticks = []
        self._input_status = []
        self._button_events: list[str] = []
        self._keyboard_events: list[str] = []
        try:
            tty.setraw(self._keyboard_fd)
            self._pending = b""
            self._pending_since = 0.0
            self._joysticks, self._input_status = self._open_joysticks()
            self._next_joystick_retry = time.monotonic() + 2.0
            self._write_input_status()
            fcntl.ioctl(sys.stdout.fileno(), KDSETMODE, KD_GRAPHICS)
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        try:
            fcntl.ioctl(sys.stdout.fileno(), KDSETMODE, KD_TEXT)
        except OSError:
            pass
        try:
            self._restore_terminal()
        finally:
            for descriptor in self._joysticks:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self._joysticks = []
            self._write_input_status()
            sys.stdout.write("\x1bc")
            sys.stdout.flush()

    def poll_actions(self) -> list[Action | Release | DeviceEvent]:
        actions: list[Action | Release | DeviceEvent] = list(self._read_keyboard_actions())
        if actions:
            self._keyboard_events.extend(action.name for action in actions if isinstance(action, Action))
            self._keyboard_events = self._keyboard_events[-30:]
            self._write_input_status()
        if not self._joysticks and time.monotonic() >= self._next_joystick_retry:
            self._joysticks, self._input_status = self._open_joysticks()
            self._next_joystick_retry = time.monotonic() + 2.0
            self._write_input_status()
            if self._joysticks:
                actions.append(DeviceEvent.PAD_CONNECTED)
        for descriptor in list(self._joysticks):
            try:
                data = os.read(descriptor, JS_EVENT.size * 32)
            except BlockingIOError:
                continue
            except OSError:
                logging.getLogger(__name__).info("Dance pad disconnected", exc_info=True)
                data = b""
            if not data:
                os.close(descriptor)
                self._joysticks.remove(descriptor)
                actions.append(DeviceEvent.PAD_DISCONNECTED)
                self._input_status.append("Dance pad disconnected; waiting for reconnection.")
                self._write_input_status()
                continue
            for offset in range(0, len(data) - JS_EVENT.size + 1, JS_EVENT.size):
                _, value, event_type, button = JS_EVENT.unpack_from(data, offset)
                # Initial state packets on reconnect must not press START.
                if event_type == 1 and button in PAD_ACTIONS:
                    action = PAD_ACTIONS[button]
                    if value == 1:
                        self._button_events.append(f"button {button} -> {action.name}")
                        self._button_events = self._button_events[-30:]
                        actions.append(action)
                    elif action in DIRECTIONS:
                        actions.append(Release(action))
        return actions

    def _read_keyboard_actions(self) -> list[Action]:
        if select.select([self._keyboard_fd], [], [], 0)[0]:
            if not self._pending:
                self._pending_since = time.monotonic()
            self._pending += os.read(self._keyboard_fd, 32)
        actions: list[Action] = []
        while self._pending:
            if self._pending.startswith(b"\x03"):
                raise KeyboardInterrupt
            sequence = next((item for item in MULTIBYTE_SEQUENCES if self._pending.startswith(item)), None)
            if sequence is not None:
                actions.append(KEY_SEQUENCES[sequence])
                self._pending = self._pending[len(sequence):]
                continue
            if any(item.startswith(self._pending) for item in MULTIBYTE_SEQUENCES) and time.monotonic() - self._pending_since < 0.03:
                break
            action = KEY_SEQUENCES.get(self._pending[:1])
            if action is not None:
                actions.append(action)
            self._pending = self._pending[1:]
            self._pending_since = time.monotonic()
        return actions

    @staticmethod
    def _open_joysticks() -> tuple[list[int], list[str]]:
        descriptors: list[int] = []
        status: list[str] = []
        paths = glob.glob("/dev/input/js*")
        if not paths:
            status.append("No /dev/input/js* devices found.")
        for path in paths:
            descriptor: int | None = None
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                name = fcntl.ioctl(descriptor, JSIOCGNAME, b"\0" * 128).split(b"\0", 1)[0].decode("utf-8", "replace")
                axes = fcntl.ioctl(descriptor, JSIOCGAXES, b"\0")[0]
                buttons = fcntl.ioctl(descriptor, JSIOCGBUTTONS, b"\0")[0]
                if name == PAD_DEVICE_NAME or (axes == 2 and buttons == 10):
                    descriptors.append(descriptor)
                    descriptor = None
                    status.append(f"Using {path}: {name!r}, {axes} axes, {buttons} buttons.")
                else:
                    status.append(f"Ignoring {path}: {name!r}, {axes} axes, {buttons} buttons.")
            except OSError as error:
                status.append(f"Cannot open {path}: {error}.")
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        if not descriptors:
            status.append("No compatible dance pad opened. The game user needs read access via the input group.")
        return descriptors, status

    def _write_input_status(self) -> None:
        lines = ["pi-py-games input status", *self._input_status]
        if self._keyboard_events:
            lines.extend(("", "Keyboard actions received:", *self._keyboard_events[-30:]))
        if self._button_events:
            lines.extend(("", "Button presses received:", *self._button_events[-30:]))
        try:
            INPUT_STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _restore_terminal(self) -> None:
        if hasattr(self, "_terminal_settings"):
            termios.tcsetattr(self._keyboard_fd, termios.TCSADRAIN, self._terminal_settings)
