"""Dependency-free tests for the realtime autonomous contract."""

import time
import unittest

from mcqueen_ml.deployment.protocol import (
    FrameMeta,
    Prediction,
    decode_message,
    encode_message,
    round_trip_latency_ms,
)
from mcqueen_ml.deployment.safety import AutoSafetyGate, SafetyConfig


class RealtimeContractTests(unittest.TestCase):
    def test_protocol_round_trip(self):
        msg = Prediction(
            frame_id=42,
            capture_mono_ns=123456789,
            servo_angle_deg=112.0,
            motor_pwm=-80.0,
            inference_ms=7.5,
            model_id="mcqueen-v0",
            server_sequence=9,
        )
        restored = decode_message(encode_message(msg))
        self.assertEqual(restored, msg)

    def test_latency_uses_jetson_clock_only(self):
        msg = Prediction(
            frame_id=1,
            capture_mono_ns=1_000_000_000,
            servo_angle_deg=90,
            motor_pwm=0,
            inference_ms=4.0,
            model_id="demo",
            server_sequence=1,
        )
        self.assertEqual(round_trip_latency_ms(msg, 1_075_000_000), 75.0)

    def test_remote_prediction_has_no_authority_by_default(self):
        gate = AutoSafetyGate()
        now = time.monotonic_ns()
        pred = Prediction(1, now, 110, 90, 5, "demo", 1)
        cmd = gate.apply(pred, now + 10_000_000)
        self.assertFalse(cmd.auto_active)
        self.assertEqual(cmd.motor_pwm, 0)
        self.assertEqual(cmd.servo_angle_deg, 90)

    def test_caps_and_servo_clamp(self):
        gate = AutoSafetyGate(SafetyConfig(forward_max_pwm=100, reverse_max_pwm=70))
        gate.set_auto_authorized(True)
        now = time.monotonic_ns()
        pred = Prediction(1, now, 140, 255, 5, "demo", 1)
        cmd = gate.apply(pred, now + 20_000_000)
        self.assertTrue(cmd.auto_active)
        self.assertEqual(cmd.servo_angle_deg, 115)
        self.assertEqual(cmd.motor_pwm, 100)

        pred2 = Prediction(2, now, 20, -255, 5, "demo", 2)
        cmd2 = gate.apply(pred2, now + 20_000_000)
        self.assertEqual(cmd2.servo_angle_deg, 45)
        self.assertEqual(cmd2.motor_pwm, -70)

    def test_stale_prediction_cancels_auto(self):
        gate = AutoSafetyGate(SafetyConfig(prediction_timeout_ms=250))
        gate.set_auto_authorized(True)
        now = time.monotonic_ns()
        pred = Prediction(1, now, 100, 50, 5, "demo", 1)
        cmd = gate.apply(pred, now + 300_000_000)
        self.assertFalse(cmd.auto_active)
        self.assertEqual(cmd.motor_pwm, 0)
        self.assertEqual(cmd.servo_angle_deg, 90)
        self.assertFalse(gate.auto_authorized)


if __name__ == "__main__":
    unittest.main()
