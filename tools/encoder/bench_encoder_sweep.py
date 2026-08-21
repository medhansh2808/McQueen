"""Bench test tool for the JGA25-370 encoder motor (Jetson Nano).

Modes:
  identify  -- hand-spin the shaft; prints edge counts per candidate pin
               pair so A/B (and by elimination VCC/GND) can be mapped
  calibrate -- hand-spin the OUTPUT shaft N full revolutions; measures
               ticks per output revolution (ticks_per_rev), no PWM needed
  sweep     -- PWM duty sweep in both directions via the HW166 driver;
               records speed (ticks/s, RPM) + direction + deadband to CSV

Usage (on the Jetson, mcqueen-openpilot or system python3):
  python3 bench_encoder_sweep.py --mode identify --pin-a 29 --pin-b 31
  python3 bench_encoder_sweep.py --mode calibrate --pin-a 29 --pin-b 31 --revs 10
  python3 bench_encoder_sweep.py --mode sweep --pin-pwm 33 \
      --pin-bin1 16 --pin-bin2 18 \
      --pin-a 29 --pin-b 31 --ticks-per-rev 100 --out sweep.csv

Safety:
  - Motor on the bench, NOT in the car (user rule).
  - PSU current limit first (start ~2 A at 12 V); never stall > 3 s.
  - Encoder VCC 3.3-5 V only -- 12 V on the encoder destroys it.
  - Sweep ramps duty gradually and clears the throttle between steps.

Driver (TB6612/HW-166): motor on CHANNEL B (PWMB/BIN1/BIN2/B01-B02)
  (FWD: BIN1=H,BIN2=L; REV: BIN1=L,BIN2=H; idle: both L).
  STBY must be tied HIGH (to 3.3 V) on the board.

Python 3.6 compatible (Jetson Ubuntu 18.04).
"""

import argparse
import csv
import os
import sys
import time

SYS_PATH = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if SYS_PATH not in sys.path:
    sys.path.insert(0, SYS_PATH)

from robot.jetson_nano.mcqueen_edge.gpio_encoder_source import GpioEncoderSource


def _mono_s():
    return time.monotonic()


def _require_jetson_gpio():
    try:
        import Jetson.GPIO as GPIO
    except ImportError:
        print("FATAL: Jetson.GPIO not available -- run this on the Jetson.")
        sys.exit(1)
    return GPIO


def _safe_float(value):
    return float(value) if value else 0.0


def mode_identify(args):
    GPIO = _require_jetson_gpio()
    GPIO.setmode(GPIO.BOARD)
    print("IDENTIFY: spin the motor shaft by hand for ~5 seconds...")
    counts = {}
    for pin in (args.pin_a, args.pin_b):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        counts[pin] = {"rise": 0, "fall": 0}
        GPIO.add_event_detect(
            pin, GPIO.BOTH,
            callback=lambda ch, c=counts[pin]: _bump(c),
        )
    start = _mono_s()
    while _mono_s() - start < 5.0:
        time.sleep(0.05)
    for pin in (args.pin_a, args.pin_b):
        GPIO.remove_event_detect(pin)
    print("counts: pin A=%s -> %s" % (args.pin_a, counts[args.pin_a]))
    print("        pin B=%s -> %s" % (args.pin_b, counts[args.pin_b]))
    if counts[args.pin_a]["rise"] == 0 and counts[args.pin_b]["rise"] == 0:
        print("NO PULSES: encoder not powered or A/B pins wrong.")
        print("Check VCC/GND first (multimeter), then retry.")
    else:
        print("PULSES OK: pins that move are A/B. Remaining two = VCC/GND.")
    GPIO.cleanup()


def _bump(counter):
    counter["rise"] += 1
    counter["fall"] += 1


def mode_calibrate(args):
    source = GpioEncoderSource(args.pin_a, args.pin_b,
                               count_direction=-1 if args.invert_dir else 1)
    source.start()
    try:
        t0 = source.snapshot(_mono_s() * 1000000000)
        print("CALIBRATE: spin the OUTPUT shaft exactly %d full turns "
              "by hand, then press Enter..." % args.revs)
        try:
            input()
        except EOFError:
            pass
        t1 = source.snapshot(_mono_s() * 1000000000)
        ticks = t1["left_ticks_total"] - t0["left_ticks_total"]
        per_rev = float(ticks) / float(args.revs)
        print("ticks measured: %d over %d revs" % (ticks, args.revs))
        print("TICKS PER OUTPUT REVOLUTION = %.2f" % per_rev)
        print("Use this as --ticks-per-rev for --mode sweep")
    finally:
        source.stop()


