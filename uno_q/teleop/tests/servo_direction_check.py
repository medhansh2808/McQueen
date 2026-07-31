#!/usr/bin/env python3

import time
from arduino.app_utils import Bridge


def hold_steering(command: int, seconds: float = 1.2) -> int:
    end_time = time.monotonic() + seconds

    while time.monotonic() < end_time:
        Bridge.call("set_drive", command, 0, 0)
        time.sleep(0.05)

    angle = int(
        Bridge.call("get_servo_angle")
    )

    print(
        f"Actual servo angle: {angle} degrees",
        flush=True,
    )

    Bridge.call("estop")
    time.sleep(0.7)

    return angle


try:
    print("=" * 60)
    print("SERVO DIRECTION CHECK")
    print("Keep the wheels raised.")
    print("=" * 60)

    print("MCU ping:", Bridge.call("ping"))
    Bridge.call("estop")

    input("\nPress ENTER for current centre...")
    centre = hold_steering(0)
    print(f"Centre angle: {centre} degrees")

    input("\nPress ENTER for TEST A...")
    angle_a = hold_steering(-200)
    print(f"TEST A angle: {angle_a} degrees")
    print("Observe whether the wheels moved LEFT or RIGHT.")

    input("\nPress ENTER for TEST B...")
    angle_b = hold_steering(200)
    print(f"TEST B angle: {angle_b} degrees")
    print("Observe whether the wheels moved LEFT or RIGHT.")

finally:
    try:
        Bridge.call("estop")
    except Exception:
        pass

print("\nTEST FINISHED")
