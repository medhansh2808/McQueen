# McQueen — Autonomous Driving RC Car

End-to-end self-driving stack for a 1/10-scale RC car. A Jetson Nano captures the camera, streams it over a low-latency RTP tunnel to an RTX 4090 that runs the driving policy, and returns steering + throttle over UDP through a Jetson safety gate.

<div align="center">

### ▶ Demo

<video src="media/demo.mp4" controls muted loop width="100%"></video>

</div>

## Architecture

```
[Phone (Kachow app)] ──UDP teleop──> [Jetson Nano · edge runtime] <──UDP control── [RTX 4090 · policy worker]
                                         │        ▲                                        │
[Camera] ──MJPEG──> [Jetson · GStreamer H.264] ──RTP / UDP (STUN-punched)──> [RTX · RTP receiver]
                                         │                                                       │
[Servo + ESC] <──PWM── [Jetson · safety gate] <───────────────────────────── steering + throttle
```

- **Jetson Nano** (2 GB): captures the camera (`gst_jetson_rtp_wan.py`), H.264-encodes and pushes frames over a direct UDP path with exact `frame_id` + monotonic capture timestamps. Runs the **edge runtime** (`edge/`) — teleop server, recorder, and the safety gate that owns the servo and motor.
- **RTX 4090**: decodes frames (`gst_rtx_rtp_receiver.py`) and runs the driving policy (`policy_worker.py`) — a frozen supercombo trunk plus a trained corridor head — producing `(servo_angle_deg, pwm255)` pairs returned over direct UDP to the edge (`:5007`).
- **`broker.py`**: NAT-punch/discovery signaling only — video and control never travel through it.
- **Laptop**: development only. Not part of the runtime loop.

## Features

- Full teleop: phone controller, UDP teleop server, recording with raw-frame spool
- Realtime inference over WAN with STUN-punched direct peer-to-peer transport
- Safety gate: explicit AUTO authorization, 250 ms prediction timeout, actuator limits, safe-stop on any failure
- Temporal corridor policy (6-frame window) trained on recorded teleop episodes

## Hardware

| Part | Role |
|---|---|
| 1/10-scale RC car | chassis (servo + ESC) |
| Jetson Nano 2 GB | on-car edge compute, GPIO actuation |
| Lenovo FHD webcam (MJPEG) | front camera |
| RTX 4090 workstation | realtime inference |

See [`docs/hardware.md`](docs/hardware.md) for wiring and the BOM.

## Quick Start

```bash
git clone https://github.com/medhansh2808/McQueen.git
cd McQueen
pip install uv && uv sync        # or: pip install -r requirements.txt
```

- **Jetson (edge + sender):** see [`docs/installation.md`](docs/installation.md) and run `scripts/start_edge_ai.sh`
- **RTX (receiver + policy):** `cp realtime/config.env.example realtime/config.env`, edit, then `realtime/rtx/start_stack.sh`
- **Phone controller:** build `apps/android/Kachow` (Android Studio)

## Safety

The model never grants itself authority. AUTO mode requires explicit authorization from the phone, predictions are rejected when stale (> 250 ms) or out of range, and any failure triggers `safe_stop` (center servo, motor off). The edge fails safe on its own even if every remote process dies.

## Repository Layout

```
edge/            Jetson Nano runtime: teleop, recorder, safety gate, GPIO
realtime/        Realtime inference: jetson sender, rtx receiver + policy worker, broker, STUN
mcqueen_ml/      Dataset schema, training, deployment safety code
models/          Action head + frozen-trunk adapter (ONNX export pipeline)
apps/android/    Kachow — Android phone controller
deploy/systemd/  systemd units for Jetson + RTX
hardware/cad/    3D-printed servo mounts
docs/            Architecture, hardware, installation, edge, realtime guides
scripts/         setup and run scripts
```

## License

All rights reserved.

## Branch Structure

This repository is developed across two long-lived branches:

| Branch | Purpose |
|--------|---------|
| `main` | Original project history and source of truth: the jetson + realtime architecture (`realtime/`, `models/`, `deploy/`), documentation, and dependency manifests (`pyproject.toml`, `uv.lock`, `requirements.txt`). |
| `jetson-nano` | Active device (deployment) branch and the repository's default: carries the runtime executed on the car — the edge autonomy stack (`edge/`), realtime inference (`realtime/`), `mcqueen_ml/`, `models/`, and the Android controller (`apps/android/Kachow`). |

Development happens on `jetson-nano`; `main` preserves the original history alongside documentation and dependency manifests.