# คู่มือเริ่มต้นใช้งานตั้งแต่เปิดเครื่อง

คู่มือนี้ใช้สำหรับเปิดระบบตั้งแต่ศูนย์จนขับรถด้วยจอย ดูภาพสด ซูม และแคปภาพได้

ระบบมี 2 ส่วน:

- **ESP32-S3** รับจอย Bluetooth และควบคุมมอเตอร์กับเซอร์โว
- **Raspberry Pi 5** รับภาพจากกล้อง เปิดหน้าเว็บ live view และรับคำสั่งซูม/แคปภาพ

คู่มือนี้แนะนำการต่อ ESP32-S3 กับ Pi 5 ด้วย **USB Serial** เพราะไม่ต้องตั้ง IP ของ
ESP32 สำหรับคำสั่งซูมและแคปภาพ แต่ถ้าต้องการใช้ Wi-Fi มีขั้นตอนทางเลือกท้ายคู่มือ

## 0. รายการอุปกรณ์

- Raspberry Pi 5 พร้อม microSD และไฟเลี้ยง
- ESP32-S3 พร้อมสาย USB ที่ส่งข้อมูลได้
- จอย Bluetooth ที่ Bluepad32 รองรับ
- กล้อง USB หรือกล้อง CSI ของ Raspberry Pi
- TB6612FNG และมอเตอร์ DC 2 ตัว
- เซอร์โว pan และแหล่งจ่ายไฟแยกที่เหมาะสม
- สาย USB สำหรับต่อ ESP32-S3 เข้ากับ Pi 5

## 1. ต่อสายก่อนเปิดไฟ

### TB6612FNG → ESP32-S3

| TB6612FNG | GPIO |
|---|---:|
| PWMA | 4 |
| AIN1 | 6 |
| AIN2 | 5 |
| PWMB | 7 |
| BIN1 | 15 |
| BIN2 | 16 |
| STBY | 17 |

ต่อมอเตอร์ซ้ายเข้าช่อง A และมอเตอร์ขวาเข้าช่อง B

- ต่อ GND ของแหล่งจ่ายมอเตอร์ร่วมกับ GND ของ ESP32-S3
- ต่อไฟมอเตอร์เข้าขา VM ของ TB6612FNG
- ห้ามจ่ายไฟมอเตอร์จากขา 3.3V ของ ESP32
- สายสัญญาณเซอร์โว MG996 pan ต่อ GPIO 8
- จ่ายไฟ MG996 จากแหล่งจ่าย 5–6V แยกที่จ่ายกระแสได้เพียงพอ และต่อ GND ร่วมกับ ESP32
- ห้ามจ่ายไฟ MG996 จากขา 3.3V ของ ESP32 เพราะ MG996 ใช้กระแสสูงและอาจทำให้ ESP32 รีเซ็ต
- ต่อกล้องเข้ากับ Pi 5
- ต่อ ESP32-S3 เข้ากับ Pi 5 ด้วยสาย USB

อย่าทดสอบมอเตอร์โดยยกล้อไม่มั่นคง และควรถอดไฟมอเตอร์ออกก่อนอัปโหลดโค้ดครั้งแรก

## 2. เปิด Pi 5 และเตรียมโปรเจกต์

เปิด Pi 5 ต่อจอ/คีย์บอร์ดหรือ SSH แล้วเปิด Terminal

ตรวจ IP ของ Pi ไว้ก่อน เผื่อใช้เปิดเว็บจากคอมพิวเตอร์เครื่องอื่น:

```bash
hostname -I
```

คัดลอกโฟลเดอร์ `software/pi-transfer` จากโปรเจกต์นี้ไปไว้ใน Pi เช่น:

```bash
mkdir -p ~/meter-controller
```

ถ้าใช้ PowerShell จากคอมพิวเตอร์ที่เก็บโปรเจกต์อยู่ ให้คัดลอกด้วยคำสั่งลักษณะนี้
โดยเปลี่ยน `PI_IP` เป็น IP ของ Pi:

```powershell
scp -r .\software\pi-transfer\* pi@PI_IP:~/meter-controller/
```

จากนั้นกลับมาที่ Terminal ของ Pi:

```bash
cd ~/meter-controller
ls -la
```

