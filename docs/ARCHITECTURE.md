# McQueen architecture

## Phone / KACHOW

Human-control and authority endpoint:
- manual steering/throttle
- ARM / neutral-arm flow
- manual takeover / E-stop
- AUTO authorization

Manual/E-stop authority must override remote inference.

## Jetson Nano 2GB

Edge runtime:
- Lenovo camera capture
- NVIDIA hardware H.264 encode
- KACHOW UDP teleop
- dataset-v2 recording
- exact frame IDs and Jetson monotonic capture timestamps
- future wheel-encoder GPIO input
- actuator I/O
- stale-prediction / steering / speed safety

Current steering mapping:
- `-1000 -> 115 deg` left
- `0 -> 90 deg` center
- `+1000 -> 45 deg` right

## RTX 4090

First autonomous compute target:
- receive/decode camera video
- preprocessing
- temporal-policy inference
- return `[servo_angle_deg, motor_pwm]`
- training/evaluation/checkpoints

Jetson-only inference is a later compression/distillation option, not the current requirement.

## Laptop

Development/SSH/debug/Git/orchestration and dataset inspection. It is not intended to sit in the
normal robot runtime loop.

## Transport split

- video: Jetson hardware H.264 -> WebRTC -> RTX
- signaling: WebSocket/WSS rendezvous when needed
- autonomous action return: direct UDP
- full-loop identity: exact frame ID
- authoritative latency origin: Jetson monotonic capture timestamp

## Dataset flow

1. Human drives with KACHOW.
2. Jetson records RGB/actions/timestamps/encoder observations.
3. Raw episode validates against dataset-v2.
4. Convert to LeRobot in the verified RTX environment.
5. Split by whole episodes.
6. Train temporal policy.
7. Evaluate held-out drives before closed-loop deployment.
