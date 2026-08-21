# ENCODER BENCH — JGA25-370 encoder-motor bench runbook (2026-08-18)

> **CORRECTION 2026-08-19 (CAR SESSION): the wire colors below were WRONG for
> the actual motor.** Encoder power pair = **blue (VCC) / black (GND)**;
> motor pair = **white / red**. Bench was abandoned midway (user left); the
> bench never completed. THE CAR USES CHANNEL A (pins 29/31/32, encoder 11/13)
> per `jetson_gpio.py` — this doc's channel-B card (16/18/33) is for the bench
> ONLY and does not match the car. See `docs/CAR_WIRING.md` for the car.

Motor: **JGA25-370**, 6 wires (equal thickness): white, blue, green, yellow,
black, red. 2 = motor power (12 V class; running at 7.4 V PSU), 4 = hall
quadrature encoder (VCC/GND/A/B). Driver: **TB6612/HW-166** (motor on **CHANNEL B**: PWMB/BIN1/BIN2/B01-B02).
PSU: 7.4 V, current limit 1.5 A. ONE motor powers BOTH rear wheels -> one
encoder, mirrored into the left/right contract.

---

## ⚡ WIRING CARD (print this; everything else below is reference)

```
JETSON (40-pin, BOARD numbers)          MOTOR/DRIVER
--------------------------------        ------------------------------
pin 1  (3.3V)   <-->  encoder blue  (VCC)      [verify at bench]
pin 6  (GND)    <-->  encoder white (GND)      [verify at bench]
pin 29          <-->  encoder green (A)
pin 31          <-->  encoder yellow (B)
pin 17 (3.3V)   <-->  driver VCC (logic)
pin 6  (GND)    <-->  driver GND
pin 33 (PWM1)   <-->  driver PWMB            [CHANNEL B]
pin 16          <-->  driver BIN1
pin 18          <-->  driver BIN2
driver STBY     <-->  driver VCC (tie HIGH)     [enables outputs]
driver VM       <-->  PSU + (7.4V)
driver GND      <-->  PSU -
driver B01/B02  <-->  motor red/black (either order = direction data)
PSU -  and Jetson pin 6 = COMMON GROUND (mandatory)

SAFETY: 7.4V ONLY on driver VM. Encoder wires ONLY on pins 1/6/29/31.
Motor pair ONLY on A01/A02. PSU limit 1.5A BEFORE switch-on.
No connect/disconnect while PSU on. Motor secured on bench.
```

## Test flow (3 modes, then analysis — total ~15 min)

| Step | Command (on Jetson, system python3) | What it gives |
|------|--------------------------------------|---------------|
| 1 | `python3 tools/encoder/bench_encoder_sweep.py --mode identify --pin-a 29 --pin-b 31` | confirms A/B pulse while hand-spinning; VCC/GND by elimination |
| 2 | `python3 tools/encoder/bench_encoder_sweep.py --mode calibrate --pin-a 29 --pin-b 31 --revs 10` | **TICKS PER OUTPUT REV** (the wheel-speed calibration constant) |
| 3 | `python3 tools/encoder/bench_encoder_sweep.py --mode sweep --pin-a 29 --pin-b 31 --ticks-per-rev <v> --out ~/mcqueen/run/encoder_sweep.csv` | duty sweep FWD+REV: ticks/s, RPM, rate spread, deadband |
| 4 | (laptop) `python3 tools/encoder/analyze_sweep.py --csv encoder_sweep.csv --ticks-per-rev <v>` | summary CSV + deadband + direction convention + symmetry |

Wire identification: red/black = motor pair (1-10 Ω). Blue/white should show
~0.5-0.7 V diode drop one way only (diode mode, UNPOWERED). Green/yellow =
A/B (either order; swap is harmless). If any measurement is confusing: STOP,
report numbers, do not power anything.

## Data design

- `encoder_sweep.csv` (Jetson): direction, duty, ticks_delta, ticks_per_s,
  rate_std, rate_min, rate_max, rpm, samples — one row per duty step,
  2 s settle + 2 s measurement window at 50 Hz, idle throttle between steps.
- `encoder_summary.csv` (laptop): duty, fwd_rpm, rev_rpm, fwd/rev ticks/s.
- Calibration constant: ticks_per_rev (output shaft, measured, not assumed).
- Direction convention: decided from the sweep (FWD positive -> default;
  negative -> re-run with `--invert-dir` or swap A/B).
- Deliverable: `docs/evidence/2026-08-18/encoder-bench/` (CSV + summary +
  REPORT.md, no clock timestamps) after the session.

## Safety rules (non-negotiable)

1. 7.4 V NEVER on encoder wires or Jetson GPIO. Encoder VCC = 3.3 V only.
2. Motor pair ONLY on driver A01/A02.
3. PSU: 7.4 V, current limit 1.5 A, set BEFORE switch-on. Stall > 3 s = stop.
4. Common ground: PSU -, driver GND, Jetson pin 6.
5. All wiring changes with PSU OFF. Power-down order: stop script -> PSU off
   -> disconnect.
6. Motor on bench, secured (tape/vise). LiPo (2S) later only with inline
   2-3 A fuse.

## Files

- `robot/jetson_nano/mcqueen_edge/gpio_encoder_source.py` — quadrature
  counter (Jetson.GPIO edge events, signed, thread-safe), speaks the
  recorder/schema-v2 `snapshot()` contract (left=right, single motor).
- `tools/encoder/bench_encoder_sweep.py` — identify / calibrate / sweep.
- `tools/encoder/analyze_sweep.py` — laptop analysis (pure stdlib).
- `tools/encoder/test_encoder_bench.py` — laptop unit tests
  (`python3 -m unittest tools.encoder.test_encoder_bench -v`).
- `tools/encoder/deploy_bench.sh` — 1-command scp to the Jetson.