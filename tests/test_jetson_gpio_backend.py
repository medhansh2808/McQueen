from robot.jetson_nano.mcqueen_edge.jetson_gpio import JetsonDriveBackend


class FakePWM:
    def __init__(self, pin, frequency):
        self.pin = pin
        self.frequency = frequency
        self.started = None
        self.duty = None
        self.stopped = False

    def start(self, duty):
        self.started = float(duty)
        self.duty = float(duty)

    def ChangeDutyCycle(self, duty):
        self.duty = float(duty)

    def stop(self):
        self.stopped = True


class FakeGPIO:
    BOARD = "BOARD"
    OUT = "OUT"
    LOW = 0
    HIGH = 1

    def __init__(self):
        self.mode = None
        self.pin_state = {}
        self.pwms = {}
        self.cleaned = False

    def setmode(self, mode):
        self.mode = mode

    def setup(self, pin, mode, initial=None):
        if initial is not None:
            self.pin_state[pin] = initial

    def output(self, pin, value):
        self.pin_state[pin] = value

    def PWM(self, pin, frequency):
        pwm = FakePWM(pin, frequency)
        self.pwms[pin] = pwm
        return pwm

    def cleanup(self):
        self.cleaned = True


gpio = FakeGPIO()

backend = JetsonDriveBackend(
    servo_left_us=1100,
    servo_center_us=1500,
    servo_right_us=1900,
    gpio_module=gpio,
)

assert gpio.mode == gpio.BOARD

# Startup safe state.
assert gpio.pin_state[29] == gpio.LOW
assert gpio.pin_state[31] == gpio.LOW
assert gpio.pwms[32].duty == 0.0
assert round(gpio.pwms[33].duty, 4) == 7.5

# Full forward + full right.
backend.apply(1000, 1000, True)
assert gpio.pin_state[29] == gpio.HIGH
assert gpio.pin_state[31] == gpio.LOW
assert gpio.pwms[32].duty == 100.0
assert round(gpio.pwms[33].duty, 4) == 9.5

# Half reverse + full left.
backend.apply(-1000, -500, True)
assert gpio.pin_state[29] == gpio.LOW
assert gpio.pin_state[31] == gpio.HIGH
assert gpio.pwms[32].duty == 50.0
assert round(gpio.pwms[33].duty, 4) == 5.5

# Disabled motor stops safely.
backend.apply(0, 900, False)
assert gpio.pin_state[29] == gpio.LOW
assert gpio.pin_state[31] == gpio.LOW
assert gpio.pwms[32].duty == 0.0
assert round(gpio.pwms[33].duty, 4) == 7.5

# Emergency stop centers steering and stops motor.
backend.apply(500, 400, True)
backend.emergency_stop()
assert gpio.pin_state[29] == gpio.LOW
assert gpio.pin_state[31] == gpio.LOW
assert gpio.pwms[32].duty == 0.0
assert round(gpio.pwms[33].duty, 4) == 7.5

backend.close()
assert gpio.pwms[32].stopped is True
assert gpio.pwms[33].stopped is True
assert gpio.cleaned is True
assert backend.closed is True

backend.close()

print("PIN MAP      : AIN1=29 AIN2=31 PWMA=32 SERVO=33")
print("TB6612 STBY  : tied to VCC at Jetson 3.3V")
print("MOTOR PWM    : 1000 Hz")
print("SERVO PWM    : 50 Hz")
print("SAFE STATE   : motor PWM=0, AIN1=0, AIN2=0, servo=center")
print("GPIO BACKEND SELF-TEST : PASS")
