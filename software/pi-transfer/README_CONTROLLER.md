# ESP32-S3 + Raspberry Pi 5 controller

เริ่มจากคู่มือแบบทำตามทีละขั้นที่ [START_HERE_TH.md](START_HERE_TH.md)

ระบบนี้แบ่งงานเป็น 2 ส่วน:

- ESP32-S3 รับจอย Bluetooth ผ่าน Bluepad32 และควบคุมมอเตอร์/เซอร์โวโดยตรง
- Raspberry Pi 5 ต่อกล้อง USB และเปิดหน้าเว็บสำหรับวิดีโอสด, แคปภาพ และซูม

ESP32 ไม่จำเป็นต้องต่อกับ Pi เพื่อให้ดูภาพ, ซูม หรือแคปภาพจากเว็บทำงาน
การเชื่อมต่อระหว่าง ESP32 กับ Pi เป็นเพียงทางเลือกสำหรับส่งคำสั่งจากจอยไปยัง Pi
ซึ่งโหมดปัจจุบันไม่ได้ใช้แล้ว

ค่าเริ่มต้นใช้ Wi-Fi โดยทั้งสองบอร์ดต้องอยู่เครือข่ายเดียวกัน ถ้าต้องการต่อ
ESP32 กับ Pi 5 ด้วยสาย USB ให้ใช้โหมด USB Serial ตามหัวข้อด้านล่าง

## การควบคุม

| จอย | การทำงาน |
|---|---|
| Left stick ขึ้น/ลง | เดินหน้า/ถอยหลัง |
| Left stick ซ้าย/ขวา | หมุนซ้าย/ขวา โดยผสมความเร็วสองมอเตอร์ |
| Right stick ขึ้น/ลง | Pan กล้องขึ้น/ลง |
| A / X / B | ไม่ใช้ควบคุมกล้องในโหมดปัจจุบัน |
| เว็บ Pi | แคปภาพและซูมเข้า/ออก |

## การต่ออุปกรณ์

### TB6612FNG → ESP32-S3

ค่าที่อยู่ใน sketch ปัจจุบัน:

| TB6612FNG | ESP32-S3 |
|---|---:|
| PWMA | GPIO 4 |
| AIN1 | GPIO 6 |
| AIN2 | GPIO 5 |
| PWMB | GPIO 7 |
| BIN1 | GPIO 15 |
| BIN2 | GPIO 16 |
| STBY | GPIO 17 |

ต่อมอเตอร์ซ้ายเข้าช่อง A และมอเตอร์ขวาเข้าช่อง B, ต่อ GND ของแหล่งจ่ายมอเตอร์ร่วมกับ GND ของ ESP32 และจ่ายไฟมอเตอร์เข้าขา VM ของ TB6612FNG

เซอร์โว pan ใช้สัญญาณที่ GPIO 8 และต้องใช้ไฟเลี้ยงแยกที่เหมาะสมสำหรับ MG996 โดยต่อ GND ร่วมกับ ESP32 ห้ามจ่าย MG996 จากขา 3.3V ของ ESP32 ค่าเริ่มต้นใน sketch เป็น positional servo 0–180 องศา; ถ้าใช้ continuous-rotation servo ให้ตั้ง `PAN_SERVO_CONTINUOUS` เป็น `true`

## การติดตั้งบน Pi 5

1. ติดตั้ง dependencies จาก `requirements.txt`
   - ถ้าใช้กล้อง CSI ให้ติดตั้งเพิ่มด้วย `sudo apt install python3-picamera2`
2. คัดลอก `.env.example` เป็น `.env`
3. ตั้ง `CAMERA_INDEX`, `CAMERA_BACKEND`, `CAPTURE_DIR`, `PORT` และ `CONTROLLER_PORT`
4. รันจากโฟลเดอร์นี้ด้วย `python app.py`
5. เปิด `http://<PI_IP>:5000/` เพื่อดูวิดีโอสด

ถ้าต้องการให้ Pi เปิดระบบเองหลัง reboot ให้ใช้ไฟล์
`meter-controller.service.example` ตามขั้นตอนใน `START_HERE_TH.md`

ทดสอบ endpoint ซูมโดยไม่ต้องต่อฮาร์ดแวร์ได้ด้วย
`python test_controller.py`

การแคปภาพและซูมใช้หน้าเว็บโดยตรง จึงไม่ต้องให้ ESP32 เชื่อมต่อ TCP `8765`
และไม่ต้องตั้ง `PI_HOST` เพื่อใช้งานกล้อง

ตั้ง `CAMERA_BACKEND=opencv` สำหรับ USB webcam หรือ `CAMERA_BACKEND=picamera2`
สำหรับกล้อง CSI ของ Raspberry Pi; ค่า `auto` จะลอง USB/OpenCV ก่อนแล้วค่อย fallback ไป
Picamera2

### โหมด USB Serial ระหว่าง ESP32 กับ Pi 5

1. ต่อสาย USB ระหว่าง ESP32-S3 กับ Pi 5 และตรวจชื่อพอร์ต เช่น `/dev/ttyACM0`
2. ใน sketch ตั้ง `PI_USE_WIFI = false`
3. ใน `.env` ของ Pi ตั้ง `CONTROLLER_SERIAL_PORT=/dev/ttyACM0`
4. ตั้ง `CONTROLLER_SERIAL_BAUD=115200` แล้วรัน `python app.py`

มอเตอร์และเซอร์โวยังคุมโดย ESP32 เหมือนเดิม ส่วน capture/zoom ให้กดจากหน้าเว็บ Pi

## การตั้งค่า ESP32

1. ติดตั้ง Bluepad32 และเลือกบอร์ด ESP32-S3 ที่ตรงกับฮาร์ดแวร์
2. แก้ `WIFI_SSID`, `WIFI_PASSWORD` และ `PI_HOST` ใน `esp32_s3_controller.ino`
3. อัปโหลด sketch แล้วจับคู่จอย Bluetooth
4. เปิด Serial Monitor ที่ 115200 เพื่อตรวจจอย มอเตอร์ และเซอร์โว

ถ้าจอยถูกถอดหรือ Wi-Fi ขาด ESP32 จะหยุดมอเตอร์และเซอร์โวเพื่อความปลอดภัย
