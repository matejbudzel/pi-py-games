"""Best-effort HDMI status checks outside the rendering and audio loop."""

import logging
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import subprocess
from threading import Event, Thread

from .input import DeviceEvent


LOGGER = logging.getLogger(__name__)


def tvservice_status(output: str) -> bool | None:
    match = re.search(r"state 0x[0-9a-f]+ \[([^]]+)\]", output, re.IGNORECASE)
    if match is None:
        return None
    mode = match.group(1).upper()
    if "HDMI" in mode or "DVI" in mode:
        return True
    if "OFF" in mode or "UNPLUGGED" in mode:
        return False
    return None


def cec_status(output: str) -> bool | None:
    match = re.search(r"power status:\s*([^\r\n]+)", output, re.IGNORECASE)
    if match is None:
        return None
    status = match.group(1).strip().lower()
    if status == "on":
        return True
    if status in ("standby", "in transition from on to standby"):
        return False
    return None


class DisplayMonitor:
    def __init__(self, legacy: bool = False, cec: bool = False) -> None:
        self.report_initial_disconnect = legacy or cec
        self._last_cec_status: bool | None = None
        self.status_paths = list(Path("/sys/class/drm").glob("card*-HDMI-A-*/status"))
        self.tvservice = shutil.which("tvservice") if legacy else None
        if legacy and self.tvservice is None and Path("/opt/vc/bin/tvservice").is_file():
            self.tvservice = "/opt/vc/bin/tvservice"
        self.cec_client = shutil.which("cec-client") if cec else None
        if cec and self.cec_client is None:
            LOGGER.warning("CEC monitoring requested but cec-client is unavailable")
        self.events: Queue[DeviceEvent] = Queue()
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self.status_paths or self.tvservice or self.cec_client:
            self._thread = Thread(target=self._watch, name="display-status", daemon=True)
            self._thread.start()
        else:
            LOGGER.info("HDMI monitoring unavailable on this display backend")

    @staticmethod
    def _command(arguments: list[str], input_text: str | None = None) -> str:
        try:
            result = subprocess.run(arguments, input=input_text, capture_output=True,
                                    text=True, timeout=3, check=False)
            return result.stdout if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def _read_status(self) -> bool | None:
        statuses = []
        for path in self.status_paths:
            try:
                value = path.read_text().strip()
            except OSError:
                continue
            if value in ("connected", "disconnected"):
                statuses.append(value == "connected")
        connected = any(statuses) if statuses else None
        if connected is None and self.tvservice:
            connected = tvservice_status(self._command([self.tvservice, "-s"]))
        if self.cec_client and not self._stop.is_set():
            # Single-command mode disables activation of this device as a source.
            power = cec_status(self._command([self.cec_client, "-s", "-d", "1"], "pow 0\n"))
            if power is not None:
                self._last_cec_status = power
            if self._last_cec_status is not None:
                return self._last_cec_status if connected is not False else False
        return connected

    def _watch(self) -> None:
        previous = None
        while not self._stop.is_set():
            try:
                current = self._read_status()
                if current is not None and current != previous:
                    # An unused HDMI socket on a desktop is not a lost display.
                    if previous is not None or current or self.report_initial_disconnect:
                        self.events.put(DeviceEvent.DISPLAY_CONNECTED if current else DeviceEvent.DISPLAY_DISCONNECTED)
                    previous = current
            except Exception:
                LOGGER.exception("Display status check failed")
            self._stop.wait(2)

    def poll_events(self) -> list[DeviceEvent]:
        events = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except Empty:
                return events

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.5)
