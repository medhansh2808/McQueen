# AGENT_STATE.md — McQueen agent durable state

Updated: 2026-08-14 (LAB session 2e — wrap-up: all procs stopped, tasks deferred to tomorrow)

## Identity
- Agent: McQueen coding/repository engineering agent (contract: `AGENTS.md` at repo root).
- Scope: software engineering only. NOT part of the realtime driving loop.

## Machines (roles, not IPs)
- **Laptop** (`/home/kartik/McQueenWork/McQueen`): development, coding, Git, SSH/admin,
  debugging, offline replay/analysis, setup. System python3 = 3.10.12 (NO torch). Torch work
  uses `mcqueen-laptop` env (`/home/kartik/miniforge3/envs/mcqueen-laptop/bin/python`:
  3.12.13, torch 2.11.0+cu128, CUDA available — VERIFIED 2026-08-14).
- **Jetson Nano 2GB**: robot edge computer — camera capture, H.264 encode, teleop runtime,
  raw recording, frame IDs / monotonic timestamps, safety gate, actuator I/O. Ubuntu 18.04-era,
  old Python/GStreamer/NVIDIA stack — dependency changes must be conservative.
- **RTX 4090**: heavy ML/inference — video receive/decode, temporal-policy inference,
  direct-UDP action return, training/evaluation. COMMON machine (DECISION 014 hygiene rule).
  VERIFIED 2026-08-14: `omen`, i9-13900K (24C/32T), 62 GB RAM, venv gst-webrtc-venv GStreamer
  1.20.3 (rtpjitterbuffer: `drop-on-latency`, NO `drop-on-late`), avdec_h264 + nvcodec both
  present. GPU BUSY again (21:41 check): ViReL train.py PID 575347 (started 20:17, 90% util,
  20.4 GiB VRAM) — NOT McQueen's, UNTOUCHABLE (DECISION 014 + hard rule). Plan A (CPU
  decode/infer) is GPU-independent — jitter25 run proceeded sustained at 25.4 fps with GPU busy.

## Data flow (final desired runtime)
CAMERA → JETSON NANO → low-latency transport / WebRTC → RTX 4090 → autonomous-driving model
→ control return → JETSON SAFETY GATE → SERVO + MOTOR

## Realtime target
- Target: <100 ms end-to-end. **TARGET, NOT A PROVEN RESULT.**
- Proven (2026-08-11 lab): direct-WAN UDP control return 60/60 ACKs, p50 43.1 ms /
  p95 70.4 ms RTT (dry-run, zero GPIO).
- **FULL LOOP NOW MEASURED on separate WAN (2026-08-14 lab, hardware):** capture→
  encode→hotspot→internet→campus NAT→RTX decode→CPU infer→control return→Jetson, on the
  Jetson monotonic clock. Old hotspot: p50 391 ms / p95 1.67 s @ 400 kbps. New network:
  ~160 ms @ 30fps/400; fps ladder @150 kbps: 10→677, 15→478, 30→277 ms p50; 25 ms jitter
  ≈ 50 ms (281.9 vs 276.8 ms) → ~280 ms is wire/RTT, compute <10 ms. Bottleneck = link,
  pipeline proven (loss ~0% on the good link). <100 ms needs a better link (43 ms control
  RTT proven on the good route) — NOT yet achieved.

## Current working mode
- **LAB mode** (hardware-verification). **L0 FULL LOOP FLAWLESS + MEASURED (2026-08-14):**
  the 3 fixes + CPU path implemented on the reset-to-HEAD baseline; run script UNTOUCHED
  (F7/F8/F9 still in it by design — noted, not fixed per user order).
- **NEW NETWORK (user switched phone):** loss dropped to ~0% (frames 99.5%, META 0.6% loss,
  controls ~0%, EXACT_FRAME_MATCH 95–99%); latency p50: 30fps@400 → ~160 ms, 30fps@150 →
  224 ms. Bottleneck was the internet link, now fixed. Sender gained `--max-fps` (default 30
  = original path).
- **APPROVED 4-PART PLAN COMPLETE (2026-08-14):** (1) cleanup RTX+Jetson DONE, keep-list
  intact; (2) save-latency test DONE — `--save-frames` (JPEG+CSV, async writer), recv→decode→save
  p50 1.14 ms / p95 1.54 ms, 0 dropped, completeness 90.8%; (3) fps ladder + RTT probe DONE —
  10→677 ms, 15→478 ms, 30→277 ms p50 loop @150 kbps, link healthy all runs (RTT p50 46 ms)
  → sparse-traffic penalty CONFIRMED (NOT the link); true 20 fps impossible (30/N rates);
  30 fps = winner. (4) 25 ms jitter buffer @ 30fps — p50 281.9 ms / p95 425.4 ms ≈ identical
  to 50 ms (276.8/393) → jitter buffer was never the latency driver; ~280 ms is wire/RTT.
