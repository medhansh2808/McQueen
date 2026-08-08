# McQueen — Jetson Nano Edge

Minimal edge software for the McQueen RC car.

## Current architecture

- Phone -> Jetson: UDP `5007` for manual steering/throttle/E-stop/status
- Phone -> Jetson: HTTP `8080` for health/status/log controls
- Jetson -> motor/servo: real GPIO/PWM backend is the next hardware step
- OAK-D -> RTX PC: WebRTC will be added later
- Dataset/training/inference: RTX PC with LeRobot + W&B

No ESP32 is used.

## Requirements

Current laptop-tested core:

- Python 3.6+
- Python standard library only

No Docker, web framework, database, or MQTT broker is required.

## Run all current tests

From the repository root:

```bash
PYTHONPATH="$PWD" python3 tests/test_jetson_protocol.py
PYTHONPATH="$PWD" python3 tests/test_jetson_drive.py
PYTHONPATH="$PWD" python3 tests/test_jetson_udp_server.py
PYTHONPATH="$PWD" python3 tests/test_jetson_http_server.py
PYTHONPATH="$PWD" python3 tests/test_jetson_edge_app.py
```

All should end in `PASS`.

## Run the edge app

From the repository root:

```bash
PYTHONPATH="$PWD" python3 -m robot.jetson_nano.mcqueen_edge.app
```

Default interfaces:

- UDP control/status: `0.0.0.0:5007`
- HTTP: `http://0.0.0.0:8080`

Stop with `Ctrl+C`.

## HTTP endpoints

- `GET /` — camera-page placeholder
- `GET /health`
- `GET /status`
- `POST /api/log/start`
- `POST /api/log/stop`

The log endpoints currently change runtime state only. Official LeRobot recording will happen on the RTX PC later.

## Safety already implemented

- new session starts safe
- neutral command required before motion
- stale/duplicate commands ignored
- phone E-stop
- ~300 ms command watchdog

## Important

The current laptop tests use a mock drive backend. They do **not** move real hardware.

Real Jetson GPIO/PWM, MG995 calibration, TB6612 control, OAK-D capture, and RTX communication are added only when their hardware stage is reached.
