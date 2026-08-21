"""GPIO wheel-encoder source for McQueen (Jetson Nano).

Python 3.6 compatible. Implements the same snapshot() contract as
encoder_source.py (left/right ticks_total/delta/per_s, encoder_valid,
sample_dt_s) using a physical quadrature encoder on Jetson GPIO pins.

Single-motor drivetrain: one physical encoder drives BOTH rear wheels, so
left and right report the same value (signed; reversing counts negative).

Hardware notes (JGA25-370, 6 wires):
- 2 wires = motor power (12 V class) -- NEVER on the encoder
- 4 wires = hall quadrature encoder: VCC (3.3-5 V), GND, A, B
- Wire colors vary by vendor; verify VCC/GND/A/B at the bench (see
  docs/ENCODER_BENCH.md) before powering.

Direction convention: configurable. count_direction=+1 means a rising
edge on A while B is HIGH increments (adjust with --invert-dir /
swapped pins at the bench).
"""

import threading
import time


def _mono_ns():
    return int(time.monotonic() * 1000000000)


class GpioEncoderSource(object):
    """Quadrature counter on two GPIO pins, edge-driven via Jetson.GPIO.

    A and B are read at every A/B edge (BOTH-edge events on both pins);
    direction comes from the phase of the other pin at each edge.
    The counter is signed and thread-safe.
    """

    def __init__(self, pin_a, pin_b, count_direction=1):
        self.pin_a = int(pin_a)
        self.pin_b = int(pin_b)
        self.count_direction = int(count_direction)
        self._lock = threading.Lock()
        self._total = 0
        self._previous_ns = None
        self._previous_total = 0
        self._gpio = None
        self._started = False

    # -- lifecycle -------------------------------------------------

    def start(self):
        if self._started:
            return
        try:
            import Jetson.GPIO as GPIO
        except ImportError as exc:
            raise RuntimeError(
                "Jetson.GPIO not importable (run on the Jetson): %s" % exc
            )
        self._gpio = GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin_a, GPIO.BOTH, callback=self._on_edge)
        GPIO.add_event_detect(self.pin_b, GPIO.BOTH, callback=self._on_edge)
        self._started = True

    def stop(self):
        if not self._started:
            return
        self._gpio.remove_event_detect(self.pin_a)
        self._gpio.remove_event_detect(self.pin_b)
        self._gpio.cleanup(self.pin_a)
        self._gpio.cleanup(self.pin_b)
        self._started = False

    # -- counting ---------------------------------------------------

    def _on_edge(self, channel):
        gpio = self._gpio
        if channel == self.pin_a:
            other = gpio.input(self.pin_b)
        else:
            other = gpio.input(self.pin_a)
        step = self.count_direction if other else -self.count_direction
        with self._lock:
            self._total += step

    # -- contract ---------------------------------------------------

    def snapshot(self, capture_monotonic_ns):
        now_ns = int(capture_monotonic_ns)
        with self._lock:
            total = self._total
        if self._previous_ns is None:
            dt_s = 0.0
            delta = 0
            rate = 0.0
        else:
            dt_s = max(0.0, (now_ns - self._previous_ns) / 1000000000.0)
            delta = total - self._previous_total
            rate = delta / dt_s if dt_s > 0 else 0.0

        self._previous_ns = now_ns
        self._previous_total = total

        return {
            "encoder_valid": True,
            "left_ticks_total": int(total),
            "right_ticks_total": int(total),
            "left_ticks_delta": int(delta),
            "right_ticks_delta": int(delta),
            "left_ticks_per_s": float(rate),
            "right_ticks_per_s": float(rate),
            "sample_dt_s": float(dt_s),
        }