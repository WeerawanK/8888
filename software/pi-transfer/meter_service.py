from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import pytesseract
from dotenv import load_dotenv

load_dotenv()
if os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]


class Camera:
    def __init__(self, index: int = 0, width: int = 3840, height: int = 2160) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._capture: cv2.VideoCapture | None = None
        self._picamera = None
        self._lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._latest_frame: Any | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_reader = threading.Event()
        self._zoom = 1.0

    @property
    def zoom(self) -> float:
        with self._lock:
            return self._zoom

    def change_zoom(self, amount: float) -> float:
        with self._lock:
            self._zoom = max(1.0, min(4.0, round(self._zoom + amount, 1)))
            return self._zoom

    def open(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            return
        if self._picamera is not None:
            return
        backend = os.environ.get("CAMERA_BACKEND", "auto").lower()
        if backend not in {"auto", "opencv", "picamera2"}:
            raise ValueError("CAMERA_BACKEND ต้องเป็น auto, opencv หรือ picamera2")

        if backend != "picamera2":
            capture = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.index)
            if capture.isOpened():
                # Brio 4K needs MJPG for reliable high-resolution colour frames
                # over USB. If unsupported, the camera keeps its default format.
                capture.set(
                    cv2.CAP_PROP_FOURCC,
                    cv2.VideoWriter_fourcc(*"MJPG"),
                )
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                # Drain the camera continuously so the web stream uses the
                # newest frame instead of displaying USB-buffered old frames.
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._capture = capture
                self._stop_reader.clear()
                self._reader_thread = threading.Thread(
                    target=self._read_camera_loop,
                    name="camera-reader",
                    daemon=True,
                )
                self._reader_thread.start()
                return
            capture.release()

        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "เปิดกล้องไม่ได้: ติดตั้ง picamera2 สำหรับกล้อง CSI "
                "หรือกำหนด CAMERA_BACKEND=opencv สำหรับ USB camera"
            ) from exc

        picamera = Picamera2()
        configuration = picamera.create_video_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"}
        )
        picamera.configure(configuration)
        picamera.start()
        self._picamera = picamera

    def read(self) -> Any:
        with self._lock:
            self.open()
            zoom = self._zoom

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self._picamera is not None:
                frame = cv2.cvtColor(
                    self._picamera.capture_array(), cv2.COLOR_RGB2BGR
                )
            else:
                with self._frame_lock:
                    frame = (
                        self._latest_frame.copy()
                        if self._latest_frame is not None
                        else None
                    )

            if frame is not None and float(frame.mean()) > 2:
                if zoom <= 1.0:
                    return frame
                height, width = frame.shape[:2]
                crop_width = max(1, int(width / zoom))
                crop_height = max(1, int(height / zoom))
                x = (width - crop_width) // 2
                y = (height - crop_height) // 2
                return frame[y : y + crop_height, x : x + crop_width]
            time.sleep(0.01)
        raise RuntimeError("กล้องส่งภาพดำหรืออ่านภาพไม่ได้ ตรวจสอบฝาครอบเลนส์และ USB")

    def _read_camera_loop(self) -> None:
        while not self._stop_reader.is_set():
            capture = self._capture
            if capture is None:
                return
            ok, frame = capture.read()
            if ok and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.01)

    def release(self) -> None:
        self._stop_reader.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        with self._frame_lock:
            self._latest_frame = None
        if self._picamera is not None:
            self._picamera.stop()
            self._picamera.close()
            self._picamera = None


def preprocess_for_ocr(frame: Any) -> Any:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def read_meter(frame: Any, crop: tuple[int, int, int, int] | None = None) -> str:
    if crop:
        x, y, width, height = crop
        frame = frame[y : y + height, x : x + width]
    image = preprocess_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(
            image,
            config="--psm 7 -c tessedit_char_whitelist=0123456789.",
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "ไม่พบ Tesseract OCR ให้ติดตั้ง Tesseract และเพิ่มโฟลเดอร์ติดตั้งลง PATH"
        ) from exc
    value = "".join(char for char in text if char.isdigit() or char == ".")
    if not value:
        raise ValueError("OCR อ่านตัวเลขไม่สำเร็จ")
    return value


