import unittest

from mcqueen_ml.dataset.schema_v2 import validate_frame
from robot.jetson_nano.mcqueen_edge.encoder_source import (
    NullEncoderSource,
    SyntheticEncoderSource,
)
from robot.jetson_nano.mcqueen_edge.record_row import build_frame_row


DRIVE = {
    "steering": 0,
    "throttle": 250,
    "motor_enabled": True,
}


class EncoderAndRowTests(unittest.TestCase):

    def test_null_encoder_is_explicitly_invalid(self):
        source = NullEncoderSource()
        value = source.snapshot(1_000_000_000)

        self.assertFalse(value["encoder_valid"])
        self.assertEqual(value["left_ticks_total"], 0)
        self.assertEqual(value["right_ticks_total"], 0)

    def test_synthetic_encoder_rates(self):
        source = SyntheticEncoderSource()

        first = source.snapshot(1_000_000_000)
        self.assertTrue(first["encoder_valid"])

        source.advance(12, 10)
        second = source.snapshot(1_100_000_000)

        self.assertEqual(second["left_ticks_delta"], 12)
        self.assertEqual(second["right_ticks_delta"], 10)
        self.assertAlmostEqual(
            second["left_ticks_per_s"], 120.0, places=3
        )
        self.assertAlmostEqual(
            second["right_ticks_per_s"], 100.0, places=3
        )

    def test_generated_row_matches_v2_contract(self):
        source = SyntheticEncoderSource()
        source.snapshot(1_000_000_000)
        source.advance(5, 6)
        enc = source.snapshot(1_100_000_000)

        row = build_frame_row(
            frame_index=7,
            relative_rgb_path="rgb/frame_000007.jpg",
            capture_monotonic_ns=1_100_000_000,
            timestamp_unix_s=1700000000.0,
            servo_angle_deg=90,
            motor_pwm=64,
            drive_state=DRIVE,
            encoder=enc,
        )

        self.assertEqual(validate_frame(row), [])
        self.assertEqual(
            row["observation.wheels.left_ticks_delta"], 5
        )
        self.assertEqual(
            row["observation.wheels.right_ticks_delta"], 6
        )


if __name__ == "__main__":
    unittest.main()
