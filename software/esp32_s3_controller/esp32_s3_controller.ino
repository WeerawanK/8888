#include <Bluepad32.h>
#include <ESP32Servo.h>
#include <WiFi.h>

// -------------------- Wi-Fi and Raspberry Pi --------------------
const char *WIFI_SSID = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char *PI_HOST = "192.168.1.100";
const uint16_t PI_PORT = 8765;
// true = Wi-Fi TCP to Pi; false = USB Serial to Pi (Pi listens for PI_CMD lines)
const bool PI_USE_WIFI = false;
// Camera capture and zoom are controlled from the Pi web page.
const bool GAMEPAD_CAMERA_ACTIONS = false;

WiFiClient piClient;
unsigned long lastWifiTryAt = 0;
const unsigned long WIFI_RETRY_MS = 5000;

// -------------------- TB6612FNG motor driver --------------------
const int PWMA = 4;
const int AI1 = 6;
const int AI2 = 5;
const int PWMB = 7;
const int BI1 = 15;
const int BI2 = 16;
const int STBY = 17;

// -------------------- Pan servo --------------------
const int SERVO_PIN = 8;
// false = normal positional servo (recommended for camera pan)
// true  = continuous-rotation servo, moved for a timed step
const bool PAN_SERVO_CONTINUOUS = false;
int servoStopUs = 1500;
const int SERVO_FORWARD_US = 1000;
const int SERVO_REVERSE_US = 2000;
const unsigned long SERVO_STEP_TIME_MS = 120;

// -------------------- Controller settings --------------------
const int DEADZONE = 50;
const int MIN_SPEED = 80;
const int SERVO_STEP_DEGREES = 5;
const int SERVO_MIN_ANGLE = 0;
const int SERVO_MAX_ANGLE = 180;
const unsigned long STATUS_INTERVAL_MS = 5000;

ControllerPtr myController = nullptr;
Servo panServo;

int virtualServoAngle = 90;
int lastLeftSpeed = 0;
int lastRightSpeed = 0;
uint8_t previousDpad = 0;
bool previousA = false;
bool previousX = false;
bool previousB = false;
unsigned long lastStatusAt = 0;

void driveMotors(int leftSpeed, int rightSpeed);

void onConnectedController(ControllerPtr ctl) {
  Serial.println("[GAMEPAD] Controller connected");
  myController = ctl;
  previousDpad = 0;
  previousA = false;
  previousX = false;
  previousB = false;
}

void stopServo() {
  if (PAN_SERVO_CONTINUOUS) {
    panServo.writeMicroseconds(servoStopUs);
  } else {
    panServo.write(virtualServoAngle);
  }
}

void stopRobot() {
  driveMotors(0, 0);
  lastLeftSpeed = 0;
  lastRightSpeed = 0;
  stopServo();
}

