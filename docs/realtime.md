# Realtime inference (`realtime/`)

The realtime stack connects the Jetson sender to the RTX receiver/policy worker over **direct peer-to-peer UDP**, with NAT punched by a STUN round-trip. Configuration is per-host via `config.env` (copy from `config.env.example`; `config.env` itself is gitignored).

## Layout

```
realtime/
├── jetson/          # on-car sender
│   ├── gst_jetson_rtp_wan.py     # camera + H.264 + RTP push
│   └── go_autonomy_jetson.sh     # sender launcher (systemd-run friendly)
├── rtx/             # inference side
│   ├── gst_rtx_rtp_receiver.py  # RTP receive + decode
│   ├── policy_worker.py          # prediction loop (feeds the policy)
│   ├── rtx_policy_v1.py          # corridor policy: frozen supercombo trunk + trained head
│   ├── broker.py                 # NAT-punch / discovery signaling (aiohttp)
│   ├── udp_sink.py               # control return over UDP
│   ├── start_stack.sh            # RTX stack launcher
│   └── stack_watchdog.sh         # watchdog for the stack
├── common/
│   └── mini_stun.py              # minimal STUN server for NAT punch
├── bench/                        # benchmark and contract-test scripts
└── config.env.example            # per-host configuration template
```

## Flow

1. `broker.py` exchanges signaling so the peers learn each other's public endpoints; `mini_stun.py` (or any STUN server) punches the NAT hole.
2. `gst_jetson_rtp_wan.py` H.264-encodes the camera and pushes RTP over the punched UDP path, tagging each frame with `frame_id` + `capture_monotonic_ns`.
3. `gst_rtx_rtp_receiver.py` decodes and `policy_worker.py` runs `rtx_policy_v1.py` on a 6-frame window + previous actions + encoder state.
4. The prediction `(servo_angle_deg, pwm255)` is returned over direct UDP to the edge control port (`:5007`).

## Configuration

```bash
cp realtime/config.env.example realtime/config.env   # then edit
```

Key variables: `MCQUEEN_SESSION` (must match on both peers), `MCQUEEN_BROKER_HOST` (leave empty on the RTX — `start_stack.sh` reads the live tunnel URL), servo trims, bitrate, and interpreter paths.

## Benchmarks

`realtime/bench/` contains end-to-end contract tests and latency/bitrate benchmarks (`run_rtp_lan_test.sh`, `run_rtp_wan_test.sh`, `measure_true_path_rtt.py`, …).