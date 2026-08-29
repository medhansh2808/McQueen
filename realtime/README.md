# McQueen realtime autonomy stack

The closed loop that drives the physical car: the Jetson streams camera frames
over the public internet to an RTX 4090, the 4090 runs the driving policy, and
control commands come back to the Jetson's GPIO actuator.

```
  JETSON NANO (ubuntu, user sravjti)          RTX 4090 (omen, user junior)
  ────────────────────────────────────        ──────────────────────────────
  camera (USB, by-id path)
        │ cv2 capture 640x480@30
        ▼
  gst_jetson_rtp_wan.py                       broker.py            :8765
    appsrc → queue(2, leaky) → x264 SW              ▲  websocket signalling
    → manual RTP packetization                      │
        │                                           │
        ├──── wss signalling ───────────────────────┘  (Cloudflare quick tunnel)
        │
        └──── punched UDP (STUN hole-punch, no ICE) ──► gst_rtx_rtp_receiver.py
                                                              │ I420 frame
                                                              ▼
                                                        policy_worker.py  :9801
                                                          ORT trunk (CUDA)
                                                          + trained action head
                                                              │
        ◄──── CTRL datagrams ─────────────────────────────────┘
        │
        ▼
  mcqueen_edge (UDP :5007) ──► GPIO servo + motor
```

## Which host runs what

| Host | Command | Brings up |
|---|---|---|
| RTX 4090 | `./realtime/rtx/start_stack.sh` | `broker.py` :8765, `policy_worker.py` :9801 (CUDA), `gst_rtx_rtp_receiver.py` |
| Jetson | `sudo ./realtime/jetson/go_autonomy_jetson.sh --broker-host HOST` | `mcqueen-edge-autonomy` (GPIO, :5007), `mcqueen-sender-autonomy` (camera → RTP) |

Start the RTX first — it prints the broker host the Jetson needs.

## Setup (once per host)

```bash
cp realtime/config.env.example realtime/config.env
$EDITOR realtime/config.env
```

`config.env` is gitignored. Every path, camera, servo trim, port and model
location lives there; **nothing is hardcoded in the tracked scripts**. The
launchers fail loudly with a named variable if something is unset or missing,
rather than starting half a stack.

The Cloudflare tunnel must already be running on the RTX:

```bash
"$MCQUEEN_RUNTIME_DIR/cloudflared" tunnel --url http://localhost:8765 \
    --no-autoupdate --logfile "$MCQUEEN_RUNTIME_DIR/broker-tunnel.log"
```

## Running

```bash
# --- RTX ---
./realtime/rtx/start_stack.sh
# ... ends with: run there: sudo ./realtime/jetson/go_autonomy_jetson.sh --broker-host abc-def.trycloudflare.com

# --- Jetson ---
sudo ./realtime/jetson/go_autonomy_jetson.sh --broker-host abc-def.trycloudflare.com
```

## Stopping the car — read this

```bash
sudo systemctl stop mcqueen-sender-autonomy mcqueen-edge-autonomy
```

Both children run as **transient systemd units**, not `setsid nohup … &`.

This is a safety fix, not a style preference. The old launcher spawned the edge
actuator with `setsid`, which reparents it to PID 1 with no systemd handle.
`systemctl stop mcqueen-edge` then only ever reached the *packaged*
`mcqueen-edge.service` instance — the hand-spawned process holding the GPIO kept
driving the motors, and there was no unit name to stop it by. Anything that
touches the actuator must be launched under `systemd-run` so that a single
`systemctl stop` is authoritative.

Note there are two distinct edge units, and they are not interchangeable:

- `mcqueen-edge.service` — packaged, `Restart=always`, holds the camera.
- `mcqueen-edge-autonomy` — transient, GPIO + `--no-record`, camera-less
  (the sender owns the camera during autonomy).

`go_autonomy_jetson.sh` stops the former before starting the latter.

## Verified behaviour

Measured 2026-08-26 on this hardware:

- Policy worker cold start: **~5 s** to `serving on 127.0.0.1:9801`.
- Trunk providers: `['CUDAExecutionProvider', 'CPUExecutionProvider']`, ~2.6 GB VRAM.
- Policy inference roundtrip, localhost, 640x480 I420: **min 8.6 / median 13.0 / max 16.8 ms**.
- The worker refuses to serve if the CUDA execution provider is missing
  (`policy_worker.py`), rather than silently falling back to CPU — a silent
  fallback previously poisoned both benchmarks and training feature spaces.

## Known gotchas

**The tunnel URL rotates on every `cloudflared` restart.** Nothing caches it:
`start_stack.sh` re-reads `broker-tunnel.log` each run, and
`go_autonomy_jetson.sh` refuses to start on an empty broker host instead of
dialing a dead one. Never copy a URL out of an old log or a `.last_report`.

**Steering polarity is hardware-verified, not derivable from the code.** The
physical linkage inverts pulse direction, so the sender applies a flip
(`gst_jetson_rtp_wan.py`) *and* `config.env` has `SERVO_LEFT_US > SERVO_RIGHT_US`.
These two cancel to the correct direction. Changing one without re-measuring the
other on the bench reverses the steering.

**`MCQUEEN_ONNX` points at a base filename that does not exist on disk.**
`rtx_policy_v1.py` appends `_ks` to get the ORT-patched trunk, which is the only
usable copy. `start_stack.sh` checks for the derived `_ks` file and fails early
if it is missing.

**Use the camera's `by-id` path, never `/dev/videoN`** — the numbering changes
across reboots and the sender will grab the wrong device.

## Layout

```
realtime/
  config.env.example   per-host config template (copy to config.env, gitignored)
  jetson/              runs on the Jetson Nano
    go_autonomy_jetson.sh
    gst_jetson_rtp_wan.py     camera → x264 → RTP → UDP; CTRL → edge
  rtx/                 runs on the RTX 4090
    start_stack.sh
    broker.py                 websocket signalling
    gst_rtx_rtp_receiver.py   RTP reassembly → policy → CTRL back
    policy_worker.py          isolated CUDA policy server (:9801)
    rtx_policy_v1.py          ORT trunk + trained action head
    make_ks_onnx.py           produces the _ks ORT-patched trunk
    stack_watchdog.sh         cron health check + relaunch
    udp_sink.py
  common/
    mini_stun.py              STUN hole-punch helper
  bench/               diagnostics, preflights and protocol tests
```

`policy_worker.py` runs the policy in its **own process** deliberately: ORT-CUDA
segfaults when initialised inside the GStreamer receiver alongside torch, so the
receiver never touches CUDA and talks to the worker over localhost TCP instead.
