# CAR WIRING — McQueen drivetrain + servo (2026-08-19, VERIFIED at car)

Authoritative wiring for the car as built. Supersedes the bench card's wire
colors (they were WRONG for this motor — see ENCODER_BENCH.md correction).

## POWER (2 UBECs, verified plan)
```
11.4V battery + ──► UBEC-1 input ──► 5V out ──► TB6612 VM
11.4V battery + ──► UBEC-2 input ──► 5V out ──► servo VCC (red)
11.4V battery − ──► both UBEC inputs' GND
```
- UBEC-1 = 5V/3A motor-driver supply. 3A built-in limit protects the TB6612
  (rated 1.2A continuous / 3.2A peak) from stall current — NEVER feed the
  driver direct from the battery (11.4V no-limit fried the first driver).
- UBEC-2 = servo supply (MG995 can spike ~2.5A on stall; separate UBEC keeps
  it from tripping the motor supply).

## JETSON 40-PIN (BOARD numbering) → DEVICES
```
pin 1  (3.3V)  <->  encoder blue  (VCC)      [corrected: was white in bench doc]
pin 6  (GND)   <->  encoder black (GND)      [corrected: was white/red confusion]
pin 11         <->  encoder green (A)
pin 13         <->  encoder yellow (B)
pin 17 (3.3V)  <->  driver VCC (logic)
pin 6  (GND)   <->  driver GND
pin 29         <->  driver AIN1               [channel A — code expects A]
pin 31         <->  driver AIN2               [channel A]
pin 32         <->  driver PWMA (motor PWM)   [channel A]
pin 33         <->  servo signal (yellow/white)
driver STBY    <->  driver VCC (tie HIGH)     [enables outputs]
driver VM      <->  UBEC-1 5V
driver GND     <->  UBEC-1 GND
driver A01/A02 <->  motor white / red (either order = direction data)
servo red      <->  UBEC-2 5V
servo black    <->  UBEC-2 GND
```

## COMMON GROUND (mandatory)
```
Jetson pin 6 ── UBEC-1 GND ── UBEC-2 GND ── TB6612 GND ── servo GND ── encoder GND
```

## WIRE COLORS (JGA25-370 in the car — VERIFIED 2026-08-19)
| Wire | Role |
|---|---|
| blue | encoder VCC (3.3V ONLY) |
| black | encoder GND |
| green / yellow | encoder A / B quadrature (order swap harmless) |
| white / red | MOTOR pair (→ driver A01/A02) |

The bench doc's old claim (blue/white = encoder power, red/black = motor) was
WRONG for this motor. Encoder power pair = blue/black; motor = white/red.

## CODE CONTRACT (must match — robot/jetson_nano/mcqueen_edge/jetson_gpio.py)
- AIN1=29, AIN2=31, PWMA=32, servo=33, encoder default pins "11 13".
- The bench card wired the TB6612 on CHANNEL B (16/18/33) — the car code drives
  CHANNEL A. Bench doc updated accordingly; do NOT re-add channel-B wiring.

## SAFETY
- 5V ONLY on driver VM and servo (via UBECs). Never 11.4V on anything but the
  UBEC inputs.
- Common ground mandatory (no common ground = floating logic = driver damage).
- No connect/disconnect while powered. Battery OFF first.
- Wheels must be free when powering up (a stalled/back-driven motor generates
  current back through the enabled driver output stage → fried the first
  TB6612).
- Encoder VCC is 3.3V ONLY — 5V/7.4V/11.4V on encoder wires kills the encoder.