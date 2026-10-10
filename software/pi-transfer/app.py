from __future__ import annotations

import os
import logging
from pathlib import Path

import cv2
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template
from googleapiclient.errors import HttpError

from meter_service import Camera, capture_and_record
from controller_server import ControllerServer
from serial_controller import SerialController

load_dotenv()
app = Flask(__name__)
camera = Camera(
    index=int(os.environ.get("CAMERA_INDEX", "0")),
    width=int(os.environ.get("CAMERA_WIDTH", "1920")),
    height=int(os.environ.get("CAMERA_HEIGHT", "1080")),
)
preview_width = int(os.environ.get("PREVIEW_WIDTH", "640"))
output_dir = Path(os.environ.get("CAPTURE_DIR", "captures"))
latest: dict[str, str] = {}
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def frames():
    while True:
        frame = camera.read()
        preview = frame
        if preview_width > 0 and frame.shape[1] > preview_width:
            scale = preview_width / frame.shape[1]
            preview = cv2.resize(
                frame,
                (preview_width, max(1, int(frame.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
        ok, encoded = cv2.imencode(
            ".jpg",
            preview,
            [cv2.IMWRITE_JPEG_QUALITY, 60],
        )
        if not ok:
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"


@app.get("/")
def index():
    return render_template("index.html", latest=latest)


@app.get("/video")
def video():
    return Response(
        frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.post("/capture")
def capture():
    try:
        result = perform_capture()
        return jsonify({"ok": True, **result})
    except HttpError as exc:
        return jsonify(
            {
                "ok": False,
                "error": (
                    "อัปโหลด Drive ไม่สำเร็จ: Service Account ไม่มี storage quota "
                    "ให้ใช้ Shared Drive และเพิ่ม Service Account เป็นสมาชิก "
                    "หรือเปลี่ยนไปใช้ OAuth ของบัญชี Google"
                ),
                "details": str(exc),
            }
        ), 502
    except (RuntimeError, ValueError, KeyError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def perform_capture() -> dict[str, str]:
    global latest
    latest = capture_and_record(camera, output_dir)
    return latest


@app.post("/zoom/<direction>")
def zoom(direction: str):
    if direction not in {"in", "out"}:
        return jsonify({"ok": False, "error": "ทิศทางซูมไม่ถูกต้อง"}), 400
    amount = 0.5 if direction == "in" else -0.5
    return jsonify({"ok": True, "zoom": camera.change_zoom(amount)})


def handle_controller_command(command: str) -> str:
    parts = command.strip().split()
    if not parts:
        raise ValueError("คำสั่งว่าง")
    action = parts[0].upper()

    if action == "DRIVE" and len(parts) == 3:
        # The motor driver is on the ESP32; the Pi only acknowledges the command.
        int(parts[1])
        int(parts[2])
        return "OK DRIVE"
    if action == "CAPTURE" and len(parts) == 1:
        perform_capture()
        return "OK CAPTURE"
    if action == "ZOOM" and len(parts) == 2:
        zoom = camera.change_zoom(float(parts[1]))
        return f"OK ZOOM {zoom:.1f}"
    raise ValueError(f"ไม่รู้จักคำสั่งจาก ESP32: {command}")


if __name__ == "__main__":
    controller_serial = None
    controller_server = ControllerServer(
        host=os.environ.get("CONTROLLER_HOST", "0.0.0.0"),
        port=int(os.environ.get("CONTROLLER_PORT", "8765")),
        command_handler=handle_controller_command,
        logger=logger,
    )
    controller_server.start()
    serial_port = os.environ.get("CONTROLLER_SERIAL_PORT", "").strip()
    if serial_port:
        controller_serial = SerialController(
            port=serial_port,
            baudrate=int(os.environ.get("CONTROLLER_SERIAL_BAUD", "115200")),
            command_handler=handle_controller_command,
            logger=logger,
        )
        controller_serial.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), threaded=True)