ต้องเห็นไฟล์ `requirements.txt`, `app.py` และโฟลเดอร์ `templates`
ถ้าไม่เห็น แปลว่ายังไม่ได้คัดลอกโฟลเดอร์โปรเจกต์ ให้คัดลอกจาก PowerShell
บนคอมด้วยคำสั่งนี้:

```powershell
scp -r "C:\Users\noonu\Desktop\888\software\pi-transfer" noey@meter-pi.local:/home/noey/
```

แล้วกลับมาที่ Pi และรวมไฟล์เข้าโฟลเดอร์ที่ใช้งาน:

```bash
cp -r ~/pi-transfer/. ~/meter-controller/
cd ~/meter-controller
ls -la
```

เมื่อเห็น `requirements.txt` แล้วจึงทำขั้นตอนติดตั้งต่อ

## 3. ติดตั้งโปรแกรมฝั่ง Pi 5

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-opencv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

ถ้าใช้กล้อง CSI ให้ติดตั้งเพิ่ม:

```bash
sudo apt install -y python3-picamera2
```

ถ้าใช้ ESP32 ผ่าน USB Serial ให้เพิ่มสิทธิ์พอร์ต serial แล้ว reboot หนึ่งครั้ง:

```bash
sudo usermod -aG dialout $USER
sudo reboot
```

หลัง Pi เปิดกลับมา ให้เข้าโฟลเดอร์และเปิด environment ใหม่:

```bash
cd ~/meter-controller
source .venv/bin/activate
```

## 4. ตั้งค่าไฟล์ `.env` บน Pi

สร้างไฟล์ตั้งค่าจากตัวอย่าง:

```bash
cp .env.example .env
nano .env
```

### ค่าที่แนะนำสำหรับ USB webcam + USB Serial

ใส่หรือแก้ให้เป็นแบบนี้:

```ini
CAMERA_INDEX=0
CAMERA_BACKEND=opencv
CAMERA_WIDTH=1920
CAMERA_HEIGHT=1080
CAPTURE_DIR=captures
PORT=5000
CONTROLLER_PORT=8765
CONTROLLER_SERIAL_PORT=/dev/ttyACM0
CONTROLLER_SERIAL_BAUD=115200
OCR_ENABLED=false
```

ตรวจชื่อพอร์ต ESP32 ก่อน ถ้าไม่ใช่ `/dev/ttyACM0`:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

### ถ้าใช้กล้อง CSI

เปลี่ยนเป็น:

```ini
CAMERA_BACKEND=picamera2
```

### สำคัญ: Google Drive/Sheets

โค้ดพร้อมส่งรูปขึ้น Google Drive และเพิ่มแถวใน Google Sheets แล้ว
ให้ทำขั้นตอนนี้บน Windows PowerShell ก่อน:

```powershell
scp -r "C:\Users\noonu\Desktop\888\secrets" noey@172.20.10.3:/home/noey/meter-controller/
```

จากนั้นเปิดไฟล์ `.env` บน Pi:

```bash
cd ~/meter-controller
nano .env
```

เปิดใช้และแก้ชื่อไฟล์ให้ตรงกับไฟล์จริงใน `secrets`:

```ini
GOOGLE_OAUTH_CLIENT_FILE=/home/noey/meter-controller/secrets/client_secret_ชื่อไฟล์จริง.json
GOOGLE_OAUTH_TOKEN_FILE=/home/noey/meter-controller/secrets/token.json
GOOGLE_SERVICE_ACCOUNT_FILE=/home/noey/meter-controller/secrets/service-account-ชื่อไฟล์จริง.json
GOOGLE_SHEET_ID=ใส่รหัส Google Sheet
GOOGLE_SHEET_RANGE=ชีต1!A:D
```

ดูชื่อไฟล์จริงบน Pi ด้วย:

```bash
ls -1 ~/meter-controller/secrets
```

ต้องแชร์ Google Sheet ให้กับอีเมลของ Service Account ด้วยสิทธิ์ Editor
และบัญชี Google ที่ใช้ OAuth ต้องมีสิทธิ์อัปโหลดเข้า Drive หากต้องการเก็บในโฟลเดอร์เฉพาะ
ให้ใส่ `GOOGLE_DRIVE_FOLDER_ID` เพิ่มได้ (ไม่ใส่ก็อัปโหลดเข้า Drive หลัก)

ถ้ายังไม่ตั้งค่า Google ระบบจะยังแคปภาพเก็บในโฟลเดอร์ `captures` ได้
แต่ยังไม่อัปโหลด Drive/Sheets

