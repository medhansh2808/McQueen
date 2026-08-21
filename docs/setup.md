# Current McQueen setup

This file describes the current Jetson-based direction. Legacy UNO-Q/OAK-D code remains in the
repository for history/experiments but is not the current runtime architecture.

## Current compute / control

| role | current direction |
|---|---|
| human controller | Nothing Phone 3a running KACHOW |
| edge computer | Jetson Nano 2GB |
| remote compute | RTX 4090 |
| development | Ubuntu laptop |
| camera | Lenovo FHD webcam |
| motor driver | TB6612FNG family board |
| steering | servo hardware when available |
| drivetrain | brushed motor hardware; encoder-motor upgrade pending physical integration |

At the start of the next lab session, the drivetrain/chassis/servo may not yet be physically
available; the Jetson/camera/network/RTX work can proceed independently.

## Phone / network ports

Jetson runtime uses:
- UDP 5006: KACHOW discovery when discovery service is enabled
- UDP 5007: phone teleoperation
- TCP 8080: status/recording HTTP service

Portable operation can use the phone hotspot; lab Wi-Fi is a fallback/test path. Dynamic Wi-Fi
addresses should be discovered rather than hard-coded.

## Steering semantics

- `-1000` -> `115 deg` left
- `0` -> `90 deg` center
- `+1000` -> `45 deg` right

## Camera

Known Lenovo camera target:
- MJPEG
- 1280x720
- 30 fps camera source

Known Jetson video path:

    v4l2src
      -> jpegparse
      -> nvv4l2decoder mjpeg=1
      -> nvvidconv
      -> NVMM NV12
      -> nvv4l2h264enc
      -> h264parse

Dataset recording is initially 10 Hz and uses `mcqueen-driving-spool-v2`.

## Power

Current actuator battery direction is a 2S LiPo (nominal 7.4 V). Jetson/camera/network power is
handled separately by the power-bank arrangement. Re-check all grounds and actual voltage rails
when the drivetrain is reassembled; do not infer wiring from old UNO-Q setup notes.

## Next session

Run procedures live in `tools/realtime/` (sender/receiver/bench scripts); see
`docs/full_loop_benchmark_v2.md` for the measurement contract.

## Free model providers (opencode)

### 1. NVIDIA NIM

- **API Key Storage**: Stored securely in `auth.json` managed by opencode (never committed to or stored in the repository).
- **Configuration Path**: `~/.config/opencode/opencode.jsonc`
- **Supported Model IDs**:
  - `deepseek-ai/deepseek-v4-flash-0731` (default)
  - `z-ai/glm-5.2`
  - `nvidia/nemotron-3-ultra-550b-a55b`
  - `nvidia/nemotron-3.5-lightning-30b-a3b`
  - `stepfun-ai/step-3.7-flash`
  - `thinkingmachines/inkling`
- **Usage & Catalog Notes**:
  - The free tier is burst-limited, subject to HTTP 429 rate limits and has no SLA guarantees.
  - The `models.dev` catalog is stale; always refer to and use the live NVIDIA NIM catalog for current model availability.

### 2. Google AI Studio Fallback

- **Model ID**: `gemini-3.6-flash`
- **Rate Limit / Quota**: ~1500 requests/day
- **Usage Strategy**: Fallback provider used when NVIDIA NIM is saturated or rate-limited.

