#!/usr/bin/env python3
from __future__ import print_function
import time
from robot.jetson_nano.mcqueen_edge.drive import DriveController, MockDriveBackend

def packet(typ, seq, steering=0, throttle=0, motor=False):
    return {
        "type": typ,
        "session": "lab-safety",
        "sequence": seq,
        "timestamp_ms": 1,
        "steering": steering,
        "throttle": throttle,
        "motor_enabled": motor,
    }

b = MockDriveBackend()
d = DriveController(b, failsafe_seconds=0.250)

assert d.handle_packet(packet("H", 0)) == "hello"
assert d.handle_packet(packet("C", 1, 100, 20, True)) == "awaiting-neutral"
assert d.handle_packet(packet("C", 2, 0, 0, False)) == "applied"
assert d.snapshot()["session_armed"] is True
assert d.handle_packet(packet("C", 3, 250, 40, True)) == "applied"
assert d.snapshot()["throttle"] == 40
assert d.enforce_failsafe(now=d.last_command_monotonic + 0.251) is True
assert d.snapshot()["failsafe"] is True
assert d.snapshot()["throttle"] == 0

# New neutral after E-stop is required.
assert d.handle_packet(packet("E", 4)) == "estop"
assert d.snapshot()["session_armed"] is False
assert d.handle_packet(packet("C", 5, 100, 20, True)) == "awaiting-neutral"
assert d.handle_packet(packet("C", 6, 0, 0, False)) == "applied"

print("✅ JETSON PHONE SAFETY CONTRACT: neutral-arm + 250ms timeout + E-stop PASS")
