#!/usr/bin/env python3

import time
from arduino.app_utils import Bridge


def call(method, *args):
    result = Bridge.call(method, *args)
    print(f"{method}{args} -> {result}", flush=True)
    return result


print("=" * 65)
print("MCQUEEN PERFBOARD HARDWARE TEST")
print("KEEP DRIVEN WHEELS RAISED")
print("=" * 65)

print("\nChecking Linux to STM32 bridge...")
call("ping")
call("estop")

input("\nPress ENTER to test steering...")

print("Steering one direction")
call("set_drive", -400, 0, 0)
time.sleep(1)

print("Steering opposite direction")
call("set_drive", 400, 0, 0)
time.sleep(1)

print("Returning steering to centre")
call("set_drive", 0, 0, 0)
time.sleep(1)

input("\nPress ENTER to test motor FORWARD at 25%...")

call("set_drive", 0, 250, 1)
time.sleep(1)

call("set_drive", 0, 0, 0)
time.sleep(1)

input("\nPress ENTER to test motor REVERSE at 25%...")

call("set_drive", 0, -250, 1)
time.sleep(1)

call("set_drive", 0, 0, 0)
time.sleep(1)

call("estop")

print("\nTEST COMPLETE")