อย่าใส่ path ตัวอย่างอย่าง `C:\path\...` ลงใน Pi เพราะเป็น path ของ Windows

## 5. เปิดโปรแกรมฝั่ง Pi และทดสอบกล้อง

จาก Terminal ของ Pi:

```bash
cd ~/meter-controller
source .venv/bin/activate
python app.py
```

ถ้าเริ่มสำเร็จจะมี Flask ทำงานที่ port 5000 และ controller server ที่ port 8765
เปิดเว็บจากคอมพิวเตอร์หรือโทรศัพท์ที่อยู่เครือข่ายเดียวกับ Pi:

```text
http://PI_IP:5000/
```

เช่น `http://192.168.1.50:5000/`

หน้าเว็บต้องเห็นภาพจากกล้องก่อน จึงค่อยไปขั้นตอนอัปโหลด ESP32

ถ้าต้องการทดสอบ protocol โดยไม่ต่อฮาร์ดแวร์:

```bash
python test_controller.py
```

## 6. เตรียม Arduino IDE บนคอมพิวเตอร์

ติดตั้ง Arduino IDE แล้วเปิดโปรเจกต์ไฟล์นี้:

```text
software/esp32_s3_controller/esp32_s3_controller.ino
```

อย่าใช้ `test.ino` เป็นไฟล์หลัก ไฟล์ที่ต้องอัปโหลดคือ
`esp32_s3_controller.ino`

ใน Arduino IDE ทำตามนี้:

1. เปิด `File > Preferences`
2. เพิ่ม ESP32 Boards Manager URL:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. เพิ่ม Bluepad32 Boards Manager URL:
   `https://raw.githubusercontent.com/ricardoquesada/esp32-arduino-lib-builder/master/bluepad32_files/package_esp32_bluepad32_index.json`
4. เปิด `Tools > Board > Boards Manager`
5. ติดตั้ง `esp32` และ `ESP32 + Bluepad32`
6. เลือกบอร์ดกลุ่ม `ESP32 + Bluepad32` ที่ตรงกับรุ่น ESP32-S3
7. ต่อ ESP32-S3 ด้วย USB แล้วเลือก COM port ที่ถูกต้อง

ขั้นตอนนี้อ้างอิงจากคู่มือ Arduino-ESP32 และ Bluepad32 ทางการ:

- https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html
- https://bluepad32.readthedocs.io/en/latest/plat_arduino/

## 7. ตั้งค่าและอัปโหลดโค้ด ESP32

เปิดไฟล์ `esp32_s3_controller.ino` แล้วตรวจค่าด้านบนของไฟล์:

```cpp
const bool PI_USE_WIFI = false;
```

ใช้ `false` เพราะคู่มือนี้ใช้ USB Serial ต่อ ESP32 เข้ากับ Pi 5

ถ้าใช้ positional servo ให้คงค่า:

```cpp
const bool PAN_SERVO_CONTINUOUS = false;
```

ถ้าเป็น continuous-rotation servo ค่อยเปลี่ยนเป็น `true`

จากนั้นกดปุ่ม **Verify** เพื่อ compile และกด **Upload** เพื่ออัปโหลด
ถ้าอัปโหลดไม่เข้า ให้กดปุ่ม BOOT ค้างไว้ตอนเริ่ม upload แล้วปล่อยเมื่อเห็นว่าเริ่มเขียนไฟล์

เปิด `Tools > Serial Monitor` และตั้ง baud rate เป็น `115200`

## 8. จับคู่จอย Bluetooth

1. เปิดจอยให้อยู่ในโหมด pairing
2. รีเซ็ต ESP32 หรือกดปุ่ม EN
3. ดู Serial Monitor ต้องเห็นข้อความประมาณ `Controller connected`
4. ถ้ายังไม่เจอ ให้ปิด Bluetooth ของอุปกรณ์อื่นที่เคยจับคู่กับจอยก่อน

เมื่อจอยถูกถอด ระบบจะหยุดมอเตอร์และเซอร์โวเพื่อความปลอดภัย

## 9. ทดสอบตามลำดับที่ปลอดภัย

ให้ทดสอบโดยยังไม่จ่ายไฟมอเตอร์ก่อน:

