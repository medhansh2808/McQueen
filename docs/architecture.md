# Architecture

McQueen is a two-machine autonomous driving stack: a **Jetson Nano** in the car and an **RTX 4090** workstation doing inference, with a laptop used only for development.

## Control loop

```
[Phone (Kachow app)] ──UDP teleop──> [Jetson Nano · edge runtime] <──UDP control── [RTX 4090 · policy worker]
                                         │        ▲                                        │
[Camera] ──MJPEG──> [Jetson · GStreamer H.264] ──RTP / UDP (STUN-punched)──> [RTX · RTP receiver]
                                         │                                                       │
[Servo + ESC] <──PWM── [Jetson · safety gate] <───────────────────────────── steering + throttle
```

### 1. Capture and transport (`realtime/`)
The Jetson encodes the camera (`gst_jetson_rtp_wan.py`) to H.264 and pushes frames over **direct peer-to-peer UDP**, punched through NAT by a tiny STUN round-trip (`realtime/common/mini_stun.py`). Every frame carries an exact `frame_id` and the Jetson monotonic capture time (`capture_monotonic_ns`) so the receiver can associate frames with actions.

`broker.py` (an aiohttp service) is used **only** for NAT-punch/discovery signaling — neither video nor control flows through it.

### 2. Inference (`realtime/rtx/`)
`gst_rtx_rtp_receiver.py` decodes the stream and hands frames to `policy_worker.py`, which runs the temporal corridor policy: a frozen supercombo trunk plus a trained action head (`rtx_policy_v1.py`). A 6-frame window plus previous actions and encoder state produce `(servo_angle_deg, pwm255)`.

The prediction is returned **directly over UDP** on the same punched path to the edge control port (`127.0.0.1:5007`).

### 3. Edge and safety gate (`edge/`)
The edge runtime (`app.py`) owns the actuators and the ultimate authority over the car:

- **Teleop**: a UDP teleop server accepts phone commands (`server.py`).
- **Recorder**: raw frames + drive state are spooled to CSV rows (`recorder.py`, `record_row.py`) for offline training.
- **Safety gate**: the remote model never grants itself authority. AUTO requires explicit phone authorization; predictions are rejected when not authorized, stale (> 250 ms), or out of range; any failure triggers `safe_stop` (center servo, motor PWM 0). The edge also safe-stops on its own if control packets stop arriving.

### 4. Development
The laptop is not part of the runtime loop. It is used for coding, dataset inspection, and offline replay.

## Data format

Recorded rows use the schema in `mcqueen_ml/dataset/schema_v2.py`:

| Field | Meaning |
|---|---|
| `frame_index`, `capture_monotonic_ns` | frame identity + capture time |
| `observation.images.front_rgb` | relative path to the raw frame |
| `action.servo_angle_deg`, `action.motor_pwm` | commanded action |
| `observation.wheels.encoder_valid` | encoder health flag |
| `observation.wheels.left/right_ticks_total/delta` | wheel encoder counts |