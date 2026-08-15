# CURRENT_TASK.md — McQueen active task

Updated: 2026-08-15 (session 2s — Jio 5G loop test VERIFIED: no improvement, worse tail; full cleanup; user leaving lab)

## OBJECTIVE (2-WEEK SPRINT, deadline = demo day)
Autonomous track demo with the trained policy, best-effort toward openpilot-style
generalization (DECISION 022). Drivetrain being redesigned NOW (encoder DC+quad motors,
gearbox + differential, drive-side only; steering servo FROZEN until post-demo). Plan:
hardware critical path (gearbox → bench → Q1 probe pass → 20-lap dataset) in parallel
with software de-risk (training rehearsal, app build, transport procedures). Lab
available all 14 days, ~4–8 h/day. Training runs on the RTX at training time (user to
confirm ViReL done first). Full 2026-08-14 lab-day context below remains valid.

## CURRENT STATE
- **SESSION 2s (2026-08-15) — Jio 5G loop test: VERIFIED NO improvement.** Jetson+camera+phone
  walked outside on a power bank to a 5G/5G++ spot (phone mode-shifted to 4G sometimes); RTX +
  laptop stayed in the lab; resilient autostart wrapper (`/home/sravjti/mcqueen_5g/`, append-log +
  stall-kill + retry) ran the sender through the whole walk (0 restarts). RTX: 49,369 frames,
  fps 20.6, assoc 95.3%. p50: best ~223-224 ms at desk on stable 4G; 5G++ spot ~231-237 ms (≈4G);
  cumulative end 257.7 ms; **p95 worsened to ~1239 ms** (mode-shifting). **5G++ ≈ 4G median, worse
  tail — <100 ms NOT achieved via 5G on this phone** (RTT ~50 ms either way; queueing is the wall).
  En-route fixes: Jetson `/tmp` is tmpfs (wiped on reboot → autostart moved to home dir);
  `mcqueen-edge.service` holds `/dev/video0` at boot (stopped for test, restored); F7-class
  pkill-in-cleanup → precise PID kills. Evidence `docs/evidence/2026-08-15/5g/`; ERROR_LOG entry
  F + AUDIT section 12. **Cleanup COMPLETE** (wrapper+cron removed, dir deleted, receiver stopped,
  edge active, tunnel up). NO commits (DECISION 013). Pacing/320×240 remain approved-but-future
  latency levers (user: "fck pacing for now, might do in future").
- **LAB COMPLETE (session 2r, 2026-08-15)** — ALL software de-risk items DONE and verified
  on real hardware:
  1. Smoke + rehearsal training on RTX CPU (GPU busy with neighbor `train.py` — untouched):
     `smoke_train_batch.py` PASS; `train_temporal_v2.py --backbone tiny --device cpu --epochs 20`
     → `/home/junior/mcqueen_run/rehearsal_temporal.pt` (36 MB, best_val 3.02).
  2. Inference chain w/ REAL ckpt on RTX: 10/10 + 18/18 tests; `--checkpoint` CPU infer
     6.59 ms/frame, servo=89.0 pwm=4. (CUDA path proven 444.75 ms single-frame while GPU busy.)
  3. Jetson deploy: repo sender + kachow_probe + RTT probe at clone (61a3c91) + /tmp.
  4. APP BUILT (27 s): `apps/android/KachowV8/app/build/outputs/apk/debug/app-debug.apk`.
     Install HELD until user says.
  5. **FULL WAN LOOP VERIFIED via STUN punch — port-forward theory RETRACTED** (wrong; see
     ERROR_LOG A): media/control are DIRECT punched UDP (receiver public
     `14.139.108.62:49995`/`:41820`/`:53591`, Jetson `152.59.109.96:59856`); cloudflared is
     ONLY the startup broker. Blocker was dead cloudflared + STALE URL (F8) → fresh tunnel
     `carlo-booth-austin-pics.trycloudflare.com` → **LAT_p50=276.5 ms / p95=486.7 ms**
     @300 kbps, fps 18.3, assoc ~94%, infer 0.12 ms (reproduces 2026-08-14).
  6. **Bitrate A/B 150/300/400×2 DONE** (5/6 + manual 400 rerun after transient ws 530):
     p50 stable ~270-280 ms across bitrates, fps 18-22, assoc ~94-96%, ctrl_rx in every run.
     Evidence `docs/evidence/2026-08-15/{REPORT.md,ab/}`. Script's 3 launch failures
     (ssh -t, pkill self-match, bracket self-match) → **PID-file kill/check** (F7-safe).
  7. Docs corrected to honest state: ERROR_LOG + AUDIT 2026-08-15 rewritten (root cause =
     dead tunnel/stale URL, FIXED; A/B failure chain; p95 tail note).
  8. Cleanup: all test procs stopped; **mcqueen-edge.service restored ACTIVE**; cloudflared
     tunnel left up for next session.
