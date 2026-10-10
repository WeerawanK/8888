#include <Bluepad32.h>

ControllerPtr controller = nullptr;
// ใช้ true ในการจับคู่ครั้งแรก ถ้าจับคู่ได้แล้วให้เปลี่ยนเป็น false
const bool FORGET_BLUETOOTH_KEYS_ON_BOOT = true;
unsigned long lastPrintAt = 0;
unsigned long lastWaitingAt = 0;

void onConnectedController(ControllerPtr ctl) {
  controller = ctl;
  Serial.println("Controller connected!");
}

void onDisconnectedController(ControllerPtr ctl) {
  if (controller == ctl) {
    controller = nullptr;
  }
  Serial.println("Controller disconnected");
}

void printControllerState() {
  if (controller == nullptr || !controller->isConnected()) {
    if (millis() - lastWaitingAt >= 2000) {
      Serial.println("[GAMEPAD] Waiting for controller...");
      lastWaitingAt = millis();
    }
    return;
  }

  if (millis() - lastPrintAt < 200) {
    return;
  }
  lastPrintAt = millis();

  Serial.printf(
    "LX:%d LY:%d RX:%d RY:%d | A:%d B:%d X:%d Y:%d | LT:%d RT:%d\n",
    controller->axisX(),
    controller->axisY(),
    controller->axisRX(),
    controller->axisRY(),
    controller->a(),
    controller->b(),
    controller->x(),
    controller->y(),
    controller->brake(),
    controller->throttle()
  );
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("=== ESP32 gamepad test ===");
  Serial.println("Pair a Bluetooth controller and move the sticks/buttons");

  BP32.setup(&onConnectedController, &onDisconnectedController);
  if (FORGET_BLUETOOTH_KEYS_ON_BOOT) {
    BP32.forgetBluetoothKeys();
    Serial.println("[GAMEPAD] Pairing keys cleared; pair the controller now");
  }
}

void loop() {
  BP32.update();
  printControllerState();
  delay(10);
}
