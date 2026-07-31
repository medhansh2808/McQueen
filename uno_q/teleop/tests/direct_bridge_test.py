#!/usr/bin/env python3
from __future__ import annotations

import time
from arduino.app_utils import Bridge


def call(method: str, *args: object) -> object:
    result = Bridge.call(method, *args)
    print(f"{method}{args} -> {result}", flush=True)
    return result


print("=" * 68)
print("MCQUEEN UNO Q DIRECT BRIDGE TEST")
print("Keep driven wheels raised.")
print("=" * 68)

print("Pinging MCU...")
call("ping")
call("estop")

input("\nPress ENTER to test steering only...")

call("set_drive", -500, 0, 0)
time.sleep(1.0)
call("set_drive", 500, 0, 0)
time.sleep(1.0)
call("set_drive", 0, 0, 0)
time.sleep(0.5)

input("\nPress ENTER to test motor forward/reverse with wheels raised...")

call("set_drive", 0, 450, 1)
time.sleep(1.5)
call("set_drive", 0, 0, 1)
time.sleep(1.0)
call("set_drive", 0, -450, 1)
time.sleep(1.5)
call("set_drive", 0, 0, 0)
time.sleep(1.0)
call("estop")

print("\nDIRECT TEST FINISHED")