1. เปิด Pi และรัน `python app.py`
2. เปิดหน้าเว็บและตรวจว่ามีภาพสด
3. กดปุ่มซูมเข้าในหน้าเว็บ ตรวจว่าภาพซูมเข้า
4. กดปุ่มซูมออกในหน้าเว็บ ตรวจว่าภาพซูมออก
5. กดปุ่ม `ถ่ายภาพ + บันทึก Drive/Sheets` แล้วตรวจไฟล์ใน `captures/`, Drive และ Sheets
6. ดันสติ๊กขวาขึ้น/ลง ตรวจเซอร์โว pan
7. ยกล้อรถให้พ้นพื้น แล้วจ่ายไฟมอเตอร์
8. ดัน Left stick ขึ้น/ลง ตรวจเดินหน้า/ถอยหลัง
9. ดัน Left stick ซ้าย/ขวา ตรวจหมุน
10. วางรถลงพื้นและทดสอบความเร็วต่ำก่อน

## 10. ตั้งให้ Pi เปิดระบบอัตโนมัติหลัง reboot (แนะนำ)

หลังจากรันทดสอบแบบ manual ผ่านแล้ว ให้ติดตั้ง service:

```bash
sudo cp meter-controller.service.example /etc/systemd/system/meter-controller.service
sudo systemctl daemon-reload
sudo systemctl enable --now meter-controller.service
```

ตรวจสถานะ:

```bash
systemctl status meter-controller.service
```

ดู log แบบต่อเนื่อง:

```bash
journalctl -u meter-controller.service -f
```

ถ้า username ของ Pi ไม่ใช่ `noey` หรือย้ายโฟลเดอร์โปรเจกต์ ให้แก้
`User`, `WorkingDirectory`, `EnvironmentFile` และ `ExecStart` ใน
`meter-controller.service.example` ก่อนติดตั้ง

หยุด service ชั่วคราวได้ด้วย:

```bash
sudo systemctl stop meter-controller.service
```

## 11. การเปิดใช้งานในครั้งถัดไป

### เปิด Pi

```bash
cd ~/meter-controller
source .venv/bin/activate
python app.py
```

### เปิด ESP32

ต่อ USB เข้ากับ Pi แล้วกดปุ่ม EN ถ้าจำเป็น จากนั้นเปิดจอย

### เปิดดูภาพ

```text
http://PI_IP:5000/
```

## 12. ถ้าใช้ Wi-Fi แทน USB Serial

ใน ESP32 เปลี่ยน:

```cpp
const bool PI_USE_WIFI = true;
const char *WIFI_SSID = "ชื่อ Wi-Fi";
const char *WIFI_PASSWORD = "รหัส Wi-Fi";
const char *PI_HOST = "IP ของ Pi 5";
```

ใน `.env` ของ Pi ให้ปล่อย:

```ini
CONTROLLER_SERIAL_PORT=
CONTROLLER_PORT=8765
```

ทั้ง ESP32 และ Pi ต้องอยู่ Wi-Fi เดียวกัน และต้องใช้ IP ของ Pi จริง ห้ามใช้
`localhost` ใน `PI_HOST`

## 13. อาการที่พบบ่อย

| อาการ | ตรวจสอบ |
|---|---|
| เปิดเว็บไม่ได้ | รัน `python app.py`, ตรวจ IP และ port 5000 |
| เว็บเปิดแต่ไม่มีภาพ | ตรวจ `CAMERA_INDEX`, `CAMERA_BACKEND` และสายกล้อง |
| ESP32 ต่อ Pi ไม่ได้ | ตรวจ `PI_USE_WIFI`, `PI_HOST` หรือ `/dev/ttyACM0` |
| จอยไม่เจอ | ตรวจ Bluepad32 board ที่เลือกและ pairing mode |
| มอเตอร์ไม่หมุน | ตรวจ STBY, GND ร่วม, ไฟ VM และ pin ตามตาราง |
| เซอร์โวสั่น/ESP32 รีเซ็ต | ใช้แหล่งจ่ายเซอร์โวแยกและต่อ GND ร่วม |
| กด A แล้วแคปไม่ได้ | ตรวจว่า `captures/` เขียนได้ และปิด Google path ตัวอย่าง |

ถ้าหยุดระบบฉุกเฉิน ให้ปล่อยจอยและถอดไฟมอเตอร์ก่อน แล้วค่อยตรวจสายไฟ
