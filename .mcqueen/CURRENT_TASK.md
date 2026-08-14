# CURRENT_TASK.md — McQueen active task

Updated: 2026-08-14 (LAB day COMPLETE — session 2e wrap-up; user heading home)

## OBJECTIVE
Lab day: 3 fixes live + full-loop measured, approved 4-part plan (cleanup, save-latency,
fps ladder + RTT probe, 25 ms jitter) COMPLETE, cleanup full sweep done, error log
created, all procs stopped. NO commit today (DECISION 013). Tomorrow: broker removal +
<100 ms diagnostics + first hardware-verified commit.

## CURRENT STATE
- Approved plan COMPLETE (all 4 items, hardware-verified live):
  1. **Cleanup** — round 1 (old WAN scripts) + round 2 FULL SWEEP (user-approved): git
     bundles ~50 MB, McQueen_files/, stale pids, old probe copies, __pycache__, old
     Aug 11–13 logs, install artifacts, ~/mcqueen scratch, ~/logs policy_server logs all
     removed from both machines. KEEPLIST_INTACT re-verified (receiver/broker/cloudflared/
     sender alive; clone + edge service + data + HF cache + current tools present). Manual
     punch tools (natprobe/punch_peer/rtp_loopback_test) + mcq_rtt evidence kept.
  2. **Save-latency test**: `--save-frames` (opt-in, default off) on receiver — JPEG every
     frame + meta.csv (frame_id, capture_mono_ns, recv_mono_ns, save_mono_ns), async writer.
     recv→decode→save p50 1.14ms / p95 1.54ms; 5,277 saved / 5,270 assoc ≈ 100% (0 dropped);
     completeness vs received 90.8% (lost-META frames not saved by design).
  3. **FPS ladder + RTT probe** (same network, 150 kbps, ping 1.1.1.1 each run): 10→677ms,
     15→478ms, 30→277ms p50 loop. Link healthy every run (RTT p50 46ms) → sparse-traffic
     interaction CONFIRMED (NOT the link): 30 fps is the winner. True 20 fps impossible from
     a 30 fps camera (30/N rates only).
  4. **25 ms jitter buffer @ 30fps** (`--jitter-ms` flag, default 50 = unchanged): loop
     p50 281.9ms / p95 425.4ms — statistically identical to 50 ms (276.8/393) → jitter
     buffer was never the latency driver; ~280 ms is wire/RTT. SAVED n=21,400, 0 dropped.
- Full-loop latency on this network is now ~280 ms p50 at 30fps@150kbps (vs 391 ms old net,
  160 ms earlier today on the better link at 400 kbps — link-dependent, pipeline proven).
- DROPPED per user: absolute capture→save (needs Jetson↔RTX clock offset; not worth the
  time now). sync_calib.py written but not run to completion — kept in repo as untracked.
