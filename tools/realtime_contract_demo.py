#!/usr/bin/env python3
"""Show the realtime message/safety contract without WebRTC or hardware."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow direct execution as:
#   python3 tools/realtime_contract_demo.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcqueen_ml.deployment.protocol import (
    Prediction,
    encode_message,
    round_trip_latency_ms,
)
from mcqueen_ml.deployment.safety import AutoSafetyGate


def main() -> None:
    gate = AutoSafetyGate()
    capture = time.monotonic_ns()

    prediction = Prediction(
        frame_id=123,
        capture_mono_ns=capture,
        servo_angle_deg=108.0,
        motor_pwm=160.0,
        inference_ms=6.4,
        model_id="mcqueen-demo",
        server_sequence=55,
    )

    print("RTX -> Jetson payload:")
    print(encode_message(prediction))
    print()

    receive = capture + 82_000_000
    print("Measured full round-trip:", round_trip_latency_ms(prediction, receive), "ms")

    print()
    print("Before phone authorizes AUTO:")
    print(gate.apply(prediction, receive))

    gate.set_auto_authorized(True)
    print()
    print("After phone authorizes AUTO (PWM is safety-capped):")
    print(gate.apply(prediction, receive))


if __name__ == "__main__":
    main()
