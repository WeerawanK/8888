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
        self._lock = threading.Lock()

    def open(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            return
        capture = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            capture = cv2.VideoCapture(self.index)
        if not capture.isOpened():
            raise RuntimeError("เปิดกล้องไม่ได้ ตรวจสอบ USB และปิดแอปอื่นที่ใช้กล้องอยู่")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._capture = capture

    def read(self) -> Any:
        with self._lock:
            self.open()
            assert self._capture is not None
            for _ in range(3):
                self._capture.read()
                time.sleep(0.05)
            for _ in range(3):
                ok, frame = self._capture.read()
                if ok and float(frame.mean()) > 2:
                    return frame
                time.sleep(0.1)
            raise RuntimeError("กล้องส่งภาพดำหรืออ่านภาพไม่ได้ ตรวจสอบฝาครอบเลนส์และ USB")

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


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
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    path = output_dir / f"meter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    if not cv2.imwrite(str(path), frame):
        raise RuntimeError(f"บันทึกภาพไม่ได้: {path}")
    meter_value = ""
    if os.environ.get("OCR_ENABLED", "false").lower() in {"1", "true", "yes"}:
        crop = os.environ.get("OCR_CROP")
        crop_values = tuple(map(int, crop.split(","))) if crop else None
        meter_value = read_meter(frame, crop_values)
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
