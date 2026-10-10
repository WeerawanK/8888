#include <Bluepad32.h>
#include <ESP32Servo.h>

// -------------------- MG996 servo --------------------
const int SERVO_PIN = 8;
const int SERVO_START_ANGLE = 90;
const int SERVO_STEP_DEGREES = 5;
const int SERVO_MIN_ANGLE = 0;
const int SERVO_MAX_ANGLE = 180;
const bool RUN_STARTUP_SWEEP = true;

Servo testServo;
int servoAngle = SERVO_START_ANGLE;

// -------------------- TB6612FNG motors --------------------
// ใช้ wiring เดียวกับโค้ดมอเตอร์ที่ทดสอบแล้ว
const int PWMA = 4;
const int AI1 = 6;
const int AI2 = 5;
const int PWMB = 7;
const int BI1 = 15;
const int BI2 = 16;
const int STBY = 17;
const int DEADZONE = 50;
const int MIN_SPEED = 80;

// -------------------- Gamepad --------------------
ControllerPtr myController = nullptr;
const bool FORGET_BLUETOOTH_KEYS_ON_BOOT = true;
bool previousA = false;
bool previousB = false;
bool previousX = false;
unsigned long lastStatePrintAt = 0;

void driveMotors(int leftSpeed, int rightSpeed);

void setServoAngle(int angle) {
  servoAngle = constrain(angle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
  testServo.write(servoAngle);
  Serial.printf("[SERVO] angle=%d degrees\n", servoAngle);
}

void startupSweep() {
  setServoAngle(0);
  delay(1000);
  setServoAngle(90);
  delay(1000);
  setServoAngle(180);
  delay(1000);
  setServoAngle(SERVO_START_ANGLE);
  delay(500);
}

void moveServoStep(bool up) {
  int nextAngle = up
                    ? servoAngle + SERVO_STEP_DEGREES
                    : servoAngle - SERVO_STEP_DEGREES;
  setServoAngle(nextAngle);
}

void onConnectedController(ControllerPtr ctl) {
  myController = ctl;
  previousA = false;
  previousB = false;
  previousX = false;
  Serial.println("Controller connected!");
}

void onDisconnectedController(ControllerPtr ctl) {
  if (myController == ctl) {
    myController = nullptr;
  }
  previousA = false;
  previousB = false;
  previousX = false;
  driveMotors(0, 0);
  Serial.println("Controller disconnected");
}

int applyMinSpeed(int speed) {
  if (speed > 0) {
    return map(speed, 1, 255, MIN_SPEED, 255);
  }
  if (speed < 0) {
    return map(speed, -255, -1, -255, -MIN_SPEED);
  }
  return 0;
}

void updateMotorsFromGamepad() {
  if (myController == nullptr || !myController->isConnected()) {
    driveMotors(0, 0);
    return;
  }

  int rawY = -myController->axisY();
  int rawX = myController->axisX();
  int throttle = abs(rawY) > DEADZONE
                   ? map(rawY, -512, 511, -255, 255)
                   : 0;
  int turn = abs(rawX) > DEADZONE
               ? map(rawX, -512, 511, -255, 255)
               : 0;

  int leftSpeed = applyMinSpeed(constrain(throttle + turn, -255, 255));
  int rightSpeed = applyMinSpeed(constrain(throttle - turn, -255, 255));
  driveMotors(leftSpeed, rightSpeed);
}

void updateServoFromGamepad() {
  if (myController == nullptr || !myController->isConnected()) {
    return;
  }

  bool aPressed = myController->a() && !previousA;
  bool bPressed = myController->b() && !previousB;
  bool xPressed = myController->x() && !previousX;

  // Right stick ขึ้น/ลงควบคุมมุมเซอร์โวโดยตรง
  // แกนขึ้นของจอยมักเป็นค่าติดลบ จึงกลับเครื่องหมายก่อน map
  int rightStickY = -myController->axisRY();
  const int STICK_DEADZONE = 70;
  if (abs(rightStickY) > STICK_DEADZONE) {
    int targetAngle = map(
      constrain(rightStickY, -512, 512),
      -512,
      512,
      SERVO_MIN_ANGLE,
      SERVO_MAX_ANGLE
    );
    if (targetAngle != servoAngle) {
      setServoAngle(targetAngle);
    }
  }

  if (aPressed) {
    setServoAngle(90);
  }
  if (bPressed) {
    setServoAngle(135);
  }
  if (xPressed) {
    setServoAngle(45);
  }

  previousA = myController->a();
  previousB = myController->b();
  previousX = myController->x();
}

void printGamepadState() {
  if (myController == nullptr || !myController->isConnected()) {
    return;
  }
  if (millis() - lastStatePrintAt < 200) {
    return;
  }
  lastStatePrintAt = millis();

  Serial.printf(
    "LX:%d LY:%d RX:%d RY:%d | A:%d B:%d X:%d Y:%d | "
    "LT:%d RT:%d | SERVO:%d\n",
    myController->axisX(),
    myController->axisY(),
    myController->axisRX(),
    myController->axisRY(),
    myController->a(),
    myController->b(),
    myController->x(),
    myController->y(),
    myController->brake(),
    myController->throttle(),
    servoAngle
  );
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("=== MG996 servo + gamepad test ===");
  Serial.println("Right stick UP/DOWN: control servo angle");
  Serial.println("A=90 degrees, X=45 degrees, B=135 degrees");

  pinMode(PWMA, OUTPUT);
  pinMode(AI1, OUTPUT);
  pinMode(AI2, OUTPUT);
  pinMode(PWMB, OUTPUT);
  pinMode(BI1, OUTPUT);
  pinMode(BI2, OUTPUT);
  pinMode(STBY, OUTPUT);
  digitalWrite(STBY, HIGH);
  driveMotors(0, 0);
  Serial.println("[MOTOR] TB6612FNG ready; PWMA=GPIO4");

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  testServo.setPeriodHertz(50);
  testServo.attach(SERVO_PIN, 500, 2500);

  if (RUN_STARTUP_SWEEP) {
    startupSweep();
  } else {
    setServoAngle(SERVO_START_ANGLE);
  }

  BP32.setup(&onConnectedController, &onDisconnectedController);
  if (FORGET_BLUETOOTH_KEYS_ON_BOOT) {
    BP32.forgetBluetoothKeys();
    Serial.println("Pairing keys cleared; pair the controller now");
  }
}

void loop() {
  BP32.update();
  updateMotorsFromGamepad();
  updateServoFromGamepad();
  printGamepadState();
  delay(20);
}

void driveMotors(int leftSpeed, int rightSpeed) {
  digitalWrite(AI1, leftSpeed > 0 ? HIGH : LOW);
  digitalWrite(AI2, leftSpeed < 0 ? HIGH : LOW);
  analogWrite(PWMA, abs(leftSpeed));

  digitalWrite(BI1, rightSpeed > 0 ? HIGH : LOW);
  digitalWrite(BI2, rightSpeed < 0 ? HIGH : LOW);
  analogWrite(PWMB, abs(rightSpeed));
}
