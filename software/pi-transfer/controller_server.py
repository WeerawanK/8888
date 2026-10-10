from __future__ import annotations

import logging
import socketserver
import threading
from collections.abc import Callable

from googleapiclient.errors import HttpError


class _ControllerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _ControllerTCPServer)
        for raw_line in self.rfile:
            try:
                command = raw_line.decode("ascii").strip()
                response = server.command_handler(command)
            except (UnicodeError, ValueError, RuntimeError, KeyError, HttpError) as exc:
                server.logger.warning("ESP32 command failed: %s", exc)
                response = f"ERR {exc}"
            self.wfile.write((response + "\n").encode("ascii", errors="replace"))
            self.wfile.flush()


class _ControllerTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        command_handler: Callable[[str], str],
        logger: logging.Logger,
    ) -> None:
        self.command_handler = command_handler
        self.logger = logger
        super().__init__(address, _ControllerHandler)


class ControllerServer:
    def __init__(
        self,
        host: str,
        port: int,
        command_handler: Callable[[str], str],
        logger: logging.Logger,
    ) -> None:
        self._server = _ControllerTCPServer((host, port), command_handler, logger)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="esp32-controller-server",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
