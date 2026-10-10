from __future__ import annotations

import io
import logging
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template_string, request

from controller_server import ControllerServer
from serial_controller import SerialController

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Camera:
    def __init__(self) -> None:
        self.device = os.environ.get("CAMERA_DEVICE", "/dev/video0")
        self.source = os.environ.get("CAMERA_RTSP_URL", "").strip()
        self.width = int(os.environ.get("CAMERA_WIDTH", "1280"))
        self.height = int(os.environ.get("CAMERA_HEIGHT", "720"))
        self.fps = int(os.environ.get("CAMERA_FPS", "30"))
        self.capture: cv2.VideoCapture | None = None
        self.reader: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.latest_jpeg: bytes | None = None
        self.sequence = 0
        self.last_frame_time = 0.0
        self.read_failures = 0

    def open(self) -> None:
        if self.reader is not None and self.reader.is_alive():
            return
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if self.source:
            capture = cv2.VideoCapture(self.source)
        else:
            try:
                subprocess.run(
                    [
                        "v4l2-ctl",
                        "-d",
                        self.device,
                        "--set-ctrl=exposure_dynamic_framerate=0",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
            capture = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            capture = cv2.VideoCapture(self.source or self.device)
        if not capture.isOpened():
            raise RuntimeError(f"เปิดกล้องไม่ได้: {self.device}")
        if not self.source:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_FPS, self.fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.source:
            capture.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        self.capture = capture
        self.stop_event.clear()
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
        logger.info(
            "camera started device=%s requested=%sx%s@%sfps",
            self.device,
            self.width,
            self.height,
            self.fps,
        )

    def _read_loop(self) -> None:
        while not self.stop_event.is_set():
            capture = self.capture
            if capture is None:
                return
            ok, frame = capture.read()
            if not ok or frame is None:
                self.read_failures += 1
                if self.read_failures >= 30:
                    logger.warning("camera read failed repeatedly; reopening camera")
                    capture.release()
                    if self.capture is capture:
                        self.capture = None
                    return
                time.sleep(0.005)
                continue
            self.read_failures = 0
            self.last_frame_time = time.monotonic()
            jpeg = self._as_jpeg(frame)
            if jpeg is None:
                continue
            with self.condition:
                self.latest_jpeg = jpeg
                self.sequence += 1
                self.condition.notify_all()

    @staticmethod
    def _as_jpeg(frame: Any) -> bytes | None:
        if isinstance(frame, np.ndarray) and frame.ndim <= 2:
            raw = frame.tobytes()
            if raw[:2] == b"\xff\xd8":
                return raw
        if isinstance(frame, bytes) and frame[:2] == b"\xff\xd8":
            return frame
        if isinstance(frame, np.ndarray):
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                return encoded.tobytes()
        return None

    def wait_latest(self, last_sequence: int = 0) -> tuple[int, bytes]:
        self.open()
        with self.condition:
            self.condition.wait_for(
                lambda: self.sequence > last_sequence and self.latest_jpeg is not None,
                timeout=2.0,
            )
            if self.latest_jpeg is None:
                raise RuntimeError("กล้องยังไม่ส่งภาพ")
            return self.sequence, self.latest_jpeg

    def latest(self) -> bytes:
        self.open()
        with self.condition:
            if self.latest_jpeg is None:
                self.condition.wait_for(lambda: self.latest_jpeg is not None, timeout=2.0)
            if self.latest_jpeg is None:
                raise RuntimeError("กล้องยังไม่ส่งภาพ")
            return self.latest_jpeg

    def release(self) -> None:
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.reader is not None:
            self.reader.join(timeout=1.0)
            self.reader = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None


def upload_to_drive(data: bytes, filename: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    client_file = Path(os.environ["GOOGLE_OAUTH_CLIENT_FILE"])
    token_file = Path(os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "token.json"))
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    credentials: Credentials | None = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), scopes)
    if credentials is None or not credentials.valid:
        if credentials is not None and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            raise RuntimeError("Google OAuth token ใช้ไม่ได้ ให้สร้าง token.json ใหม่บน Windows")
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    service = build("drive", "v3", credentials=credentials)
    metadata: dict[str, Any] = {"name": filename}
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="image/jpeg", resumable=False)
    started = time.time()
    uploaded = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
    ).execute()
    service.permissions().create(
        fileId=uploaded["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()
    logger.info("drive upload seconds=%.3f bytes=%d", time.time() - started, len(data))
    return f"https://drive.google.com/file/d/{uploaded['id']}/view"


def append_to_sheet(timestamp: str, image_url: str) -> None:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_file(
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=credentials)
    sheet_range = os.environ.get("GOOGLE_SHEET_RANGE", "Sheet1!A:D")
    sheet_name = sheet_range.split("!", 1)[0].strip("'")
    service.spreadsheets().values().append(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
        range=f"'{sheet_name}'!A:D",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [[
                timestamp,
                "",
                image_url,
                os.environ.get("METER_NAME", ""),
            ]]
        },
    ).execute()


app = Flask(__name__)
camera = Camera()
output_dir = Path(os.environ.get("CAPTURE_DIR", "captures"))
upload_executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
max_pending_uploads = 4

PAGE = """
<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Meter Reader</title>
  <style>
    body { margin: 0; background: #111; color: #eee; font-family: sans-serif; }
    main { max-width: 1100px; margin: auto; padding: 12px; }
    #stage { overflow: hidden; background: #000; line-height: 0; }
    #video-frame { display: block; width: 100%; height: 70vh; min-height: 360px; border: 0; transform-origin: center center; }
    button { font-size: 18px; padding: 10px 14px; margin: 8px 4px 0 0; }
    #result { white-space: pre-wrap; font-size: 14px; }
  </style>
</head>
<body>
<main>
  <div id="stage"><iframe id="video-frame" allow="autoplay" title="ภาพสดจากกล้อง"></iframe></div>
  <div>
    <button id="zoom-out">ซูมออก</button>
    <button id="zoom-in">ซูมเข้า</button>
    <button id="capture">แคปภาพ + บันทึก Drive</button>
  </div>
  <div>Zoom: <span id="zoom-label">1.0x</span></div>
  <pre id="result"></pre>
</main>
<script>
let zoom = 1.0;
const frame = document.getElementById("video-frame");
const label = document.getElementById("zoom-label");
const result = document.getElementById("result");
frame.src = `${location.protocol}//${location.hostname}:8889/robot`;
function renderZoom() {
  frame.style.transform = `scale(${zoom})`;
  label.textContent = `${zoom.toFixed(1)}x`;
}
function changeZoom(amount) {
  zoom = Math.max(1.0, Math.min(4.0, Math.round((zoom + amount) * 10) / 10));
  renderZoom();
}
async function capture() {
  result.textContent = "กำลังบันทึกภาพ...";
  const response = await fetch(`/capture?z=${zoom.toFixed(1)}`, {method: "POST"});
  const data = await response.json();
  result.textContent = JSON.stringify(data, null, 2);
  if (data.job_id) pollJob(data.job_id);
}
async function pollJob(jobId) {
  const response = await fetch(`/capture/status/${jobId}`);
  const data = await response.json();
  result.textContent = JSON.stringify(data, null, 2);
  if (data.status === "pending" || data.status === "uploading") {
    setTimeout(() => pollJob(jobId), 1000);
  }
}
document.getElementById("zoom-in").onclick = () => changeZoom(0.5);
document.getElementById("zoom-out").onclick = () => changeZoom(-0.5);
document.getElementById("capture").onclick = capture;
renderZoom();
</script>
</body>
</html>
"""


def upload_job(job_id: str, data: bytes, filename: str, timestamp: str) -> None:
    with jobs_lock:
        jobs[job_id]["status"] = "uploading"
    started = time.time()
    try:
        image_url = ""
        if os.environ.get("GOOGLE_OAUTH_CLIENT_FILE"):
            image_url = upload_to_drive(data, filename)
        if os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
            append_to_sheet(timestamp, image_url)
        elapsed = time.time() - started
        logger.info("background upload total_seconds=%.3f job=%s", elapsed, job_id)
        with jobs_lock:
            jobs[job_id].update(
                {"status": "completed", "image_url": image_url, "upload_seconds": elapsed}
            )
            if len(jobs) > 100:
                for old_job_id in list(jobs)[:-100]:
                    jobs.pop(old_job_id, None)
    except Exception as exc:
        logger.exception("background upload failed job=%s", job_id)
        with jobs_lock:
            jobs[job_id].update({"status": "failed", "error": str(exc)})
            if len(jobs) > 100:
                for old_job_id in list(jobs)[:-100]:
                    jobs.pop(old_job_id, None)


@app.get("/")
def index() -> str:
    return render_template_string(PAGE)


@app.get("/video")
def video() -> Response:
    def frames():
        sequence = 0
        while True:
            try:
                sequence, jpeg = camera.wait_latest(sequence)
            except RuntimeError as exc:
                logger.error("video error: %s", exc)
                time.sleep(0.2)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    return Response(
        frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/capture")
def capture():
    try:
        with jobs_lock:
            pending = sum(
                item["status"] in {"pending", "uploading"}
                for item in jobs.values()
            )
        if pending >= max_pending_uploads:
            return jsonify({"ok": False, "error": "กำลังอัปโหลดรูปก่อนหน้าอยู่"}), 429
        zoom = max(1.0, min(4.0, float(request.args.get("z", "1"))))
        source = camera.latest()
        crop_started = time.time()
        encode_seconds = 0.0
        if zoom <= 1.0:
            data = source
        else:
            image = cv2.imdecode(np.frombuffer(source, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("ถอดรหัส JPEG จากกล้องไม่ได้")
            height, width = image.shape[:2]
            crop_width = max(1, int(width / zoom))
            crop_height = max(1, int(height / zoom))
            x = (width - crop_width) // 2
            y = (height - crop_height) // 2
            cropped = image[y : y + crop_height, x : x + crop_width]
            encode_started = time.time()
            ok, encoded = cv2.imencode(
                ".jpg",
                cropped,
                [cv2.IMWRITE_JPEG_QUALITY, 90],
            )
            encode_seconds = time.time() - encode_started
            if not ok:
                raise RuntimeError("เข้ารหัสภาพซูมไม่ได้")
            data = encoded.tobytes()
        crop_seconds = time.time() - crop_started
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        filename = f"meter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_bytes(data)
        job_id = uuid.uuid4().hex
        with jobs_lock:
            jobs[job_id] = {
                "job_id": job_id,
                "status": "pending",
                "file": str(path),
                "zoom": zoom,
                "crop_seconds": crop_seconds,
                "encode_seconds": encode_seconds,
            }
        upload_executor.submit(upload_job, job_id, data, filename, timestamp)
        logger.info(
            "capture saved file=%s zoom=%.1f bytes=%d crop_seconds=%.3f encode_seconds=%.3f",
            path,
            zoom,
            len(data),
            crop_seconds,
            encode_seconds,
        )
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "status": "uploading",
                "file": str(path),
                "zoom": zoom,
                "crop_seconds": crop_seconds,
                "encode_seconds": encode_seconds,
            }
        ), 202
    except Exception as exc:
        logger.exception("capture failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/capture/status/<job_id>")
def capture_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "ไม่พบงานแคปภาพ"}), 404
    return jsonify({"ok": True, **job})


def handle_controller_command(command: str) -> str:
    parts = command.strip().split()
    if not parts:
        raise ValueError("คำสั่งว่าง")
    action = parts[0].upper()
    if action == "DRIVE" and len(parts) == 3:
        int(parts[1])
        int(parts[2])
        return "OK DRIVE"
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
    try:
        app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")),
            threaded=True,
            use_reloader=False,
        )
    finally:
        camera.release()
        upload_executor.shutdown(wait=False, cancel_futures=True)
