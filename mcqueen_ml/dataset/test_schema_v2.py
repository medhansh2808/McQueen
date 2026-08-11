import unittest

from mcqueen_ml.dataset.schema_v2 import (
    SCHEMA_VERSION,
    validate_frame,
    validate_sequence,
)


def frame(index, mono):
    return {
        "schema_version": SCHEMA_VERSION,
        "frame_index": index,
        "capture_monotonic_ns": mono,
        "timestamp_unix_s": 1234.5,

        "observation.images.front_rgb":
            "rgb/frame_{:06d}.jpg".format(index),

        "action.servo_angle_deg": 90,
        "action.motor_pwm": 0,

        "observation.wheels.encoder_valid": True,
        "observation.wheels.left_ticks_total": index * 5,
        "observation.wheels.right_ticks_total": index * 5,
        "observation.wheels.left_ticks_delta": 5,
        "observation.wheels.right_ticks_delta": 5,
        "observation.wheels.left_ticks_per_s": 50.0,
        "observation.wheels.right_ticks_per_s": 50.0,
        "observation.wheels.sample_dt_s": 0.1,

        "mcqueen.raw.steering_command": 0,
        "mcqueen.raw.throttle_command": 0,
        "mcqueen.raw.motor_enabled": True,
    }


class DatasetSchemaV2Tests(unittest.TestCase):
    def test_valid_frame(self):
        self.assertEqual(validate_frame(frame(0, 1_000_000_000)), [])

    def test_valid_sequence(self):
        rows = [
            frame(0, 1_000_000_000),
            frame(1, 1_100_000_000),
            frame(2, 1_200_000_000),
        ]
        self.assertEqual(validate_sequence(rows), [])

    def test_rejects_non_monotonic_time(self):
        rows = [
            frame(0, 1_000_000_000),
            frame(1, 900_000_000),
        ]
        self.assertTrue(validate_sequence(rows))

    def test_rejects_bad_servo(self):
        row = frame(0, 1_000_000_000)
        row["action.servo_angle_deg"] = 150
        self.assertTrue(validate_frame(row))


if __name__ == "__main__":
    unittest.main()
