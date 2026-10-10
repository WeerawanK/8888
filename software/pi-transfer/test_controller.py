from __future__ import annotations

import logging
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app, handle_controller_command  # noqa: E402
from controller_server import ControllerServer  # noqa: E402


class ControllerIntegrationTest(unittest.TestCase):
    def test_zoom_command_and_http_endpoint(self) -> None:
        response = app.test_client().post("/zoom/in")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["zoom"], 1.5)
        self.assertEqual(handle_controller_command("ZOOM -0.5"), "OK ZOOM 1.0")

    def test_tcp_command_round_trip(self) -> None:
        server = ControllerServer(
            "127.0.0.1",
            0,
            lambda command: f"OK {command}",
            logging.getLogger("controller-test"),
        )
        server.start()
        try:
            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
                client.sendall(b"CAPTURE\nZOOM 0.5\n")
                received = b""
                while not received.endswith(b"OK ZOOM 0.5\n"):
                    received += client.recv(128)
                self.assertEqual(received, b"OK CAPTURE\nOK ZOOM 0.5\n")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