def upload_to_drive(path: Path) -> str:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "ยังไม่ได้ติดตั้ง Google API packages: pip install -r requirements.txt"
        ) from exc

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
            if not client_file.exists():
                raise RuntimeError(f"ไม่พบ OAuth client file: {client_file}")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes)
            credentials = flow.run_local_server(port=0)
        token_file.write_text(credentials.to_json(), encoding="utf-8")

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    service = build("drive", "v3", credentials=credentials)
    metadata: dict[str, Any] = {"name": path.name}
    if folder_id:
        metadata["parents"] = [folder_id]
    file = (
        service.files()
        .create(
            body=metadata,
            media_body=MediaFileUpload(str(path), mimetype="image/jpeg"),
            fields="id",
        )
        .execute()
    )
    service.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/file/d/{file['id']}/view"


def append_to_sheet(timestamp: str, meter_value: str, image_url: str) -> None:
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "ยังไม่ได้ติดตั้ง Google API packages: pip install -r requirements.txt"
        ) from exc

    credentials = Credentials.from_service_account_file(
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=credentials)
    sheet_range = os.environ.get("GOOGLE_SHEET_RANGE", "Sheet1!A:D")
    sheet_name = sheet_range.split("!", 1)[0].strip("'")
    metadata = service.spreadsheets().get(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
        fields="sheets.properties",
    ).execute()
    sheet_id = next(
        item["properties"]["sheetId"]
        for item in metadata["sheets"]
        if item["properties"]["title"] == sheet_name
    )
    existing = service.spreadsheets().values().get(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
        range=sheet_range,
    ).execute().get("values", [])
    if not existing or existing[0][:2] != ["วันที่/เวลา", "เลขมิเตอร์"]:
        if existing:
            service.spreadsheets().batchUpdate(
                spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
                body={"requests": [{"insertDimension": {"range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                }, "inheritFromBefore": False}}]},
            ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
            range=f"'{sheet_name}'!A1:D1",
            valueInputOption="USER_ENTERED",
            body={"values": [["วันที่/เวลา", "เลขมิเตอร์", "ลิงก์รูป", "ห้อง/มิเตอร์"]]},
        ).execute()
    service.spreadsheets().batchUpdate(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
        body={"requests": [{
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 4},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.12, "green": 0.32, "blue": 0.55}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        }, {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        }, {
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 4}
            }
        }]},
    ).execute()
    service.spreadsheets().values().append(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"],
        range=f"'{sheet_name}'!A:D",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[timestamp, meter_value, image_url, os.environ.get("METER_NAME", "")]]},
    ).execute()


def capture_and_record(camera: Camera, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = camera.read()
    capture_width = int(os.environ.get("CAPTURE_WIDTH", "1280"))
    capture_height = int(os.environ.get("CAPTURE_HEIGHT", "720"))
    capture_quality = int(os.environ.get("CAPTURE_JPEG_QUALITY", "80"))
    saved_frame = frame
    if capture_width > 0 and capture_height > 0:
        saved_frame = cv2.resize(
            frame,
            (capture_width, capture_height),
            interpolation=cv2.INTER_AREA,
        )
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    path = output_dir / f"meter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    if not cv2.imwrite(
        str(path),
        saved_frame,
        [cv2.IMWRITE_JPEG_QUALITY, capture_quality],
    ):
        raise RuntimeError(f"บันทึกภาพไม่ได้: {path}")
    meter_value = ""
    if os.environ.get("OCR_ENABLED", "false").lower() in {"1", "true", "yes"}:
        crop = os.environ.get("OCR_CROP")
        crop_values = tuple(map(int, crop.split(","))) if crop else None
        meter_value = read_meter(saved_frame, crop_values)
    image_url = ""
    if os.environ.get("GOOGLE_OAUTH_CLIENT_FILE"):
        image_url = upload_to_drive(path)
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
        append_to_sheet(timestamp, meter_value, image_url)
    return {
        "timestamp": timestamp,
        "meter_value": meter_value,
        "image_url": image_url,
        "file": str(path),
    }
