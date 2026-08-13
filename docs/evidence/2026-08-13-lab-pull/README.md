# 2026-08-13 Lab Exit Pull — Manifest

Pulled 2026-08-13 ~20:02–20:05 (lab, user leaving for home) via tar-over-SSH
with user-provided passwords (transient askpass helper, deleted after use).
Laptop is the authoritative code copy; these are EXACT deployed-state snapshots
from the machines for home debugging.

## Sources

| Machine | User@IP | What was pulled |
|---|---|---|
| Jetson Nano | sravjti@192.168.55.1 (USB) | `~/` deployed WAN scripts + logs + pid files, `/tmp/mcq_sender_probe_errors.log`, `~/McQueen/data/spool` recordings |
| RTX 4090 (omen) | junior@192.168.0.132 (wired) | `/var/tmp/mcqueen-junior/` receiver scripts, broker.py, cloudflared state + logs, 15 lab receiver logs, `raw/` |

## Layout

- `jetson/` — exact copies of every WAN/GStreamer/control script, log, and pid
  file found in the Jetson home dir at pull time, plus `mcq_sender_probe_errors.log`.
- `rtx/` — exact copies of `/var/tmp/mcqueen-junior/` scripts, broker/cloudflared
  state, and all `gst_rtx_rtp_receiver_lab*.log` runs.
- Recordings: `data/lab_pull_20260813/jetson_spool/` (Jetson dataset spool,
  2 sessions) and `data/lab_pull_20260813/rtx_raw/` (RTX raw, 7.2M).

## Machine state at pull time (VERIFIED)

- Jetson: camera present (`/dev/v4l/by-id/usb-Sonix_..._Lenovo_FHD_Webcam...video-index0`).
  `mcqueen-edge.service` = **inactive** (was stopped for WAN work), enabled. Kernel
  4.9.253-tegra. Clone at `~/McQueen` on commit `61a3c91` (untracked `tools/realtime/kachow_probe.py`).
- RTX: broker.py RUNNING (health `{"ok": true}`), cloudflared RUNNING
  (URL at pull time: `https://disposition-cabinets-mariah-glad.trycloudflare.com`).
  Clone at `/var/tmp/mcqueen-junior/McQueen` on `8259460`.

## Findings from pulled evidence (2026-08-13)

### F1 — Sender NameError bug (CONFIRMED, FIXED on laptop copy)
`tools/realtime/gst_jetson_rtp_wan.py` (the 584-line cv2+x264 version, which
produced the 19:20 probe-error flood on the Jetson) had:

```python
if self.sent_pkts % 30 < n:   # NameError: 'n' is not defined
```

- `/tmp/mcq_sender_probe_errors.log` = 22,209 lines, ALL `NameError("name 'n' is not defined")`.
- The exception fires BEFORE `self.rtp_ts += self.rtp_ts_step`, so `rtp_ts` never
  advances → every frame sent with RTP timestamp 0 → `rtph264depay` on the RTX
  merges all frames into one AU (matches the "1 frame decoded / frames_rx 0" symptom).
- FIXED on the laptop copy: `% 30 == 0` (matches the older deployed sender, which
  was correct). Verify compile + unit test passed. **Must be redeployed to the
  Jetson next lab session.**

### F2 — RTX receiver lab16 crashed: wrong Python
`gst_rtx_rtp_receiver_lab16.log` (last run, 19:40):
`ModuleNotFoundError: No module named 'websocket'` — receiver was started with
system python. Per `run_direct_wan_test.sh` it must use
`/var/tmp/mcqueen-junior/gst-webrtc-venv/bin/python`.

### F3 — lab15 (4.6MB, 4m27s run): FU-A + AUD pattern
Receiver got `RTP_RX pkts=30 meta=30 frames_rx=29`, PLAYING OK, then
`rtph264depay` stuck in "waiting for start" with FU-A fragments
(`S 1, E 0` → `queueing`) and AUD (NAL type 9) packets — the exact orphan pattern
the sender comments say confused the depay. The newer sender (F1 fix applied)
drops AUD NALs; this log is from the older NVENC-era sender run.

### F4 — Deployed Jetson sender is OLDER than laptop copy
Jetson `~/gst_jetson_rtp_wan.py` (17:25, 411 lines, v4l2src/NVENC-era, correct
`% 30 == 0`) ≠ laptop `tools/realtime/gst_jetson_rtp_wan.py` (19:20, 584 lines,
cv2+x264 manual-packetization era). Laptop copy is newest; deploy it next time.
Receiver: deployed RTX copy md5 **identical** to laptop copy (b4cf4ee…).

### F5 — The exact buggy sender WAS on the Jetson (smoking gun)
Second copy found at `/tmp/gst_jetson_rtp_wan.py` = 584 lines, bug at line 414
(`% 30 < n`), md5 `ecd09a69…` = **byte-identical to the laptop's pre-fix copy**.
That is the version that ran at 19:20 and flooded `/tmp/mcq_sender_probe_errors.log`
(22,209 NameErrors). Pulled to
`jetson/jetson_extra_gst_jetson_rtp_wan.py` (UNFIXED snapshot for reference).
Also pulled: `jetson/sh/` (install_jetson_static.sh, preflight_jetson_webrtc.sh,
preflight.sh). At pull time a `gst_jetson_rtp_wan.py` process was STILL RUNNING on
the Jetson against the old dead tunnel URL — left running, harmless (dry-run).

### F6 — RTX receiver venv verified
`/var/tmp/mcqueen-junior/gst-webrtc-venv/bin/python` exists AND `import websocket`
works inside it — confirms F2 fix is purely "use the venv python".

## Next actions (home)
1. Diff/clean the laptop sender (fixed) vs deployed copies; redeploy sender + run
   `python3 gst_jetson_rtp_wan.py` on the Jetson next lab session.
2. Start RTX receiver with the **venv python** (F2).
3. Re-run full loop; watch for `SENT pkts` throttle + `rtp_ts` advancing.
