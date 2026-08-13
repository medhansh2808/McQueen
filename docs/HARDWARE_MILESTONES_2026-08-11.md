# Hardware-verified lab milestones — 2026-08-11

**Scope rule:** this file contains only results that involved the real project hardware or real
network endpoints during the 2026-08-11 lab session. Home unit tests, synthetic fixtures, design
decisions and unexecuted PyTorch code are deliberately excluded.

## 1. Real Jetson <-> real RTX 4090 direct-WAN control path

Verified with the Jetson and RTX 4090 on separate Internet paths.

Observed result:

- direct UDP NAT-punched path became ready on both peers
- RTX reported CUDA on an NVIDIA GeForce RTX 4090
- `60/60` returned control packets were acknowledged
- control RTT: `29.4 ms` minimum
- control RTT: `43.1 ms` p50
- control RTT: `70.4 ms` p95
- control RTT: `75.7 ms` maximum

**Boundary:** the Jetson endpoint was deliberately dry-run (`ZERO GPIO WRITES`). This proves the
real returned-control network path and Jetson receipt/ACK behavior. It does **not** prove physical
servo or motor actuation.

A sanitized excerpt is retained in `docs/evidence/2026-08-11-direct-wan-control.txt`.

## 2. Real Lenovo camera -> Jetson hardware video path -> RTX compute path

Verified with the actual Lenovo camera, Jetson Nano and RTX 4090:

- camera capture on Jetson
- MJPEG camera input
- NVIDIA Jetson hardware H.264 encode path
- WebRTC video transport
- RTX decode/appsink reception
- CUDA/PyTorch dummy action computation on the RTX

**Boundary:** the successful complete camera-compute proof used the temporary local lab route.
It is not the final authoritative separate-WAN camera-to-returned-command latency measurement.

## 3. Real KACHOW phone -> real Jetson command-interface proof

With the actual phone and Jetson, the KACHOW probe observed valid non-zero control traffic,
including forward/reverse throttle values and steering commands reaching both extremes.

**Boundary:** this probe used the Jetson `MockDriveBackend` / no-GPIO path. It proves real
phone-to-Jetson packet parsing/control semantics, not physical actuator motion.

## Explicitly NOT counted as hardware milestones today

The following are not claimed as hardware-verified in this file:

- wheel-encoder wiring or encoder counts
- physical encoder-motor operation
- physical servo/motor movement from today's final probes
- PPGeo or Drive-JEPA checkpoint inference
- the new temporal Transformer forward pass
- actual LeRobot-v2 conversion in the current RTX environment
- final separate-WAN full camera -> inference -> returned-command latency
- trained autonomous driving
- unknown-environment autonomous navigation
- any synthetic/home-only test result
