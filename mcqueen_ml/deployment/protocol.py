"""Wire contract for McQueen Jetson <-> RTX realtime inference.

Transport-independent on purpose. WebRTC/Tailscale are plugged underneath this
contract later.

Important latency rule:
- Jetson stamps frame_capture_mono_ns with time.monotonic_ns().
- RTX echoes the exact value in its prediction.
- Jetson computes receive_mono_ns - frame_capture_mono_ns.
This measures full capture->prediction-return latency without comparing clocks
from two different machines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Literal


PROTOCOL_VERSION = 1
MessageType = Literal["frame_meta", "prediction", "heartbeat"]


@dataclass(frozen=True)
class FrameMeta:
    frame_id: int
    capture_mono_ns: int
    width: int
    height: int
    source_fps: float
    type: str = "frame_meta"
    version: int = PROTOCOL_VERSION


@dataclass(frozen=True)
class Prediction:
    frame_id: int
    capture_mono_ns: int
    servo_angle_deg: float
    motor_pwm: float
    inference_ms: float
    model_id: str
    server_sequence: int
    type: str = "prediction"
    version: int = PROTOCOL_VERSION


@dataclass(frozen=True)
class Heartbeat:
    sequence: int
    sender: str
    type: str = "heartbeat"
    version: int = PROTOCOL_VERSION


def encode_message(message: FrameMeta | Prediction | Heartbeat) -> str:
    return json.dumps(asdict(message), separators=(",", ":"), sort_keys=True)


def decode_message(payload: str | bytes) -> FrameMeta | Prediction | Heartbeat:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    raw: dict[str, Any] = json.loads(payload)

    if raw.get("version") != PROTOCOL_VERSION:
        raise ValueError(
            f"Unsupported protocol version {raw.get('version')!r}; "
            f"expected {PROTOCOL_VERSION}"
        )

    kind = raw.get("type")
    if kind == "frame_meta":
        return FrameMeta(**raw)
    if kind == "prediction":
        return Prediction(**raw)
    if kind == "heartbeat":
        return Heartbeat(**raw)
    raise ValueError(f"Unknown message type: {kind!r}")


def round_trip_latency_ms(prediction: Prediction, receive_mono_ns: int) -> float:
    if receive_mono_ns < prediction.capture_mono_ns:
        raise ValueError("receive timestamp is earlier than capture timestamp")
    return (receive_mono_ns - prediction.capture_mono_ns) / 1_000_000.0
