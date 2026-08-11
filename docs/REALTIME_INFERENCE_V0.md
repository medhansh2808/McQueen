# McQueen realtime inference architecture (v0)

This document locks the intended responsibility split without locking a Jetson
WebRTC implementation before hardware preflight.

## Runtime roles

Jetson Nano:
- Lenovo camera capture
- video encode/stream
- phone TELEOP / AUTO authority
- actuator execution
- stale-command failsafe
- capture timestamp generation
- raw dataset logging

RTX 4090:
- receive/decode video
- model preprocessing
- model inference
- return [servo_angle_deg, motor_pwm]
- W&B / evaluation / model metadata

Laptop:
- development/debugging
- offline held-out replay viewer
- no normal robot-runtime dependency

## Connectivity

Tailscale provides private reachability between Jetson and RTX when they are on
different physical networks.

WebRTC is the intended realtime media/control transport:
- video: Jetson -> RTX
- prediction/control DataChannel: RTX -> Jetson
- telemetry/latency metadata: both directions as needed

The remote model never grants driving authority. The phone/Jetson state machine
must explicitly enter AUTO before any remote prediction reaches actuators.

## Latency measurement

Jetson assigns each captured frame:
- frame_id
- capture_mono_ns

RTX must echo both in the returned Prediction message.

Jetson computes:
    receive_mono_ns - capture_mono_ns

This is the authoritative full capture -> RTX -> returned-command measurement
and does not depend on synchronized clocks.

Additional RTX-local timestamps may be logged for profiling:
- RTX receive
- inference start
- inference finish

## Initial safety configuration

These are configuration values, not model constants:
- forward PWM cap: 100
- reverse PWM magnitude cap: 70
- stale prediction timeout: 250 ms
- stale result: PWM 0, steering 90 deg, AUTO cancelled

## Implementation decision gate

Do not force a modern Python WebRTC package onto the old Jetson.

Tomorrow first run:
    tools/realtime/preflight_jetson_webrtc.sh

If Jetson already has:
- webrtcbin
- nvv4l2h264enc

prefer the native GStreamer/NVIDIA hardware-encode route on Jetson.

The RTX can use a modern Python WebRTC stack in its isolated McQueen environment
if compatible with that environment.

Only install missing Jetson packages after inspecting the actual preflight.
