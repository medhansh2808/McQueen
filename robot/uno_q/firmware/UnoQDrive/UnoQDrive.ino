#include <Arduino_RouterBridge.h>
#include <Servo.h>

// McQueen UNO Q real-time motor + steering firmware.
// D7  -> TB6612 AIN1
// D8  -> TB6612 AIN2
// D9  -> TB6612 PWMA (software PWM)
// D10 -> steering servo signal

static constexpr uint8_t MOTOR_IN1_PIN = D7;
static constexpr uint8_t MOTOR_IN2_PIN = D8;
static constexpr uint8_t MOTOR_PWM_PIN = D9;
static constexpr uint8_t SERVO_PIN = D10;

static constexpr int LEFT_ANGLE = 45;
static constexpr int CENTER_ANGLE = 80;
static constexpr int RIGHT_ANGLE = 115;
static constexpr bool REVERSE_STEERING = true;
static constexpr bool REVERSE_MOTOR = false;

static constexpr int MAX_COMMAND = 1000;
static constexpr int MAX_MOTOR_PWM = 255;
static constexpr int STEERING_DEADBAND = 30;
static constexpr int THROTTLE_STEP = 25;
static constexpr int SERVO_STEP_DEGREES = 1;
static constexpr uint32_t MOTOR_UPDATE_MS = 10;
static constexpr uint32_t SERVO_UPDATE_MS = 5;
static constexpr uint32_t SERVO_RELEASE_MS = 500;
static constexpr uint32_t DIRECTION_PAUSE_MS = 200;
static constexpr uint32_t FAILSAFE_MS = 300;
static constexpr uint32_t MOTOR_PWM_PERIOD_US = 1000;

Servo steeringServo;

volatile int requestedSteering = 0;
volatile int requestedThrottle = 0;
volatile bool requestedMotorEnabled = false;
volatile uint32_t lastCommandMs = 0;

int actualSteeringAngle = CENTER_ANGLE;
int actualThrottle = 0;
int motorDuty = 0;

bool directionPause = false;
uint32_t directionPauseStartedMs = 0;
uint32_t lastServoUpdateMs = 0;
uint32_t lastMotorUpdateMs = 0;
uint32_t servoAtTargetSinceMs = 0;
bool pwmPinState = false;

static int clampInt(int value, int minimum, int maximum) {
  if (value < minimum) return minimum;
  if (value > maximum) return maximum;
  return value;
}

static bool isFailsafeActive(uint32_t nowMs) {
  return lastCommandMs == 0 ||
      static_cast<uint32_t>(nowMs - lastCommandMs) > FAILSAFE_MS;
}

static int moveTowards(int current, int target, int step) {
  if (current < target) {
    current += step;
    if (current > target) current = target;
  } else if (current > target) {
    current -= step;
    if (current < target) current = target;
  }
  return current;
}

static int commandToServoAngle(int steering) {
  steering = clampInt(steering, -MAX_COMMAND, MAX_COMMAND);
  if (REVERSE_STEERING) steering = -steering;

  if (steering < 0) {
    return LEFT_ANGLE +
        ((steering + MAX_COMMAND) * (CENTER_ANGLE - LEFT_ANGLE)) /
        MAX_COMMAND;
  }

  return CENTER_ANGLE +
      (steering * (RIGHT_ANGLE - CENTER_ANGLE)) /
      MAX_COMMAND;
}

static void setMotorDirectionAndDuty(int throttle) {
  throttle = clampInt(throttle, -MAX_COMMAND, MAX_COMMAND);
  if (REVERSE_MOTOR) throttle = -throttle;

  motorDuty = (abs(throttle) * MAX_MOTOR_PWM) / MAX_COMMAND;

  if (throttle > 0) {
    digitalWrite(MOTOR_IN1_PIN, HIGH);
    digitalWrite(MOTOR_IN2_PIN, LOW);
  } else if (throttle < 0) {
    digitalWrite(MOTOR_IN1_PIN, LOW);
    digitalWrite(MOTOR_IN2_PIN, HIGH);
  } else {
    motorDuty = 0;
    digitalWrite(MOTOR_PWM_PIN, LOW);
    digitalWrite(MOTOR_IN1_PIN, LOW);
    digitalWrite(MOTOR_IN2_PIN, LOW);
    pwmPinState = false;
  }
}

static void updateMotorSoftwarePwm() {
  if (motorDuty <= 0) {
    if (pwmPinState) {
      digitalWrite(MOTOR_PWM_PIN, LOW);
      pwmPinState = false;
    }
    return;
  }

  if (motorDuty >= MAX_MOTOR_PWM) {
    if (!pwmPinState) {
      digitalWrite(MOTOR_PWM_PIN, HIGH);
      pwmPinState = true;
    }
    return;
  }

  const uint32_t phaseUs = micros() % MOTOR_PWM_PERIOD_US;
  const uint32_t onTimeUs =
      (static_cast<uint32_t>(motorDuty) * MOTOR_PWM_PERIOD_US) /
      MAX_MOTOR_PWM;
  const bool shouldBeHigh = phaseUs < onTimeUs;

  if (shouldBeHigh != pwmPinState) {
    digitalWrite(MOTOR_PWM_PIN, shouldBeHigh ? HIGH : LOW);
    pwmPinState = shouldBeHigh;
  }
}

