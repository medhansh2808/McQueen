"""Wheel encoder observation interface for McQueen.

Python 3.6 compatible.

The actual GPIO implementation is added after we verify tomorrow:
- encoder electrical levels
- A/B channel wiring
- selected Jetson GPIO pins
- direction convention

Until then NullEncoderSource keeps the recorder safe and explicit.
"""


def empty_encoder_observation():
    return {
        "encoder_valid": False,
        "left_ticks_total": 0,
        "right_ticks_total": 0,
        "left_ticks_delta": 0,
        "right_ticks_delta": 0,
        "left_ticks_per_s": 0.0,
        "right_ticks_per_s": 0.0,
        "sample_dt_s": 0.0,
    }


class NullEncoderSource(object):
    """Encoder source used when physical encoders are unavailable."""

    def snapshot(self, capture_monotonic_ns):
        del capture_monotonic_ns
        return empty_encoder_observation()


class SyntheticEncoderSource(object):
    """Dependency-free source for tests; never used for real driving."""

    def __init__(self):
        self.left_total = 0
        self.right_total = 0
        self.previous_ns = None
        self.previous_left = 0
        self.previous_right = 0

    def advance(self, left_ticks, right_ticks):
        self.left_total += int(left_ticks)
        self.right_total += int(right_ticks)

    def snapshot(self, capture_monotonic_ns):
        now_ns = int(capture_monotonic_ns)

        if self.previous_ns is None:
            dt_s = 0.0
            left_delta = 0
            right_delta = 0
            left_rate = 0.0
            right_rate = 0.0
        else:
            dt_s = max(
                0.0,
                (now_ns - self.previous_ns) / 1000000000.0,
            )
            left_delta = self.left_total - self.previous_left
            right_delta = self.right_total - self.previous_right

            if dt_s > 0:
                left_rate = left_delta / dt_s
                right_rate = right_delta / dt_s
            else:
                left_rate = 0.0
                right_rate = 0.0

        result = {
            "encoder_valid": True,
            "left_ticks_total": int(self.left_total),
            "right_ticks_total": int(self.right_total),
            "left_ticks_delta": int(left_delta),
            "right_ticks_delta": int(right_delta),
            "left_ticks_per_s": float(left_rate),
            "right_ticks_per_s": float(right_rate),
            "sample_dt_s": float(dt_s),
        }

        self.previous_ns = now_ns
        self.previous_left = self.left_total
        self.previous_right = self.right_total

        return result
