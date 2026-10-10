import os
from pathlib import Path

import cv2
from dotenv import load_dotenv

load_dotenv()
capture_dir = Path(os.environ.get("CAPTURE_DIR", "data/captures"))
capture_dir.mkdir(parents=True, exist_ok=True)

camera_index = 1
cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap.release()
    cap = cv2.VideoCapture(camera_index)

if not cap.isOpened():
    raise RuntimeError("เปิดกล้องไม่ได้: ตรวจสาย USB และปิดแอปที่กำลังใช้กล้องอยู่")

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
print(
    f"เปิดกล้องได้ที่ {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
    f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"
)

while True:
    ret, frame = cap.read()
    if not ret:
        print("อ่านกล้องไม่ได้")
        break
    cv2.imshow("Brio Camera", frame)
    key = cv2.waitKey(1)
    if key == ord('s'):
        cv2.imwrite(str(capture_dir / "meter_capture.jpg"), frame)
        print("บันทึกรูปแล้ว")
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
