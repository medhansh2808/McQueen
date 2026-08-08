"""Real Jetson GPIO/PWM drive backend for McQueen.

Minimal wiring:
- BOARD pin 29 -> TB6612 AIN1
- BOARD pin 31 -> TB6612 AIN2
- BOARD pin 32 -> TB6612 PWMA (motor PWM)
- BOARD pin 33 -> MG995 signal (servo PWM)

TB6612 VCC and STBY are tied together to Jetson 3.3V, matching the proven
previous wiring. STBY is therefore not software-controlled.

Servo calibration values are intentionally required and will be measured on
the real car.
"""


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


class JetsonDriveBackend:
    def __init__(
        self,
        servo_left_us,
        servo_center_us,
        servo_right_us,
        ain1_pin=29,
        ain2_pin=31,
        motor_pwm_pin=32,
        servo_pwm_pin=33,
        motor_pwm_hz=1000,
        servo_pwm_hz=50,
        gpio_module=None,
    ):
        if gpio_module is None:
            try:
                import Jetson.GPIO as gpio_module
            except ImportError:
                raise RuntimeError(
                    "Jetson.GPIO is required only on the real Jetson"
                )

        self.gpio = gpio_module

        self.ain1_pin = int(ain1_pin)
        self.ain2_pin = int(ain2_pin)
        self.motor_pwm_pin = int(motor_pwm_pin)
        self.servo_pwm_pin = int(servo_pwm_pin)

        self.motor_pwm_hz = int(motor_pwm_hz)
        self.servo_pwm_hz = int(servo_pwm_hz)

        self.servo_left_us = int(servo_left_us)
        self.servo_center_us = int(servo_center_us)
        self.servo_right_us = int(servo_right_us)

        self._validate_servo_calibration()

        self.gpio.setmode(self.gpio.BOARD)

        self.gpio.setup(self.ain1_pin, self.gpio.OUT, initial=self.gpio.LOW)
        self.gpio.setup(self.ain2_pin, self.gpio.OUT, initial=self.gpio.LOW)
        self.gpio.setup(self.motor_pwm_pin, self.gpio.OUT)
        self.gpio.setup(self.servo_pwm_pin, self.gpio.OUT)

        self.motor_pwm = self.gpio.PWM(self.motor_pwm_pin, self.motor_pwm_hz)
        self.servo_pwm = self.gpio.PWM(self.servo_pwm_pin, self.servo_pwm_hz)

        self.motor_pwm.start(0.0)
        self.servo_pwm.start(self._pulse_to_duty(self.servo_center_us))

        self.closed = False

    def _validate_servo_calibration(self):
        values = (
            self.servo_left_us,
            self.servo_center_us,
            self.servo_right_us,
        )

        if min(values) <= 0:
            raise ValueError("Servo pulse widths must be positive")

        if self.servo_left_us == self.servo_center_us:
            raise ValueError("Servo left pulse must differ from center")

        if self.servo_right_us == self.servo_center_us:
            raise ValueError("Servo right pulse must differ from center")

    def _pulse_to_duty(self, pulse_us):
        period_us = 1000000.0 / float(self.servo_pwm_hz)
        return (float(pulse_us) / period_us) * 100.0

    def _steering_pulse_us(self, steering):
        steering = _clamp(int(steering), -1000, 1000)

        if steering < 0:
            fraction = abs(steering) / 1000.0
            return self.servo_center_us + (
                self.servo_left_us - self.servo_center_us
            ) * fraction

        fraction = steering / 1000.0
        return self.servo_center_us + (
            self.servo_right_us - self.servo_center_us
        ) * fraction

    def _stop_motor(self):
        self.motor_pwm.ChangeDutyCycle(0.0)
        self.gpio.output(self.ain1_pin, self.gpio.LOW)
        self.gpio.output(self.ain2_pin, self.gpio.LOW)

    def apply(self, steering, throttle, motor_enabled):
        steering = _clamp(int(steering), -1000, 1000)
        throttle = _clamp(int(throttle), -1000, 1000)

        servo_pulse = self._steering_pulse_us(steering)
        self.servo_pwm.ChangeDutyCycle(self._pulse_to_duty(servo_pulse))

        if not motor_enabled or throttle == 0:
            self._stop_motor()
            return

        if throttle > 0:
            self.gpio.output(self.ain1_pin, self.gpio.HIGH)
            self.gpio.output(self.ain2_pin, self.gpio.LOW)
        else:
            self.gpio.output(self.ain1_pin, self.gpio.LOW)
            self.gpio.output(self.ain2_pin, self.gpio.HIGH)

        duty = (abs(throttle) / 1000.0) * 100.0
        self.motor_pwm.ChangeDutyCycle(duty)

    def emergency_stop(self):
        self._stop_motor()
        self.servo_pwm.ChangeDutyCycle(
            self._pulse_to_duty(self.servo_center_us)
        )

    def close(self):
        if self.closed:
            return

        self.emergency_stop()
        self.motor_pwm.stop()
        self.servo_pwm.stop()
        self.gpio.cleanup()
        self.closed = True
