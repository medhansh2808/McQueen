# McQueen — Jetson Nano Edge

Minimal edge software for the McQueen RC car.

## Architecture

- Phone -> Jetson: UDP `5007` for manual steering/throttle/E-stop/status
- Phone -> Jetson: HTTP `8080` for health/status/log controls
- Jetson -> TB6612/MG995: direct GPIO/PWM
- OAK-D -> RTX PC: WebRTC later
- LeRobot dataset/training/inference: RTX PC

No ESP32 is used.

## Requirements

Laptop/mock mode:

- Python 3.6+
- Python standard library only

Real Jetson mode additionally uses the already-installed `Jetson.GPIO`.

No Docker, web framework, database, MQTT broker, or extra config system is required.

## Current Jetson control pins

Physical BOARD numbering:

- Pin 29 -> TB6612 AIN1
- Pin 31 -> TB6612 AIN2
- Pin 32 -> TB6612 PWMA (motor PWM, 1 kHz)
- Pin 33 -> MG995 signal (servo PWM, 50 Hz)
- TB6612 VCC + STBY -> Jetson 3.3 V
- All grounds common

Pins 32 and 33 have already been enabled/tested for PWM on the Jetson.
Pins 29 and 31 still need final hardware verification with the TB6612.

MG995 left/center/right pulse widths are intentionally not hardcoded until they are measured on the real car.

## Run all current tests

From the repository root:

```bash
PYTHONPATH="$PWD" python3 tests/test_jetson_protocol.py
PYTHONPATH="$PWD" python3 tests/test_jetson_drive.py
PYTHONPATH="$PWD" python3 tests/test_jetson_udp_server.py
PYTHONPATH="$PWD" python3 tests/test_jetson_http_server.py
PYTHONPATH="$PWD" python3 tests/test_jetson_edge_app.py
PYTHONPATH="$PWD" python3 tests/test_jetson_gpio_backend.py
PYTHONPATH="$PWD" python3 tests/test_jetson_backend_selection.py
```

All should end in `PASS`.

## Run safely on a laptop

```bash
PYTHONPATH="$PWD" python3 -m robot.jetson_nano.mcqueen_edge.app
```

This uses the mock backend and cannot move hardware.

## Run on the real Jetson later

After measuring the MG995 calibration:

```bash
PYTHONPATH="$PWD" python3 -m robot.jetson_nano.mcqueen_edge.app \
  --jetson \
  --servo-left-us <measured> \
  --servo-center-us <measured> \
  --servo-right-us <measured>
```

Default interfaces:

- UDP control/status: `0.0.0.0:5007`
- HTTP: `http://0.0.0.0:8080`

Stop with `Ctrl+C`.

## HTTP endpoints

- `GET /` — camera placeholder
- `GET /health`
- `GET /status`
- `POST /api/log/start`
- `POST /api/log/stop`

The log endpoints currently change runtime state only. Official LeRobot recording will be on the RTX PC.

## Safety already implemented

- safe startup
- neutral command required before motion
- stale/duplicate commands ignored
- phone E-stop
- ~300 ms command watchdog
- motor PWM goes to zero on stop
- AIN1/AIN2 go low on stop
- steering returns to measured center on stop

## What is still hardware-dependent

- verify AIN1/AIN2 on pins 29/31 with the TB6612
- calibrate MG995 pulse widths
- test real motor and servo
- connect OAK-D
- add Jetson <-> RTX WebRTC path
- connect official LeRobot recording/training/inference