- **PENDING (user-leave wrap)**: Q13 proposal (receiver `--inference real` with tiny ckpt —
  separate approval); PPGeo training still waits for neighbor GPU job to finish; checkpoint
  copy-back to laptop `data/checkpoints/` if user wants; state files handoff-grade (this
  session's updates uncommitted — DECISION 013).
- **HOME PHASE COMPLETE (sessions 2m–2o, 2026-08-15)**: everything home-done and
  RE-VERIFIED — rehearsal A (5 datasets, 630 frames), trainer + smoke (lab-only), Chain C
  checkpoint inference (18/18+11/11 at 2m), A/B loss fix, RTT script, gradle prep
  (SHA-verified zip + wrapper jar + local.properties), DECISION 023/024 (zero torch on
  laptop), state files pristine. Leaving for lab — first gate on arrival: **ViReL PID
  575347 confirmation**.
- **SESSION 2n (home, 2026-08-15)**: DECISION 024 — the laptop froze a THIRD time on the
  lightest torch workload (single-batch GPU smoke, no backward) → **zero torch execution
  of any kind on the laptop, ever**. `smoke_train_batch.py` written + py_compile-verified,
  lab-only (first 4090 pre-flight). `run_bitrate_ab.sh` loss FIXED (frames-based via
  `meta=` vs `frames_rx` + assoc column). Gradle prep complete: gradle-9.4.1-bin.zip in
  `~/Downloads/` (SHA-256 verified `2ab2958f…6cb`), `gradle-wrapper.jar` fetched,
  `local.properties` created. User decisions: record dataset at **10 fps** (recorder is
  offline — zero live-latency impact; Q14 temporal-mismatch logged); **encoders: zero
  work** (wheels zeros consistent train/infer). Torch tests NOT re-run at home (last
  green = 2m); pure-python suite re-run green.
- **REHEARSAL DONE AT HOME (session 2m)**: chain A — 5 usable old sessions converted to
  LeRobot datasets `data/lerobot/rehearsal/<session>/` (630 frames / 6 episodes; 2 sessions
  empty, `session_20260810_133136` FAILED validation at 5.00 Hz — excluded); chain B —
  NEW trainer `mcqueen_ml/training/train_temporal_v2.py` written (dataset discovery,
  episode-level split, MSE on normalized actions, PPGeoResNet34 via MCQUEEN_PPGEO_CKPT or
  `--backbone tiny`, checkpoint dict with stats/history/image_size; resized image cache
  ~380 MB); NOT run on laptop (DECISION 023 — laptop froze twice under torch load). chain C —
  `tools/realtime/inference_rtx.py` now supports `--checkpoint` (backbone/denorm/history
  from ckpt; default random-tiny path unchanged): existing test 18/18 + new
  `test_checkpoint_inference.py` 11/11 PASS. Full suite green (protocol/drive/realtime-
  contract/temporal-policy/PPGeo-backbone). App build: SDK present (android-36, JDK 17, adb)
  but NO gradle dist/wrapper jar → deferred to lab. Transport scripts NEW + validated:
  `measure_true_path_rtt.py` (loopback smoke 30/30) + `run_bitrate_ab.sh` (bash -n OK).
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
- **GITHUB ORGANIZE DONE (home, session 2g + 2h):** first hardware-verified commit `8f35564`
  PUSHED (reconcile `57561db` + 52-file legacy purge + all verified work + evidence), then a
  second purge `30728e1` removed `robot/uno_q/` (pre-Jetson Uno Q project; cumulative purge
  = 61 files). Restructure TAG deferred — only on "do github restructure rn". State-file
  updates from this session are uncommitted (ride next hardware-verified commit).

## BLOCKER
- None hard. Neighbor GPU job (`train.py`, grpo-gsm8k-output) still occupies the 4090 →
  full PPGeo training deferred until it ends (user authorized CPU path meanwhile — done).
- PPGeo training, live `--inference real` (L1) and repo push all gated on user/next lab.

## NEXT ACTION
(EXACTLY ONE — at next session start)
1. **SET UP REMOTE-ACCESS INFRA (DECISION 026, approved 2026-08-15)** at the lab: Jetson
   cloudflared tunnel (TCP-capable for SSH — evaluate `--url tcp://` quick tunnel + 
   `cloudflared access tcp` client vs frp vs ngrok-TCP, pick on evidence, systemd service
   for reboot survival); same for RTX SSH; document client-side connect recipe in repo.
   Verified from home: RTX public IP `14.139.108.62` is static but campus firewall drops
   ALL inbound from home ISP (ports 22/80/443/8765/8080 all time out); RTX is ALIVE via
   its quick tunnel (resolves on 8.8.8.8/1.1.1.1, answers HTTP 404 — ws-only endpoint).
   Home DNS REFUSED trycloudflare lookups (local resolver quirk — use external DNS to
   check tunnels). Goal: home sessions can reach Jetson + RTX.
2. **PPGeo training** on the 4090 (GPU was free at session end — neighbor's old job
   finished; neighbor staging a new ViReL job — check before starting); checkpoint to
   `data/checkpoints/` + `MCQUEEN_PPGEO_CKPT`.
3. **Q13 PROPOSAL to user** (separate approval): receiver `gst_rtx_rtp_receiver.py`
   `--inference real` wired to the trained tiny checkpoint (6.59 ms/frame CPU path proven)
   for the demo loop; PPGeo live inference stays gated until real-data training (L1).
4. **User's hardware critical path** (unchanged): gearbox + differential + encoder motors →
   Q1 kachow_probe on final hardware → ~20-lap dataset at 10 fps (Tuesday target).
5. **Latency**: 5G ruled out (session 2s). Pacing/320×240 = approved flags, future work;
   LAN-link demo day is the practical path to <100 ms. Re-punch trick validation (TEST PLAN
   step 5) still pending for brokerless reliability.

## ACCEPTANCE CRITERIA (this session — all MET)
- Cleanup done with working pipeline untouched (KEEPLIST_INTACT verified). ✓
- Save-latency test: recv→decode→save p50 1.14 ms / p95 1.54 ms, 0 dropped, completeness 90.8%. ✓
- fps ladder + RTT probe: 10→677 / 15→478 / 30→277 ms p50; link healthy all runs; 30 fps winner. ✓
- 25 ms jitter buffer ≈ 50 ms (281.9 vs 276.8 ms) → buffer not the driver; ~280 ms = wire/RTT. ✓
- (NEW, home 2i) RESUME gate (protocol `R` + `resume_required`) implemented + laptop-tested. ✓

## TEST PLAN (next lab — FINALIZED scope: transport/latency ONLY; machines IDLE, pipeline stopped)
**No training, no real inference** — the 8 old demos are NOT real driving data (user verdict);
L1 stays gated until: record real driving data → train policy → then live inference.
1. Deploy repo sender + `kachow_probe.py` to the Jetson clone (drift fix — clone at
   `61a3c91`, kachow_probe copy STALE) + recreate askpass helper `/tmp/mcq_askpass.sh`;
   verify machines idle, procs stopped. Pipeline start: manual-start procedure documented
   (run_rtp_wan_test.sh still has F7/F8/F9 unless the user approves fixing them).
2. **TRUE PATH RTT FIRST (decisive diagnostic, ~10 min):** Jetson pings the RTX's ACTUAL
   public IP (`14.139.108.62`), NOT Cloudflare/1.1.1.1 (yesterday's 46 ms was to 1.1.1.1 —
   gap). If true RTT ≈ 46 ms → floor ≈ 60 ms, our ~200 ms is queueing to attack; if 100+
   ms → the link is the physics ceiling; know immediately instead of chasing code.
3. **BITRATE A/B (replaces the theory-based 150, DECISION 019):** 150 / 300 / 400 kbps,
   2.5 min each, 2 cycles, back-to-back on the same network. Per run log: sender achieved
   kbps, receiver frames_rx/fps, META + CTRL loss, EXACT_FRAME_MATCH, p50/p95. Pick the
   winner by data (latency + loss + quality-for-model — bitrate is also a model-visible
   quality floor, not just a latency knob). Do NOT trust 150 or 400 from memory. **Per run:
   BOTH sender + receiver logs saved into docs/evidence/<date>/ab/ (the 400-new-network
   loss was never logged — that gap must not recur; loss is computed, never estimated).**
4. **Queueing attacks (only if RTT + A/B say worth it):** 320×240 @ best-bitrate +
   packet pacing (spread pkts/frame, no micro-burst).
5. **RE-PUNCH TRICK VALIDATION (DECISION 019, ~15 min):** mid-session kill the Jetson
   hole (stop keepalives / rebind), verify the RTX hole stays alive via its keepalives,
   Jetson re-STUNs + sends NEWCAND to the RTX's known endpoint → recovery. Pass = the
   brokerless fallback is real; fail = reopen the broker question.
6. Live KACHOW probe: `tools/realtime/kachow_probe.py` — expect exit 0 (closes Q1);
   exit 3 → drive forward AND reverse, re-run. (Repo version deployed in step 1.)
7. If healthy: RECORD A REAL DATASET (the real driving-data collection the whole inference
   chain waits on) → `tools/realtime/process_recording.sh` (must print PASSED).
8. FIRST hardware-verified commit of ALL pending prep + lab work (DECISION 013), incl.
   docs/ERROR_LOG_2026-08-14.md + filed evidence + RESUME gate code; **broker.py removal
   from the repo rides this commit ONLY if step 5 passed**.
9. L1 (`--inference real`, PPGeo) ONLY after: real dataset recorded → policy TRAINED → L0
   green → user approval. **NO trained policy exists yet (verified 2026-08-14: only the
   PPGeo encoder + 8 old demos).** Checkpoint to `data/checkpoints` + `MCQUEEN_PPGEO_CKPT`.

**Constants (confirmed, don't touch):** 30 fps (winner: 277 ms vs 478/677 at 15/10), 50 ms
jitter buffer (25 ms measured identical — keep margin), CPU decode + CPU inference
(GPU-independent, ViReL-proof), newest-frame-wins, no retransmission, 250 ms timeout.
**Real spec (user):** on real roads, see current state via camera → actuator commands as
fast as possible. <100 ms was aspirational (NOT a hard spec); Jio 5G (RTT ~10–30 ms) makes
<100 ms comfortably achievable; 4G borderline (~60 ms floor + queueing).

## FUTURE WORK (restructure + reproducibility, user mandate 2026-08-14)
1. **GitHub restructure — PARTLY DONE, remainder DEFERRED to explicit GO ("do github
   restructure rn"):** purge of `legacy/` (esp32, uno_q_previous, laptop_logger,
   dataset_logging, oakd) + `hardware/cad/oakdmount.stl` (52 files, branch-only; history
   is the backup) + `robot/uno_q/` (9 files, `30728e1`), reconcile of origin `57561db`
   (local AUDIT version kept), commit of ALL
   pending hardware-verified work, and push — ALL COMPLETED in `8f35564`/`30728e1`. REMAINING on GO:
   recovery tag `pre-purge-2026-08-14` at `57561db` (the pre-purge point) + any further
   §J simplification. EXCLUDE forever: sync_calib.py + "context stuff" folder. NEW BINDING
   RULE added to AGENTS.md §J: GitHub updates must keep the repo simple, functional,
   maximally reproducible.
2. **Fresh-machine reproducibility (NOT true yet — honest):** anyone with same hardware +
   GitHub link should reproduce the project easily. Missing: (a) verified fresh-setup
   runbook (Jetson GStreamer/NVIDIA stack + mcqueen-edge.service, RTX gst-webrtc-venv,
   laptop env) — one doc with exact commands; (b) pinned dependencies (Jetson is Ubuntu
   18.04-era, old Python/GStreamer); (c) F7/F8/F9 run-script fixes (pkill self-kill,
   stale URL, sudo hang) — needs user approval; (d) checkpoint download + MCQUEEN_PPGEO_CKPT
   doc (weights stay OUT of repo, DECISION 015); (e) cloudflared binary fetch doc;
   (f) KACHOW app build-from-source. Estimated 1–2 h laptop work + next-lab verification.
3. **Re-punch watcher (road runtime, DECISION 019):** stdlib watcher — heartbeat detection
   (Jetson: CTRL cadence; RTX: frame cadence), on silence → re-STUN → NEWCAND to the RTX's
   stable endpoint (destination-independent NAT) → re-punch → resume. Validate the trick
   at the lab first (TEST PLAN step 5); then automate.
4. **Kachow RESUME button (app-side, DECISION 019):** code written (build/verify at lab) —
   button visible only in `resume_required` state, sends `R` packet over UDP 5007; gate
   already implemented + laptop-tested (protocol `R` + `resume_required`).
5. **Both-holes-dead fallback (DECISION 019):** RTX reboot/ISP rebind + Jetson rebind
   simultaneously — design ONLY when we face it; candidate answers: keepalive-stability
   (RTX powered at home), or a minimal public rendezvous at that time.

## STATUS
**2-WEEK SPRINT (session 2s, 2026-08-15): LAB PHASE COMPLETE + 5G experiment answered.**
All software de-risk items verified on real hardware (CPU rehearsal training, real-ckpt
inference chain 6.59 ms/frame, Jetson repo deploy, KACHOW APK built — install on hold,
full WAN loop via STUN punch p50 276.5 ms, bitrate A/B p50 stable 270-280 ms). Jio 5G test:
**NO latency improvement (p50 ~231-237 ms ≈ 4G; p95 worse to 1239 ms)** → <100 ms via 5G
ruled out on this phone; queueing across the path is the wall; pacing/320×240 remain approved
future levers; LAN-link demo day is the practical <100 ms path. Docs + evidence honest
(ERROR_LOG F, AUDIT 12, `docs/evidence/2026-08-15/5g/`). Machines cleaned: sender/wrapper/
receiver stopped, cron removed, `mcqueen_5g/` deleted, edge service ACTIVE, tunnel up. NO
commits (DECISION 013). Next: Q13 proposal, PPGeo training when neighbor GPU job (PID 744309)
ends, user's hardware path (gearbox → Q1 probe → 20-lap dataset).
