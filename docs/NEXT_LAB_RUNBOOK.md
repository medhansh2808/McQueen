# McQueen — next lab runbook

The first phase assumes **no chassis, no motor, no encoder motor and no servo** are available yet.
Available: Jetson, Wi-Fi dongle, Lenovo camera, laptop, phone/hotspot, lab/alternate Wi-Fi and RTX 4090.

## Phase A — no drivetrain required

### 0. QUICK WAN PIPELINE TEST (the "server thing") — do this first if the
    only goal is proving the Jetson<->RTX video loop again

- On the laptop, in a real terminal (interactive SSH passwords):
  `./tools/realtime/run_rtp_wan_test.sh`
- It deploys the FIXED sender to the Jetson and the receiver to the RTX, starts
  broker + cloudflared (or reuses running ones), runs the loop 35s, and prints
  stage-by-stage results (NAT punch ready / RTX decoded frames / control return /
  full-loop latency).
- Key: use the venv python on the RTX (`gst-webrtc-venv/bin/python`) — system
  python lacks `websocket` (error #21). WebRTC is DEAD on the Jetson's old
  GStreamer (error #6) — do not retry webrtcbin.
- If the loop is not green, see `docs/evidence/2026-08-13-lab-pull/README.md`
  findings F1–F6 and the 21-entry error log.

### 1. Jetson health before changing anything

- connect/power Jetson
- SSH in
- run `tools/preflight/jetson_no_drivetrain_preflight.sh`
- explicitly verify `mcqueen-edge.service`; the previous benchmark may have stopped it
- verify UDP 5007 and HTTP 8080

Do not assume service state from yesterday.

### 2. Network matrix

Verify:
- USB SSH path
- Jetson Wi-Fi dongle
- phone hotspot path
- lab Wi-Fi fallback
- Jetson DNS/Internet

Networking must not block RTX/model/data work if one viable path exists.

### 3. Real camera path

- connect Lenovo camera to Jetson
- verify stable V4L2 device
- verify MJPEG 1280x720 @ 30 fps
- verify `nvv4l2decoder`, `nvvidconv`, `nvv4l2h264enc`, `webrtcbin`
- reproduce real camera -> Jetson hardware encode

### 4. RTX inspection

SSH to RTX and run `tools/preflight/rtx4090_preflight_v2.sh`.

Verify before installing anything:
- RTX 4090 visible
- PyTorch/CUDA
- existing LeRobot environment/version
- repo status
- free disk/GPU state

Do not reinstall CUDA/Torch/LeRobot blindly and do not kill unrelated GPU jobs.

### 5. Run deferred temporal-candidate tests

A local, intentionally uncommitted package is prepared at:

`~/Downloads/mcqueen_rtx_candidate_20260812`

Copy that folder to the RTX and run its `run_rtx_candidate_tests.sh` in the actual RTX LeRobot
Python. Only after it passes should the temporal PyTorch core move into the production repo.

### 6. Actual LeRobot-v2 conversion

Using the real RTX environment:
- convert a synthetic or tiny v2 episode
- inspect resulting features/actions/wheel state
- only then regard converter/runtime compatibility as proven

### 7. PPGeo first

Follow `BACKBONE_INTEGRATION_PLAN.md`:
- inspect official checkpoint structure
- integrate ResNet-34 adapter
- fake six-frame forward
- benchmark latency/memory

Drive-JEPA comes after the same interface is proven with PPGeo.

### 8. Real camera/control integration

With Jetson camera + RTX (NEW transport — NAT-punched raw RTP over UDP, NOT WebRTC):
- `tools/realtime/gst_jetson_rtp_wan.py` (Jetson sender) + `tools/realtime/gst_rtx_rtp_receiver.py` (RTX receiver)
- exact frame metadata/identity (in-band META: frame_id + capture_mono_ns)
- inference or dummy inference
- direct UDP control return
- Jetson dry-run receive
- run via `tools/realtime/run_rtp_wan_test.sh`

Use benchmark-v2 stage-by-stage diagnostics. Do not enable GPIO merely to benchmark transport.

### 9. Real KACHOW interface

Repeat real phone -> real Jetson mock/no-GPIO probe to confirm current code state before physical
hardware arrives.

## Phase B — when drivetrain/servo/encoder motors arrive

1. install mechanical drivetrain/servo;
2. verify physical KACHOW neutral/steering/forward/reverse/E-stop;
3. identify encoder power/ground/signal wiring;
4. verify signal voltage is Jetson-safe before connection;
5. determine single-channel vs quadrature;
6. choose ordinary GPIO inputs (encoder signals do not require PWM pins);
7. hand-turn wheels and verify left/right counts/directions;
8. measure counts/revolution or preserve enough raw data to derive it later;
9. lock final camera mount;
10. record a 20–30 second dataset-v2 episode;
11. validate timing/images/actions/encoder validity/deltas/rates immediately;
12. only after that passes, collect serious demonstrations;
13. sync a sample to RTX and run real conversion/training;
14. physical autonomous actuation only after safety and closed-loop dry-run checks pass.