void connectToWiFi() {
  if (!PI_USE_WIFI) {
    return;
  }
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (millis() - lastWifiTryAt < WIFI_RETRY_MS) {
    return;
  }

  lastWifiTryAt = millis();
  Serial.printf("[WIFI] Connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

bool sendPiCommand(const char *command) {
  if (!PI_USE_WIFI) {
    Serial.printf("PI_CMD %s\n", command);
    return true;
  }

  connectToWiFi();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[PI] Wi-Fi is not connected");
    return false;
  }

  if (!piClient.connected()) {
    piClient.stop();
    Serial.printf("[PI] Connecting to %s:%u\n", PI_HOST, PI_PORT);
    if (!piClient.connect(PI_HOST, PI_PORT)) {
      Serial.println("[PI] Connection failed");
      return false;
    }
  }

  piClient.println(command);
  piClient.setTimeout(1500);
  String response = piClient.readStringUntil('\n');
  response.trim();

  if (response.startsWith("OK")) {
    Serial.printf("[PI] %s -> %s\n", command, response.c_str());
    return true;
  }

  Serial.printf("[PI] %s -> %s\n", command, response.c_str());
  return false;
}

void readServoCalibration() {
  while (Serial.available() > 0) {
    char command = static_cast<char>(Serial.read());

    if (command == '[') {
      servoStopUs = max(1400, servoStopUs - 5);
      stopServo();
      Serial.printf("[SERVO] stop pulse=%dus\n", servoStopUs);
    } else if (command == ']') {
      servoStopUs = min(1600, servoStopUs + 5);
      stopServo();
      Serial.printf("[SERVO] stop pulse=%dus\n", servoStopUs);
    } else if (command == 's' || command == 'S') {
      Serial.printf(
        "[SERVO] stop pulse=%dus (use [ or ] to adjust)\n",
        servoStopUs
      );
    }
  }
}

void moveServoStep(bool increase) {
  int nextAngle = increase
                    ? virtualServoAngle + SERVO_STEP_DEGREES
                    : virtualServoAngle - SERVO_STEP_DEGREES;
  nextAngle = constrain(nextAngle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);

  if (nextAngle == virtualServoAngle) {
    Serial.printf(
      "[SERVO] Limit reached: virtual angle=%d degrees\n",
      virtualServoAngle
    );
    return;
  }

  if (PAN_SERVO_CONTINUOUS) {
    panServo.writeMicroseconds(
      increase ? SERVO_FORWARD_US : SERVO_REVERSE_US
    );
    delay(SERVO_STEP_TIME_MS);
    stopServo();
  } else {
    panServo.write(nextAngle);
  }
  virtualServoAngle = nextAngle;
  Serial.printf("[SERVO] virtual angle=%d degrees\n", virtualServoAngle);
}

void updateServoFromRightStick(ControllerPtr controller) {
  const int STICK_DEADZONE = 70;
  int rightStickY = -controller->axisRY();
  bool aPressed = controller->a() && !previousA;
  bool bPressed = controller->b() && !previousB;
  bool xPressed = controller->x() && !previousX;

  // When the stick is released, keep the current pan angle.
  if (abs(rightStickY) > STICK_DEADZONE) {
    int targetAngle = map(
      constrain(rightStickY, -512, 512),
      -512,
      512,
      SERVO_MIN_ANGLE,
      SERVO_MAX_ANGLE
    );
    targetAngle = constrain(targetAngle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);

    if (targetAngle != virtualServoAngle) {
      if (PAN_SERVO_CONTINUOUS) {
        panServo.writeMicroseconds(
          rightStickY > 0 ? SERVO_FORWARD_US : SERVO_REVERSE_US
        );
      } else {
        virtualServoAngle = targetAngle;
        panServo.write(virtualServoAngle);
      }
      Serial.printf("[SERVO] right stick pan=%d degrees\n", targetAngle);
    }
  }

  // Match the tested ESP32 gamepad sketch: A=90, X=45, B=135 degrees.
  if (aPressed) {
    virtualServoAngle = 90;
    panServo.write(virtualServoAngle);
    Serial.println("[SERVO] preset A = 90 degrees");
  }
  if (xPressed) {
    virtualServoAngle = 45;
    panServo.write(virtualServoAngle);
    Serial.println("[SERVO] preset X = 45 degrees");
  }
  if (bPressed) {
    virtualServoAngle = 135;
    panServo.write(virtualServoAngle);
    Serial.println("[SERVO] preset B = 135 degrees");
  }

  previousA = controller->a();
  previousB = controller->b();
  previousX = controller->x();
}

void updatePiActions(ControllerPtr controller) {
  bool aPressed = controller->a();
  bool xPressed = controller->x();
  bool bPressed = controller->b();

  if (aPressed && !previousA) {
    sendPiCommand("CAPTURE");
  }
  if (xPressed && !previousX) {
    sendPiCommand("ZOOM 0.5");
  }
  if (bPressed && !previousB) {
    sendPiCommand("ZOOM -0.5");
  }

  previousA = aPressed;
  previousX = xPressed;
  previousB = bPressed;
}

void onDisconnectedController(ControllerPtr ctl) {
  Serial.println("[GAMEPAD] Controller disconnected");

  if (myController == ctl) {
    myController = nullptr;
  }

  stopRobot();
  previousDpad = 0;
  previousA = false;
  previousX = false;
  previousB = false;
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

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("=== ESP32-S3 robot controller ===");
  Serial.println("Left stick = motors; Right stick UP/DOWN = pan");
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
  Serial.println("[MOTOR] TB6612FNG ready");

  panServo.setPeriodHertz(50);
  panServo.attach(SERVO_PIN, 500, 2500);
  if (PAN_SERVO_CONTINUOUS) {
    stopServo();
  } else {
    panServo.write(virtualServoAngle);
  }
  Serial.printf(
    "[SERVO] GPIO %d ready, virtual angle=%d degrees\n",
    SERVO_PIN,
    virtualServoAngle
  );

  BP32.setup(&onConnectedController, &onDisconnectedController);
  Serial.println("[GAMEPAD] Bluepad32 ready; connect the controller");

  if (PI_USE_WIFI) {
    WiFi.mode(WIFI_STA);
    connectToWiFi();
  }
}

void loop() {
  BP32.update();
  readServoCalibration();
  connectToWiFi();

  if (
    myController
    && myController->isConnected()
    && myController->isGamepad()
  ) {
    int rawY = -myController->axisY();
    int rawX = myController->axisX();

    int throttle = abs(rawY) > DEADZONE
                    ? map(rawY, -512, 511, -255, 255)
                    : 0;
    int turn = abs(rawX) > DEADZONE
                 ? map(rawX, -512, 511, -255, 255)
                 : 0;

    int leftSpeed = applyMinSpeed(
      constrain(throttle + turn, -255, 255)
    );
    int rightSpeed = applyMinSpeed(
      constrain(throttle - turn, -255, 255)
    );

    driveMotors(leftSpeed, rightSpeed);
    lastLeftSpeed = leftSpeed;
    lastRightSpeed = rightSpeed;

    updateServoFromRightStick(myController);
    if (GAMEPAD_CAMERA_ACTIONS) {
      updatePiActions(myController);
    }
  } else {
    stopRobot();
    previousDpad = 0;
    previousA = false;
    previousX = false;
    previousB = false;
  }

  if (millis() - lastStatusAt >= STATUS_INTERVAL_MS) {
    Serial.printf(
      "[STATUS] WiFi=%s, Gamepad=%s, left=%d right=%d, "
      "servo=%d, FreeHeap=%u\n",
      WiFi.status() == WL_CONNECTED ? "connected" : "disconnected",
      myController && myController->isConnected()
        ? "connected"
        : "disconnected",
      lastLeftSpeed,
      lastRightSpeed,
      virtualServoAngle,
      ESP.getFreeHeap()
    );
    lastStatusAt = millis();
  }

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
