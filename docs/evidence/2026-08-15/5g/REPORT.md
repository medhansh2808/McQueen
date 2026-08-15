# REPORT — Jio 5G full-loop test (2026-08-15, lab + outside walk)

Status: **VERIFIED** (real hardware, real network). No clock timestamps — sequence/ordering only.

## Setup
- Jetson + camera + phone walked OUTSIDE to a spot showing 5G/5G++/5G++ (shifting, sometimes 4G).
- Power source: 10,000 mAh power bank (swap from wall Type-C; Jetson rebooted — handled).
- Resilient autostart wrapper (new `/home/sravjti/mcqueen_5g/`): waits for internet, starts sender
  on 5G config, append-logs every attempt, stall-kills + retries (no restarts needed — the hotspot
  link survived all mode shifts).
- RTX receiver stayed in the lab on the campus network; tunnel/broker unchanged
  (`carlo-booth-austin-pics.trycloudflare.com`). Laptop stayed in the lab on lab WiFi.
- Sender config: 300 kbps, 30 fps, same as the earlier 276.5 ms baseline run.

## Result
- Sender ran continuously through the whole walk (0 restarts, 0 stall-kills), 21,398+ frames sent.
- RTX received **49,369 frames, fps 20.6, assoc 46,094/48,378 (95.3%), ctrl_sent 46,094, infer 0.06 ms**.
- **Loop latency did NOT improve on 5G/5G++ — it got slightly worse.**
  - p50 trajectory over the run: best **~223-224 ms at the desk on stable 4G** (start), climbing
    through the walk: 235 @ line 101 → 243 @ 1001 → 253 @ 1501 → **257.7 ms at end**.
  - 5G++ spot window (log lines ~400-550, the ~90 s stand): p50 **~231-237 ms — statistically
    identical to stable 4G (~230 ms)**.
  - p95 **exploded to ~1239 ms** (mode-shifting radio caused long-tail queueing; earlier stable-4G
    runs had p95 ~380-486 ms).
- Verdict: on THIS phone/hotspot, 5G++ ≈ 4G for p50 and worse for the tail. The <100 ms loop is
  NOT achieved by switching to 5G on this link. The bottleneck is not the phone's 5G backhaul
  alone (RTT to 1.1.1.1 ~50 ms either way); the ~230 ms loop is queueing across the path.

## Files
- `sender.log` (full sender log, all segments, 3,150 lines — p50/p95 lines).
- `receiver.log` (RTX side tail).

## Follow-ups (recorded, not resolved)
- 5G does not solve <100 ms on this phone; candidates remain: pacing (spread frame packets,
  approved flags — future), 320x240 (smaller bursts), LAN-link demo day, better phone/hotspot.
- The mode-shift instability (5G↔5G++↔4G) is itself harmful (p95 1239 ms) — if 5G is attempted
  again, the phone must be forced to a single band and held stationary.