- **Dropped per user:** absolute capture→save latency (needs Jetson↔RTX clock offset — not
  worth the time). sync_calib.py written, kept untracked, not run to completion.
- **CLEANUP ROUND 2 COMPLETE (full sweep, user-approved):** removed git bundles (~50 MB),
  McQueen_files/, stale pids, old probe copies, __pycache__, old Aug 11–13 logs on both
  machines, tailscale/websocket install artifacts, ~/mcqueen scratch, ~/logs policy_server
  logs, gst_rtx_receiver_wan.pid. Kept: manual-punch tools (natprobe/punch_peer/
  rtp_loopback_test on Jetson /tmp — McQueen's own, relevant to broker removal), mcq_rtt
  probe logs (today's evidence), everything on the working pipeline keep-list. Verified
  post-sweep: sender/receiver/broker/cloudflared all alive, keep-list intact.
- **ERROR LOG created:** `docs/ERROR_LOG_2026-08-14.md` (F1/F2/F7/F8/F9/F10/F11/F12,
  drop-on-late crash, cd mistake, Q11 ws death, NAT re-point failure, NVDEC starvation,
  10-fps + jitter findings). User approved: include in next GitHub push.
- **EVIDENCE FILED (21:50):** `docs/evidence/2026-08-14/wan-loop-measured/` — all today's
  logs pulled (Jetson sender ×2, 5× mcq_rtt probes, RTX receiver/broker/cloudflared + url,
  2× meta.csv) + `REPORT.md` per MILESTONE_TEMPLATE. Numbers from logs: FULL_LOOP_LATENCY
  n≈48.6k p50 287.1 / p95 504.0 ms (30 fps @ 150 kbps, 25 ms jitter, Jetson clock);
  CONTROL_RETURN proven at scale (CTRL_RX n=48,650 — stage was inconclusive before);
  EXACT_FRAME_MATCH 52,095 ok / 3,287 miss (~94%); RTX_INFERENCE ~0.08 ms; VIDEO_FRAMES
  57.6k sustained @25.4 fps; save path p50 0.96 / p95 1.32 ms, 52,100 saved, 0 dropped.
  Deployed sender/receiver/inference_rtx/broker md5-IDENTICAL to laptop repo copies;
  **Jetson clone `kachow_probe.py` is STALE (old Aug 13 copy) — deploy repo version before
  the live Q1 probe**. Evidence rides the first hardware-verified commit (DECISION 013).
  Recordings (raw JPEGs) left on RTX (gitignored, not needed for commit/debug; 709 MB
  partial pull deleted).
- **Pending user decision:** broker removal (manual peer exchange) + <100 ms diagnostics
  (control-only RTT probe, 320×240 run) — BOTH DEFERRED TO TOMORROW (user heading home).
- **ALL test procs STOPPED** (sender/receiver/broker/cloudflared — precise PID kills,
  verified). Recordings stay on disk. Nothing running; machines idle.
- **BINDING at-home rule (user, 2026-08-14):** ANY code/script change at home (incl. fixing
  F7/F8/F9 in run_rtp_wan_test.sh) must be PROPOSED and await explicit user approval first.
  No GitHub today (DECISION 013) — everything rides tomorrow's hardware-verified commit.
- **Next (next lab, FINALIZED scope — transport/latency ONLY, home decision 2026-08-14):**
  (1) deploy + start pipeline; (2) **TRUE PATH RTT FIRST** — Jetson pings the RTX's actual
  public IP (NOT Cloudflare; decisive floor: ≈46 ms → <100 ms fightable on 4G, easy on
  Jio 5G; 100+ ms → link is the wall); (3) queueing attacks if worth it — 320×240 @
  150 kbps + packet pacing; (4) broker removal (manual peer exchange) if time allows;
  (5) kachow_probe live (Q1; deploy repo version — Jetson clone copy STALE); (6) record a
  REAL dataset (the real driving-data collection everything waits on); (7) FIRST
  hardware-verified commit (DECISION 013; reconcile origin `57561db`; includes
  docs/ERROR_LOG_2026-08-14.md + filed evidence); (8) L1 real inference ONLY after real
  dataset → policy TRAINED → L0 green → user approval.
- **NO TRAINED POLICY EXISTS (verified 2026-08-14):** only the PPGeo visual encoder
  (`ppgeo_visual_encoder.pth`, feature extractor — outputs features, NOT actuators) + 8
  old demo sessions (`data/jetson_recordings/`, user verdict: NOT real driving data).
  L1 `--inference real` cannot run until a temporal policy is trained on real recorded
  driving data. Training deferred until real dataset exists (no point training on old
  demos).
- **REAL SPEC (user):** on real roads, see current state via camera → actuator commands
  as fast as possible. <100 ms was aspirational, NOT a hard requirement. Ideal road link:
  Jio 5G (RTT ~10–30 ms → <100 ms comfortably achievable); 4G borderline (~60 ms floor).
- **Git (DECISION 013, binding):** NOTHING committed or pushed until hardware-verified.
  Local HEAD = `6632913`; origin/jetson-nano is 1 commit AHEAD (`57561db` "actaul audit",
  user-pushed via GitHub web — only edits docs/AUDIT_2026-08-13.md). All 2026-08-14 work
  (prep + today's run-script fixes F7/F8/F9) stays uncommitted locally. `.mcqueen/` state
  files ARE updated every session end regardless.
- **GITHUB RESTRUCTURE PLAN (approved by user, awaiting explicit GO — NOT executed):**
  (1) tag `pre-purge-2026-08-14` at HEAD `6632913` (recovery point); (2) reconcile origin
  `57561db` keeping the LOCAL AUDIT version (fixes "Jetson Sends" typo); (3) branch-only
  purge 52 files: `legacy/esp32/`, `legacy/uno_q_previous/`, `legacy/laptop_logger/`,
  `legacy/dataset_logging/`, `legacy/oakd/`, `hardware/cad/oakdmount.stl`; (4) commit ALL
  pending hardware-verified work; (5) push. EXCLUDE forever: `sync_calib.py` (untested) +
  "context stuff" folder. History IS the backup (user approved git-history approach over a
  local backup folder). Full plan + fresh-machine reproducibility task in CURRENT_TASK.md
  FUTURE WORK.
- **BINDING GITHUB RULE (user mandate 2026-08-14, added to AGENTS.md §J):** GitHub updates
  must ALWAYS keep the repo simple, functional, and maximally reproducible — remove
  superseded/dead code + old-hardware artifacts (branch-only), never add non-replication
  files, one clear documented run path, nothing non-McQueen.
- **FRESH-MACHINE REPRODUCIBILITY (future task, NOT true yet):** repo is clean code but
  "clone → simple command → working robot" does NOT work yet — missing verified setup
  runbook (Jetson/RTX/laptop), pinned deps, F7/F8/F9 fixes, checkpoint download doc,
  cloudflared fetch, KACHOW app build. Est. 1–2 h laptop + lab verify. Tracked in
  CURRENT_TASK.md FUTURE WORK.
- User rules: NO unattended Jetson/RTX access (every remote command needs explicit human
  authorization). **Passwords: user-provided, live ONLY in the transient helper
  `/tmp/mcq_askpass.sh` (SSH_ASKPASS) — NEVER in repo files (AGENTS.md §H); recreate helper
  or re-ask user if gone. RTX = common machine (DECISION 014).
- **HARD RULE (2026-08-14 lab):** ViReL train.py (PID 490867, /home/junior/ViReL/Tasks/vlmgrpo,
  ~/ViReL = vision-language GRPO training, NOT McQueen's) is UNTOUCHABLE. Never pause/kill/
  modify it or anyone else's processes. Plan A exists precisely to not need the GPU.
- The agent is NOT the driving model, not a safety device, never moves the vehicle without
  explicit human authorization.

## Session-start protocol (DECISION 007 — mandatory)
At every new session open: (1) run `.mcqueen/agent_startup_check.sh`; (2) read AGENTS.md +
`.mcqueen/` state files; (3) `git status`; (4) then work.

User trigger phrases (one is included at the start of every session — triggers the protocol
AND sets the working mode):
- "im at home" → HOME mode (software-validation, laptop-only, no hardware claims).
- "im at lab" → LAB mode (hardware-verification, Jetson/RTX available, remote work begins
  with per-command human authorization).

## Key constraints (see AGENTS.md for full contract)
- No fabrication; use VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / BLOCKED / FAILED / UNKNOWN.
- Exact frame identity (`frame_id` + `capture_mono_ns`) for all realtime association.
- Newest-frame-wins; stale predictions must not control the vehicle.
- Safety: steering 45–115 deg center 90, forward cap +100 PWM, reverse cap −70, prediction
  timeout 250 ms, stale → zero PWM + center steering + cancel AUTO.
- Jetson/RTX IPs change — discover/verify/inspect before acting.
- Do not commit datasets/weights/artifacts (`.gitignore` covers `data/`, `*.pt`, etc.).
- L1 (real-inference drop-in) is gated: only after run_rtp_wan_test.sh goes green AND user
  explicitly approves.