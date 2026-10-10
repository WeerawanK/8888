from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from googleapiclient.errors import HttpError


class SerialController:
    def __init__(
        self,
        port: str,
        baudrate: int,
        command_handler: Callable[[str], str],
        logger: logging.Logger,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.command_handler = command_handler
        self.logger = logger
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="esp32-serial-controller",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            import serial
        except ImportError:
            self.logger.error("ติดตั้ง pyserial ก่อนใช้ CONTROLLER_SERIAL_PORT")
            return

        while not self._stop.is_set():
            try:
                connection = serial.Serial(self.port, self.baudrate, timeout=1)
            except serial.SerialException as exc:
                self.logger.warning("เปิด ESP32 serial ไม่ได้: %s; จะลองใหม่", exc)
                self._stop.wait(3)
                continue

            try:
                with connection:
                    self.logger.info("ESP32 serial controller connected: %s", self.port)
                    while not self._stop.is_set():
                        raw_line = connection.readline()
                        if not raw_line:
                            continue
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("PI_CMD "):
                            continue
                        try:
                            response = self.command_handler(line[7:])
                        except (ValueError, RuntimeError, KeyError, HttpError) as exc:
                            response = f"ERR {exc}"
                        connection.write((response + "\n").encode("utf-8"))
            except serial.SerialException as exc:
                self.logger.warning("ESP32 serial หลุด: %s; จะลองเชื่อมใหม่", exc)
                self._stop.wait(1)
