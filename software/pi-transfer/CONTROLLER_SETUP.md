# ESP32-S3 controller setup

สำหรับการเริ่มตั้งแต่เปิดเครื่อง แนะนำอ่าน [START_HERE_TH.md](START_HERE_TH.md)
ก่อน ส่วนหน้านี้เป็นสรุปการตั้งค่าอ้างอิง

The default transport is Wi-Fi, so the ESP32-S3 and Raspberry Pi 5 must be on
the same Wi-Fi network. USB Serial is also supported when the ESP32 is directly
connected to the Pi 5.

1. Copy `..\esp32_s3_controller\esp32_s3_controller.ino` into Arduino IDE.
2. Install the **Bluepad32** board package/library and select the correct ESP32-S3 board.
3. Set `WIFI_SSID`, `WIFI_PASSWORD`, and `PI_HOST` in the sketch. `PI_HOST` is the
   Raspberry Pi 5 LAN address, not `localhost`.
4. Upload the sketch. The motor pins and TB6612FNG wiring remain the same as the
   original sketch.
5. On the Pi 5, set `CONTROLLER_PORT=8765` in `.env` (the default) and start
   `app.py`. Allow TCP port 8765 through the Pi firewall if enabled.

For USB Serial instead, set `PI_USE_WIFI = false` in the sketch and set
`CONTROLLER_SERIAL_PORT=/dev/ttyACM0` in the Pi `.env`. Keep the baud rate at
115200 unless you change it in both places.

The existing live view remains available at `http://<pi-address>:5000/`.
Use the Pi web page for camera controls:

- Left stick: drive and turn the motors locally on the ESP32.
- Web page: capture the current frame and zoom in/out.
- Right stick up/down: pan the MG996 on ESP32 GPIO 8.

The zoom range is 1.0x to 4.0x and is applied to both the live stream and saved
captures. The default sketch uses a positional MG996 servo from 0 to 180 degrees in
The current main sketch maps the right stick Y axis to the positional pan angle
and holds the angle when the stick is released. For a continuous-rotation servo, set
`PAN_SERVO_CONTINUOUS` to `true` in the Arduino sketch. The sketch keeps
`GAMEPAD_CAMERA_ACTIONS = false`, so A/X/B do not send camera commands.

The servo signal wire goes to GPIO 8. Power the servo from a suitable 5 V
supply and connect that supply's ground to ESP32 GND; do not power a
high-current servo from the ESP32 3.3 V pin.
