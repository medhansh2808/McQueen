#!/usr/bin/env python3
"""gpio_probe.py -- sample raw GPIO levels on pins (no edge-detect API).

Diagnostic: distinguishes 'no signal at all' (constant level) from a
wiring/counting problem (transitions present). Run on the Jetson:

  python3 gpio_probe.py --pins 29 31 --window-s 6
"""
import argparse
import sys
import time

try:
    import Jetson.GPIO as GPIO
except ImportError:
    sys.exit("FATAL: Jetson.GPIO not available on this host")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pins", type=int, nargs="+", default=[29, 31])
    ap.add_argument("--window-s", type=float, default=6.0)
    a = ap.parse_args()
    GPIO.setmode(GPIO.BOARD)
    for p in a.pins:
        GPIO.setup(p, GPIO.IN)
    trans = {p: 0 for p in a.pins}
    last = {p: None for p in a.pins}
    levels = {p: {0: 0, 1: 0} for p in a.pins}
    t0 = time.time()
    print("PROBE: sampling pins %s for %.1fs -- SPIN THE SHAFT NOW"
          % (a.pins, a.window_s))
    while time.time() - t0 < a.window_s:
        for p in a.pins:
            v = GPIO.input(p)
            levels[p][v] += 1
            if last[p] is not None and v != last[p]:
                trans[p] += 1
            last[p] = v
    for p in a.pins:
        print("pin %d: transitions=%d samples low=%d high=%d final=%d"
              % (p, trans[p], levels[p][0], levels[p][1], last[p]))


if __name__ == "__main__":
    main()