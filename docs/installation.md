# Installation

## Dependencies

```bash
pip install uv && uv sync          # reproducible install (uv.lock)
# or, with plain pip:
pip install -r requirements.txt
```

`pyproject.toml` declares extras per role:

| Extra | For |
|---|---|
| `edge` | Jetson Nano GPIO (Jetson.GPIO) |
| `rtx` | RTX receiver/policy (onnxruntime, websocket-client, aiohttp) |
| `train` | training (torch, onnx, pandas) |

System packages pip cannot install:

```bash
# Jetson Nano (Ubuntu 18.04 / Python 3.6):
sudo apt install python3-gi gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-tools
sudo pip install Jetson.GPIO        # hardware GPIO driver
```

## Jetson Nano (edge + sender)

```bash
# 1) calibrate the servo and start the edge runtime
./scripts/start_edge_ai.sh

# 2) start the camera sender
cp realtime/config.env.example realtime/config.env   # edit per host
realtime/jetson/go_autonomy_jetson.sh --broker-host <broker-url>
```

## RTX 4090 (receiver + policy)

```bash
cp realtime/config.env.example realtime/config.env   # edit per host (keep MCQUEEN_BROKER_HOST empty on RTX)
realtime/rtx/start_stack.sh
```

The broker (`realtime/rtx/broker.py`) is started automatically by the stack and is used for NAT-punch/discovery only.

## Phone controller

Open `apps/android/Kachow` in Android Studio and build. The app discovers the car on the local network and drives over UDP.

## systemd units

Ready-made units for both machines are in `deploy/systemd/` (edge, recorder, ssh tunnel, URL report timer). Install with:

```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```