int setDrive(int steering, int throttle, int motorEnabled) {
  requestedSteering = clampInt(steering, -MAX_COMMAND, MAX_COMMAND);
  if (abs(requestedSteering) <= STEERING_DEADBAND) requestedSteering = 0;

  requestedThrottle = clampInt(throttle, -MAX_COMMAND, MAX_COMMAND);
  requestedMotorEnabled = (motorEnabled != 0) || (requestedThrottle != 0);
  lastCommandMs = millis();
  return 1;
}

int emergencyStop() {
  requestedSteering = 0;
  requestedThrottle = 0;
  requestedMotorEnabled = false;
  lastCommandMs = 0;
  return 1;
}

int bridgePing() { return 20260801; }
int getActualThrottle() { return actualThrottle; }

int getMotorPwm() {
  if (actualThrottle < 0) return -motorDuty;
  if (actualThrottle > 0) return motorDuty;
  return 0;
}

int getServoAngle() { return actualSteeringAngle; }

int getRequestedSteering() {
  if (isFailsafeActive(millis())) return 0;
  return requestedSteering;
}

int getRequestedThrottle() {
  if (isFailsafeActive(millis())) return 0;
  return requestedMotorEnabled ? requestedThrottle : 0;
}

void setup() {
  pinMode(MOTOR_IN1_PIN, OUTPUT);
  pinMode(MOTOR_IN2_PIN, OUTPUT);
  pinMode(MOTOR_PWM_PIN, OUTPUT);

  digitalWrite(MOTOR_IN1_PIN, LOW);
  digitalWrite(MOTOR_IN2_PIN, LOW);
  digitalWrite(MOTOR_PWM_PIN, LOW);

  steeringServo.attach(SERVO_PIN, 1000, 2000);
  steeringServo.write(CENTER_ANGLE);
  servoAtTargetSinceMs = millis();

  Bridge.begin();
  Bridge.provide("set_drive", setDrive);
  Bridge.provide("estop", emergencyStop);
  Bridge.provide("ping", bridgePing);
  Bridge.provide("get_actual_throttle", getActualThrottle);
  Bridge.provide("get_motor_pwm", getMotorPwm);
  Bridge.provide("get_servo_angle", getServoAngle);
  Bridge.provide("get_requested_steering", getRequestedSteering);
  Bridge.provide("get_requested_throttle", getRequestedThrottle);

  lastServoUpdateMs = millis();
  lastMotorUpdateMs = millis();
}

void loop() {
  const uint32_t nowMs = millis();

  int targetSteering = requestedSteering;
  int targetThrottle = requestedMotorEnabled ? requestedThrottle : 0;

  if (isFailsafeActive(nowMs)) {
    targetSteering = 0;
    targetThrottle = 0;
  }

  if (static_cast<uint32_t>(nowMs - lastServoUpdateMs) >= SERVO_UPDATE_MS) {
    lastServoUpdateMs = nowMs;
    const int targetAngle = commandToServoAngle(targetSteering);
    const int nextAngle = moveTowards(
        actualSteeringAngle,
        targetAngle,
        SERVO_STEP_DEGREES);

    if (nextAngle != actualSteeringAngle) {
      if (!steeringServo.attached()) {
        steeringServo.attach(SERVO_PIN, 1000, 2000);
      }
      actualSteeringAngle = nextAngle;
      steeringServo.write(actualSteeringAngle);
      servoAtTargetSinceMs = nowMs;
    } else if (targetAngle == CENTER_ANGLE) {
      if (steeringServo.attached() &&
          static_cast<uint32_t>(nowMs - servoAtTargetSinceMs) >=
              SERVO_RELEASE_MS) {
        steeringServo.detach();
      }
    } else {
      // Hold a non-centre command under load.
      servoAtTargetSinceMs = nowMs;
    }
  }

  if (static_cast<uint32_t>(nowMs - lastMotorUpdateMs) >= MOTOR_UPDATE_MS) {
    lastMotorUpdateMs = nowMs;

    if (directionPause) {
      actualThrottle = 0;
      setMotorDirectionAndDuty(0);
      if (static_cast<uint32_t>(nowMs - directionPauseStartedMs) >=
          DIRECTION_PAUSE_MS) {
        directionPause = false;
      }
    } else {
      const bool changingDirection =
          (actualThrottle > 0 && targetThrottle < 0) ||
          (actualThrottle < 0 && targetThrottle > 0);
      const int rampTarget = changingDirection ? 0 : targetThrottle;
      actualThrottle = moveTowards(actualThrottle, rampTarget, THROTTLE_STEP);
      setMotorDirectionAndDuty(actualThrottle);

      if (changingDirection && actualThrottle == 0) {
        directionPause = true;
        directionPauseStartedMs = nowMs;
        setMotorDirectionAndDuty(0);
      }
    }
  }

  updateMotorSoftwarePwm();
}