def mode_sweep(args):
    if args.ticks_per_rev <= 0:
        print("FATAL: --ticks-per-rev required (run --mode calibrate first)")
        sys.exit(1)
    GPIO = _require_jetson_gpio()
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(args.pin_pwm, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(args.pin_bin1, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(args.pin_bin2, GPIO.OUT, initial=GPIO.LOW)
    pwm = GPIO.PWM(args.pin_pwm, args.pwm_hz)
    pwm.start(0)
    source = GpioEncoderSource(args.pin_a, args.pin_b,
                               count_direction=-1 if args.invert_dir else 1)
    source.start()

    def set_throttle(duty, direction):
        duty = max(0.0, min(1.0, duty))
        GPIO.output(args.pin_bin1, GPIO.HIGH if direction else GPIO.LOW)
        GPIO.output(args.pin_bin2, GPIO.LOW if direction else GPIO.HIGH)
        pwm.ChangeDutyCycle(duty * 100.0)

    def set_idle():
        GPIO.output(args.pin_bin1, GPIO.LOW)
        GPIO.output(args.pin_bin2, GPIO.LOW)
        pwm.ChangeDutyCycle(0.0)

    rows = []
    deadband = None
    try:
        for direction in (True, False):
            label = "FWD" if direction else "REV"
            for duty in _duty_steps(args):
                set_throttle(duty, direction)
                time.sleep(args.settle_s)
                base = source.snapshot(_mono_s() * 1000000000)
                samples = []
                window_end = _mono_s() + args.window_s
                while _mono_s() < window_end:
                    obs = source.snapshot(_mono_s() * 1000000000)
                    samples.append(obs)
                    time.sleep(1.0 / args.rate_hz)
                set_idle()
                rates = [s["left_ticks_per_s"] for s in samples]
                ticks_delta = (
                    samples[-1]["left_ticks_total"] - base["left_ticks_total"]
                )
                rate = sum(rates) / len(rates)
                rpm = (
                    rate * 60.0 / args.ticks_per_rev if args.ticks_per_rev > 0
                    else 0.0
                )
                if deadband is None and abs(rate) > 1.0:
                    deadband = duty
                rows.append({
                    "direction": label,
                    "duty": duty,
                    "ticks_delta": ticks_delta,
                    "ticks_per_s": rate,
                    "rate_std": _std(rates),
                    "rate_min": min(rates),
                    "rate_max": max(rates),
                    "rpm": rpm,
                    "samples": len(samples),
                })
                print("%s duty=%.2f rate=%+.1f ticks/s rpm=%+.1f "
                      "(min %+.1f max %+.1f)"
                      % (label, duty, rate, rpm, min(rates), max(rates)))
    finally:
        set_idle()
        pwm.stop()
        source.stop()
        GPIO.cleanup()

    if deadband is None:
        deadband = args.duty_max
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["direction", "duty", "ticks_delta",
                        "ticks_per_s", "rate_std", "rate_min", "rate_max",
                        "rpm", "samples"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print("DEADBAND (first duty with movement): %.2f" % deadband)
    print("CSV written: %s" % args.out)


def _std(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _duty_steps(args):
    steps = []
    duty = args.duty_min
    while duty <= args.duty_max + 1e-9:
        steps.append(round(duty, 4))
        duty += args.duty_step
    return steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["identify", "calibrate", "sweep"])
    parser.add_argument("--pin-a", type=int, default=29)
    parser.add_argument("--pin-b", type=int, default=31)
    parser.add_argument("--invert-dir", action="store_true",
                        help="flip the count direction convention")
    parser.add_argument("--revs", type=int, default=10)
    parser.add_argument("--pin-pwm", type=int, default=33)
    parser.add_argument("--pin-bin1", type=int, default=16)
    parser.add_argument("--pin-bin2", type=int, default=18)
    parser.add_argument("--pwm-hz", type=int, default=1000)
    parser.add_argument("--ticks-per-rev", type=float, default=0.0)
    parser.add_argument("--duty-min", type=float, default=0.05)
    parser.add_argument("--duty-max", type=float, default=0.95)
    parser.add_argument("--duty-step", type=float, default=0.05)
    parser.add_argument("--settle-s", type=float, default=2.0)
    parser.add_argument("--window-s", type=float, default=2.0)
    parser.add_argument("--rate-hz", type=float, default=50.0)
    parser.add_argument("--out", default="encoder_sweep.csv")

    args = parser.parse_args()
    if args.mode is None:
        parser.print_help()
        sys.exit(1)
    funcs = {
        "identify": mode_identify,
        "calibrate": mode_calibrate,
        "sweep": mode_sweep,
    }
    funcs[args.mode](args)


if __name__ == "__main__":
    main()