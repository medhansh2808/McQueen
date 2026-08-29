# Hardware

## Bill of materials

| Part | Purpose |
|---|---|
| 1/10-scale RC car (servo + ESC + motor) | chassis |
| Jetson Nano 2 GB | on-car edge compute |
| Lenovo FHD webcam (MJPEG, 1280×720@30fps) | front camera |
| TB6612 (or compatible) motor driver | motor direction + PWM |
| MG995 (or compatible) servo | steering |
| Hall-effect wheel encoder (2-channel) | wheel tick sensing |
| RTX 4090 workstation | realtime inference |

## Jetson GPIO wiring

Drive backend wiring (`edge/jetson_gpio.py`), BOARD numbering:

| BOARD pin | Signal |
|---|---|
| 29 | TB6612 AIN1 (direction) |
| 31 | TB6612 AIN2 (direction) |
| 32 | TB6612 PWMA (motor PWM) |
| 33 | MG995 signal (servo PWM, 50 Hz) |

Wheel encoder: the two hall phases are wired to two Jetson GPIOs and read in software (see `edge/encoder_source.py`). The encoder phases are open-collector outputs — external pull-up resistors to 3.3 V are required for the pins to count reliably.

## Servo calibration

The servo is calibrated in microseconds and passed explicitly to the edge app (Jetson mode refuses to start without measured values):

```bash
python3 edge/app.py --jetson \
  --servo-left-us 1750 --servo-center-us 1500 --servo-right-us 1275
```

Example values (`realtime/config.env.example`): left 1750, center 1500, right 1275.

## CAD

Printable servo mounts live in `hardware/cad/` (`servohorn.stl`, `servomount.stl`).