# HOME DEBUG 2026-08-13 — WAN video path: root causes pinned + what to test tomorrow

Offline analysis (laptop, no hardware) of the 2026-08-13 lab-exit evidence pull
(`docs/evidence/2026-08-13-lab-pull/`). Goal: make tomorrow's lab TEST-ONLY.
All conclusions are code/log-level; final proof requires the hardware run.

## 1. What the evidence proves (root causes, no speculation)

### The receiver-side "frames_rx" numbers were NOT decoded frames
`gst_rtx_rtp_receiver_lab13/14/15.log` show `RTP_RX pkts=N meta=N frames_rx=N-1`
climbing steadily (30→570). That counter counts UDP-layer MARKER bits, not
decoded frames. The old deployed sender set the marker bit on EVERY RTP packet
(`(96 << 1)` PT-byte bug) — so every packet looked like a complete frame to
the receiver. Decoded frames were ZERO (no `[RTX-GST] VIDEO` line in any lab
log).

### lab15: rtph264depay "waiting for start" — why
lab15 (4m27s, 25k lines) shows FU-A fragments (`S 1, E 0` → queueing) never
completing, interleaved with AUD NALs (type 9) that FLUSH the depay's fragment
assembly (`handle NAL type 9`). Result: the depay never assembled one full AU
→ "waiting for start" until the run was killed. Two old-sender defects:
  1. AUD NALs sent as standalone RTP packets (NVENC emits them; the new sender
     drops type-9 NALs in `_split_nals`).
  2. Marker bit on every packet (see above) → the depay flushed mid-fragment.

### The #19 "sender stalls after 1 frame" was the NVENC-era chain
`gst_jetson_rtp_wan_lab.log` (deployed 17:25, 411-line v4l2src/NVDEC/NVENC
sender) ends right after `===== NVMEDIA: NVENC ===== / H264: Profile = 66` —
the encoder never emitted a second frame. The NEW sender (584-line, committed)
removes the whole chain: cv2 capture (the PROVEN mcqueen-edge path) + software
x264enc (isolated test showed x264 flows while NVENC stalls). So #19 is
designed away, and:

### The new sender's capture→encode→probe chain ALREADY worked on the Jetson
`/tmp/mcq_sender_probe_errors.log` = 22,209 probe firings = ~12 minutes of
continuous cv2→appsrc→x264→h264parse→probe output on the Jetson (19:20 run).
The ONLY failure was the `% 30 < n` NameError in the SENT print, which froze
`rtp_ts` at 0 (F1). The 411-line deployed sender did NOT have F1 (its
`% 30 == 0` is correct) but used the stalling NVENC chain + GStreamer's
constant-ts rtph264pay.

## 2. Fixes made tonight (all in `tools/realtime/`, laptop copies)

| Change | File | What / why |
|---|---|---|
| F1: `% 30 == 0` (already committed in 6698d41) | gst_jetson_rtp_wan.py | rtp_ts now advances every frame |
| Refactor: probe → `_on_rtp_probe` (buffer map) → `handle_au` (frame logic) → `send_au` (packetization) | gst_jetson_rtp_wan.py | pure-Python path unit-testable offline; zero behavior change |
| NEW hardening: non-VCL AUs (SPS/PPS/SEI emitted as separate buffers by x264enc on some stacks) are held and prepended to the next VCL AU | gst_jetson_rtp_wan.py | exactly ONE capture entry + ONE rtp_ts step per video frame — keeps frame_id association exact (benchmark-v2 contract) even if x264 splits SPS/PPS |
| NEW offline unit test | tools/realtime/test_rtp_packetization.py | locks in: AUD drop, marker-only-on-last, FU-A S/E bits, per-frame ts, one-META-per-frame, non-VCL hold, F1 no-crash guard |
| Probe-error log reset + RESULT checks | run_rtp_wan_test.sh | resets `/tmp/mcq_sender_probe_errors.log` at deploy; RESULT shows probe-error count + last SENT (rtp_ts) + last VIDEO (frames_rx) lines |

## 3. Offline verification results (2026-08-13 evening, laptop)

- `python3 tools/realtime/test_rtp_packetization.py` — 6/6 PASS (incl. 100-frame F1 guard).
- `python3 tools/realtime/test_rtp_association.py` — PASS.
- `python3 -m py_compile tools/realtime/gst_jetson_rtp_wan.py gst_rtx_rtp_receiver.py` — OK.
- `bash -n tools/realtime/run_rtp_wan_test.sh` — OK.
- AST undefined-name scan of sender + receiver — no real undefined names (the
  5 flags were scanner false positives, verified line-by-line).
- `pytest tests/` — 18 passed (excluding torch env-blocked collector).

## 4. Tomorrow's hardware test checklist (lab, camera present, NO drivetrain)

Run in a REAL terminal (interactive SSH passwords):

```bash
./tools/realtime/run_rtp_wan_test.sh
```

Expected green: NAT punch ready=1, RTX decoded frames=1, Control returned=1,
Full-loop latency=1, Jetson error=0, RTX error=0, Probe errors=0.

Watch list (what each print means):

| Print | What it proves | Bad sign |
|---|---|---|
| `[JETSON-CAM] SENT pkts=… rtp_ts=…` | sender progressing; rtp_ts must INCREASE across lines | rtp_ts stuck at 0 → probe error (check /tmp/mcq_sender_probe_errors.log) |
| `[RTX-GST] RTP_RX pkts=… frames_rx=…` | packets arriving; frames_rx should track pkts closely (NOT +1-per-packet pattern of the old sender — 1 packet/frame is wrong) | frames_rx ≈ pkts (old marker-every-packet bug) |
| `[RTX-GST] VIDEO frames_rx=… fps=… assoc_ok=… assoc_miss=…` | DECODED frames (this is the one that matters) + association health | no VIDEO line → depay/decode still broken |
| `[JETSON-CAM] CTRL_RX n=… frame=…` | control returned to Jetson | none → RTX not decoding / no inference |
| `FULL_LOOP_LATENCY n=… p50=… p95=…` | end-to-end latency on Jetson clock | n=0 → no control returns |

If NOT green, in this order:
1. Probe errors > 0 → `tail /tmp/mcq_sender_probe_errors.log` on the Jetson.
2. No VIDEO but RTP_RX climbing → capture the receiver log with
   `GST_DEBUG=rtph264depay:5` and check for "waiting for start"/FU-A orphans
   (should be GONE with the new sender; if present, dump the sender's actual
   RTP bytes for one frame: the packetization test in the repo is the spec).
3. rtp_ts not advancing → sender probe path issue (log file).
4. x264 CPU: watch `SENT` cadence ≈ 30/s; if it lags, reduce to
   `speed-preset=superfast`/lower bitrate (640x480 was chosen for the 2GB RAM;
   NVENC is NOT usable — stalls on this camera chain).

Post-test: `sudo systemctl start mcqueen-edge.service` on the Jetson if the
edge recorder should be restored; copy the two result logs
(`/tmp/mcq_wan_jetson.log`, `/tmp/mcq_wan_rtx.log`) into the repo evidence
folder for the record.

## 5. What remains genuinely unknown until the hardware run
- End-to-end latency with the NEW sender (target <100 ms; control path alone
  already proved p50 43.1 ms).
- x264enc CPU headroom at 640x480@30 on the Nano 2GB.
- cv2 camera read cadence vs 30fps (MJPEG 640x480) — the recorder's proven
  capture path, but never through this sender.
- Whether h264parse emits SPS/PPS as separate buffers here (the new
  pending_non_vcl hardening makes either case correct — no action needed).
