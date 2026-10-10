from __future__ import annotations

import os
from pathlib import Path

import cv2
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template
from googleapiclient.errors import HttpError

from meter_service import Camera, capture_and_record

load_dotenv()
app = Flask(__name__)
camera = Camera(index=int(os.environ.get("CAMERA_INDEX", "0")))
output_dir = Path(os.environ.get("CAPTURE_DIR", "captures"))
latest: dict[str, str] = {}


def frames():
    while True:
        frame = camera.read()
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"


@app.get("/")
def index():
    return render_template("index.html", latest=latest)


@app.get("/video")
def video():
    return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/capture")
def capture():
    global latest
    try:
        latest = capture_and_record(camera, output_dir)
        return jsonify({"ok": True, **latest})
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), threaded=True)
