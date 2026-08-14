# Milestone Report — wan-loop-measured

## 1. Identity

- Milestone: `wan-loop-measured`
- Date: 2026-08-14 (lab)
- Machine(s): Jetson Nano (sender, capture→encode→punch), RTX 4090 `omen` (receiver,
  CPU decode + CPU dummy inference + control return), laptop (orchestration; evidence
  pulled to laptop)
- Repo commit: local HEAD `6632913` (uncommitted 2026-08-14 work, DECISION 013 —
  hardware-verified commit pending; origin/jetson-nano `57561db`, 1 ahead)
- Test performed with drivetrain: `disconnected` (teleop path only; zero GPIO)

## 2. Stage measurements

Numbers extracted from the filed logs (see section 3). `n` = samples that reached
the stage; p50/p95 in ms where applicable.

| Stage | n | p50 (ms) | p95 (ms) | Result |
|---|---|---|---|---|
| SIGNALING_P2P | 1 | — | — | VERIFIED (`SIGNALING_P2P READY peer=152.58.29.56:54973`) |
| VIDEO_CONNECTED | 1 | — | — | VERIFIED (`DIRECT_UDP_READY peer=14.139.108.62:56741`, punched UDP, no ICE) |
| VIDEO_FRAMES | 57,641 | — | — | VERIFIED (frames_rx climbing throughout the run, fps 25.4 sustained) |
| FRAME_TIMESTAMP | — | — | — | VERIFIED (rtp_ts advances; capture_mono_ns echoed per frame) |
| EXACT_FRAME_MATCH | 52,095 ok / 3,287 miss | — | — | VERIFIED (~94 % exact assoc, honest WAN-loss misses) |
| RTX_INFERENCE | 52,095 | 0.08 | — | VERIFIED (CPU dummy infer, infer_avg 0.06–0.10 ms) |
| DIRECT_UDP | 242,910 pkts | — | — | VERIFIED (RTP + META over punched UDP) |
| CONTROL_RETURN | 48,650 | 287.1 | 504.0 | VERIFIED (Jetson `CTRL_RX n=48630…` every control; previously inconclusive) |
| SAFETY_GATE | — | — | — | UNVERIFIED (Jetson-side; servo=90.0 pwm=0 observed with no throttle; kachow probe pending, Q1) |
| FULL_LOOP_LATENCY | ~48,650 | 287.1 | 504.0 | VERIFIED (25 ms jitter run, 30 fps @ 150 kbps, Jetson monotonic clock) |

Loop context: 30 fps @ 150 kbps on the new phone network. Ladder (separate runs,
same network, RTT probe healthy at p50 46 ms): 10→677, 15→478, 30→277 ms p50 —
sparse-traffic penalty, 30 fps is the winner. 25 ms vs 50 ms jitter buffer:
281.9 vs 276.8 ms p50 → jitter buffer never was the latency driver; ~280 ms is
wire/RTT. Save path: recv→decode→save p50 0.96 / p95 1.32 ms, SAVED n=52,100,
dropped=0, completeness vs received 90.8 % (lost-META frames not saved by design).

## 3. Artifacts filed

| Artifact | Path in this folder | Source machine |
|---|---|---|
| sender log (final jitter25 run) | `gst_jetson_rtp_wan_j25.log` | Jetson `/tmp` |
| sender log (earlier lab run) | `gst_jetson_rtp_wan_lab.log` | Jetson `/tmp` |
| link RTT probes (ladder runs) | `mcq_rtt_{10,15,20,30,30b}.log` | Jetson `/tmp` |
| receiver log (full session) | `gst_rtx_rtp_receiver_lab.log` | RTX `/var/tmp/mcqueen-junior` |
| broker log | `broker_lab.log` | RTX |
| cloudflared log | `cloudflared_lab.log` | RTX |
| live tunnel URL | `cloudflared.url` | RTX |
| save-path frame timestamps | `meta_save_test_201750.csv` | RTX recordings |
| jitter25 frame timestamps | `meta_jitter25_204850.csv` | RTX recordings |

Deployed-code comparison (md5): sender, receiver, inference_rtx,
broker byte-IDENTICAL to laptop repo copies; Jetson clone `kachow_probe.py` DIFFERS
(stale Aug 13 copy — deploy repo version before the live probe, Q1).

## 4. Verification notes

- Latency: Jetson monotonic clock, per-control `LAT_p50/p95` over n≈48.6k controls.
- Frame identity: `frame_id` + `capture_mono_ns` association, `assoc_ok`/`assoc_miss`
  counted on the receiver; no FIFO assumptions.
- Newest-frame-wins: receiver engine buffer behavior (see receiver log).
- Stale-command handling: prediction timeout 250 ms, stale → zero PWM + center +
  cancel AUTO (Jetson safety gate, not exercised — zero teleop).
- Safety gate: not driven; kachow probe (Q1) pending pipeline-flawless run.
- Bitrate: `bitrate=150 kbps` — measured sweep result (Fix 3), not the old 2500 guess.
- Deviations: ViReL train.py (PID 575347, NOT McQueen's) running at 90 % GPU on RTX
  during the day — sidestepped by Plan A (CPU decode + CPU infer); pipeline GPU-free.

## 5. Verdict

- `PARTIALLY VERIFIED` — transport, decode, inference, control return and full-loop
  latency all measured at scale on real WAN. Residual: ~280 ms loop is link-bound
  (target <100 ms needs a better link; 43 ms control RTT proven on the good route),
  SAFETY_GATE stage needs the live kachow probe (Q1).

## 6. Next action

At next lab: live `kachow_probe.py` (deploy repo version — Jetson clone copy is stale),
close Q1, then make the FIRST hardware-verified commit (reconcile origin `57561db`)
including this evidence.
