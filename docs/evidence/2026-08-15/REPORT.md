# REPORT — Transport full-loop + bitrate A/B (2026-08-15, lab)

Status: **VERIFIED** on real hardware (RTX 4090 `192.168.0.132`, Jetson Nano
`192.168.55.1` USB, Jetson on hotspot WAN, laptop WiFi). No clock timestamps —
ordering/sequence only.

## 1. Mechanism verified (corrects earlier port-forward theory)
- Receiver binds an ephemeral port (`0.0.0.0:0`), STUN-punches through campus NAT
  (endpoint-independent), peer sends directly to the punched public endpoint.
- NO port-forward needed/configured. Public endpoints observed (live, per run):
  receiver `14.139.108.62:49995` → `:41820` → `:53591`; Jetson `152.59.109.96:59856`.
- Media + control flow peer-to-peer over UDP; cloudflared serves ONLY the startup
  broker rendezvous (`wss://carlo-booth-austin-pics.trycloudflare.com`).
- Earlier claim "campus port-forward down = blocker" is RETRACTED (was dead
  cloudflared + stale URL; see `docs/ERROR_LOG_2026-08-15.md` entry A).

## 2. Full-loop run (300 kbps, pre-A/B)
- Sender (Jetson): `CTRL_RX n=960`, **LAT_p50=276.5 ms, LAT_p95=486.7 ms**.
- Receiver (RTX): `RTP_RX pkts=4530 meta=1069 frames_rx=1072`, fps 18.3,
  assoc_ok 941 / assoc_miss 78 (~94%), infer_avg 0.12 ms.
- Compare 2026-08-14 baseline: ~287 ms p50 @150 kbps — consistent.

## 3. Bitrate A/B (150/300/400 kbps x2, 25 s observe per run)
Logs: `ab/run_<BR>_<ITER>/{sender,receiver}.log`; machine summary `ab/summary.txt`.

| BR (kbps) | iter | frames_rx | loss_pct* | assoc_loss | control | loop p50 (ms) |
|-----------|------|-----------|-----------|------------|---------|---------------|
| 150 | 1 | 898 | 2.9 | 4.3 | yes | 270.2 |
| 150 | 2 | 966 | skew† | 4.0 | yes | (in log) |
| 300 | 1 | 944 | skew† | 6.3 | yes | (in log) |
| 300 | 2 | 981 | skew† | 6.1 | yes | (in log) |
| 400 | 1 | 975 | skew† | 6.9 | yes | (in log) |
| 400 | 2 | 10687 | 0.0 | 5.7 | yes | 279.3 |

\* `loss` = `100*(1 - frames_rx/meta)` sampled from log tails — snapshot skew
(receiver counts continuously, sender meta counter lags) yields negative values;
only run 150_1 (clean matched pair) has a physically meaningful number.
† skew artifact (see \*).
Run 400_2 was a manual rerun (30 s window) because the scripted 6th run hit a
transient websocket 530 on the cloudflared signaling (ERROR_LOG entry E).

## 4. Readouts
- Median full-loop latency stable **~270-280 ms** p50 across 150/300/400 kbps;
  fps 18-22; association (exact frame identity) ~94-96%; infer 0.10-0.15 ms.
- 400 kbps rerun: achieved 422 kbps on the wire; p95 spiked to 1587 ms (tail
  gaps, hotspot/campus congestion) — p50 unaffected.
- WAN baseline: Jetson→`14.139.108.62` ping avg 53.8 ms; LAN RTT probe
  laptop→RTX avg 3.36 ms (10/10).

## 5. Known script limitations (recorded, NOT silent)
- `full_loop` column grep fixed post-run (sender prints `LAT_p50=` on `CTRL_RX`
  lines, not `FULL_LOOP_LATENCY n=`); evidence logs themselves unaffected.
- Sender/receiver restarted per run via PID files (no pkill — F7-safe, see
  ERROR_LOG entry D).