- **ERROR LOG:** `docs/ERROR_LOG_2026-08-14.md` created (all today's errors + findings),
  user-approved to include in the next GitHub push.
- **PENDING (deferred to TOMORROW, user decision):** broker removal via manual peer
  exchange (punch_peer.py tooling already exists on the Jetson) and <100 ms diagnostics
  (control-only RTT probe + 320×240 run). Estimates: broker removal ~1.5–2.5 h total
  (code ~1 h at home, live verify ~30–45 min lab); diagnostics ~30–45 min.
- **ALL test procs STOPPED** (sender/receiver/broker/cloudflared — precise PID kills,
  verified; machines idle). Recordings stay on disk (save_test_201750/, jitter25_204850/).
  No GitHub today (DECISION 013).

## BLOCKER
- None for today's plan. Next hardware milestone: L0 green already achieved this session
  (all benchmark-v2 stages live). Pending: user green-light for the FIRST hardware-verified
  commit of all prep work (DECISION 013).

## NEXT ACTION
(EXACTLY ONE)
- TOMORROW at lab (user-approved scope): (1) broker removal — code needs user approval
  (at-home rule: always ask + wait first), then live verify; (2) <100 ms diagnostics —
  control-only RTT probe (punch_peer.py) + 320×240 run; (3) evidence filing + kachow_probe
  (Q1); (4) first hardware-verified commit incl. docs/ERROR_LOG_2026-08-14.md (reconcile
  origin `57561db`).

## ACCEPTANCE CRITERIA (this session — all MET)
- Cleanup done with working pipeline untouched (KEEPLIST_INTACT verified). ✓
- Save-latency test: recv→decode→save p50 1.14 ms / p95 1.54 ms, 0 dropped, completeness 90.8%. ✓
- fps ladder + RTT probe: 10→677 / 15→478 / 30→277 ms p50; link healthy all runs; 30 fps winner. ✓
- 25 ms jitter buffer ≈ 50 ms (281.9 vs 276.8 ms) → buffer not the driver; ~280 ms = wire/RTT. ✓

## TEST PLAN (next lab — FINALIZED scope: transport/latency ONLY; machines IDLE, pipeline stopped)
**No training, no real inference** — the 8 old demos are NOT real driving data (user verdict);
L1 stays gated until: record real driving data → train policy → then live inference.
1. Deploy + start the pipeline (broker/cloudflared + receiver venv python + sender) —
   manual-start procedure documented (run_rtp_wan_test.sh still has F7/F8/F9 unless the
   user approves fixing them; at-home rule: ask + wait before ANY change).
2. **TRUE PATH RTT FIRST (decisive diagnostic, ~10 min):** Jetson pings the RTX's ACTUAL
   public IP (NOT Cloudflare — that was today's gap). If true RTT ≈ 46 ms → floor ≈ 60 ms,
   <100 ms fightable on 4G, easy on Jio 5G (ideal road link, user). If 100+ ms → the link
   is the wall; know immediately instead of chasing code.
3. **Queueing attacks (only if floor says worth it):** 320×240 @ 150 kbps (smaller bursts,
   less uplink queueing; inference unaffected — model resizes to 224×224 internally) +
   packet pacing (spread 4.2 pkts/frame, no micro-burst).
4. Broker removal: manual peer exchange (punch_peer.py exists; code needs user approval
   first) → live verify (~1.5–2.5 h incl. debugging). Deferred if time is short.
5. Live KACHOW probe: `tools/realtime/kachow_probe.py` — expect exit 0 (closes Q1);
   exit 3 → drive forward AND reverse, re-run. **Deploy repo version first — Jetson clone
   copy is STALE (noted in evidence REPORT).**
6. If healthy: RECORD A REAL DATASET (this is the real driving-data collection the whole
   inference chain waits on) → `tools/realtime/process_recording.sh` (must print PASSED).
7. FIRST hardware-verified commit of ALL pending prep + lab work (DECISION 013), incl.
   docs/ERROR_LOG_2026-08-14.md + the filed evidence; reconcile origin `57561db` (AUDIT doc
   local-vs-remote).
8. L1 (`--inference real`, PPGeo) ONLY after: real dataset recorded → policy TRAINED → L0
   green → user approval. **NO trained policy exists yet (verified 2026-08-14: only the
   PPGeo encoder + 8 old demos).** Checkpoint to `data/checkpoints` + `MCQUEEN_PPGEO_CKPT`.

**Constants (confirmed, don't touch):** 30 fps (winner: 277 ms vs 478/677 at 15/10), 50 ms
jitter buffer (25 ms measured identical — keep margin), CPU decode + CPU inference
(GPU-independent, ViReL-proof), newest-frame-wins, no retransmission, 250 ms timeout.
**Real spec (user):** on real roads, see current state via camera → actuator commands as
fast as possible. <100 ms was aspirational (NOT a hard spec); Jio 5G (RTT ~10–30 ms) makes
<100 ms comfortably achievable; 4G borderline (~60 ms floor + queueing).

## FUTURE WORK (restructure + reproducibility, user mandate 2026-08-14)
1. **GitHub restructure (approved plan, awaiting user GO):** purge `legacy/` (esp32,
   uno_q_previous, laptop_logger, dataset_logging, oakd) + `hardware/cad/oakdmount.stl`
   (branch-only, 52 files; recovery via tag `pre-purge-2026-08-14` at HEAD `6632913`),
   reconcile origin `57561db` (keep local AUDIT version — fixes "Jetson Sends" typo),
   commit ALL pending hardware-verified work, push. EXCLUDE: sync_calib.py + "context
   stuff" folder. NEW BINDING RULE added to AGENTS.md §J: GitHub updates must keep the
   repo simple, functional, maximally reproducible.
2. **Fresh-machine reproducibility (NOT true yet — honest):** anyone with same hardware +
   GitHub link should reproduce the project easily. Missing: (a) verified fresh-setup
   runbook (Jetson GStreamer/NVIDIA stack + mcqueen-edge.service, RTX gst-webrtc-venv,
   laptop env) — one doc with exact commands; (b) pinned dependencies (Jetson is Ubuntu
   18.04-era, old Python/GStreamer); (c) F7/F8/F9 run-script fixes (pkill self-kill,
   stale URL, sudo hang) — needs user approval; (d) checkpoint download + MCQUEEN_PPGEO_CKPT
   doc (weights stay OUT of repo, DECISION 015); (e) cloudflared binary fetch doc;
   (f) KACHOW app build-from-source. Estimated 1–2 h laptop work + next-lab verification.

## STATUS
LAB DAY COMPLETE — all procs stopped, evidence filed to laptop (21:50), state handoff-grade.
**ViReL train.py is BACK on RTX (PID 575347, 90 % GPU) — untouchable; Plan A CPU path proven
GPU-independent.** Tomorrow: broker removal + diagnostics + kachow_probe (Q1) + first
hardware-verified commit (with user approval at each step)
