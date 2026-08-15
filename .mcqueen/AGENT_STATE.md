# AGENT_STATE.md — McQueen agent durable state

Updated: 2026-08-15 (session 2s — Jio 5G loop test VERIFIED: no improvement, worse tail; full cleanup; user leaving lab)

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
  First hardware-verified commit DONE tonight (`8f35564`, pushed); any NEW changes ride the
  NEXT hardware-verified commit.
- **Next (next lab, FINALIZED scope — transport/latency ONLY, home decision 2026-08-14):**
  (1) deploy repo sender + kachow_probe to Jetson (drift fix; clone copy STALE) + recreate
  askpass helper; (2) **TRUE PATH RTT FIRST** — Jetson pings the RTX's ACTUAL public IP
  (`14.139.108.62`), NOT 1.1.1.1/Cloudflare (decisive floor: ≈46 ms → our queueing is the
  wall to attack; 100+ ms → link is the physics ceiling); (3) **BITRATE A/B** (150/300/400
  kbps ×2 cycles, same network back-to-back, per-run loss+frames_rx+p50/p95 logged — the
  400-run loss gap from 2b must never recur; 150 is NOT final — 400 gave p50 ~160 ms on
  the new network vs 224–287 at 150); (4) 320×240 + pacing ONLY if the floor justifies;
  (5) **re-punch trick validation** (kill hole mid-session → rebind → NEWCAND recovery —
  proves the brokerless fallback, DECISION 019); (6) kachow_probe live (Q1); (7) record a
  REAL dataset (the real driving-data collection everything waits on); (8) FIRST
  hardware-verified commit (DECISION 013; broker.py removal rides it ONLY if re-punch
  validation passed); (9) L1 real inference ONLY after real dataset → policy TRAINED →
  L0 green → user approval.
- **BROKER POLICY (DECISION 019):** brokerless for lab AND road sessions. Fallback = the
  re-punch trick (NAT mappings are destination-independent — RTX's hole stays alive via
  keepalives; Jetson re-STUNs and sends NEWCAND to the RTX's stable endpoint through the
  still-open mapping). No broker rewrite, no aiohttp, no cloudflared. Both-holes-dead =
  FUTURE TASK (fix when faced). Re-punch watcher = FUTURE TASK (road runtime).
- **RESUME RE-ENGAGE (DECISION 019, implemented this home session):** watchdog/link-loss
  stops set gate `resume_required`; Kachow app gets a one-tap RESUME button (visible only
  in that state) → sends `R` packet → gate clears → existing neutral-before-motion applies.
  Manual E-stop does NOT require RESUME. Jetson-side code + tests done at home (rides next
  hardware-verified commit); app button code-only (build/verify at lab).
- **NO TRAINED POLICY EXISTS (verified 2026-08-14):** only the PPGeo visual encoder
  (`ppgeo_visual_encoder.pth`, feature extractor — outputs features, NOT actuators) + 8
  old demo sessions (`data/jetson_recordings/`, user verdict: NOT real driving data).
  L1 `--inference real` cannot run until a temporal policy is trained on real recorded
  driving data. Training deferred until real dataset exists (no point training on old
  demos).
- **REAL SPEC (user):** on real roads, see current state via camera → actuator commands
  as fast as possible. <100 ms was aspirational, NOT a hard requirement. Ideal road link:
  Jio 5G (RTT ~10–30 ms → <100 ms comfortably achievable); 4G borderline (~60 ms floor).
- **Git (DECISION 013):** FIRST HARDWARE-VERIFIED COMMIT DONE — `8f35564` pushed to
  origin/jetson-nano (`57561db..8f35564`, sync 0/0, VERIFIED). Includes: all H1–H5 prep,
  lab fixes, 14-file milestone evidence, day AUDIT/ERROR_LOG, handoff-grade state files,
  and the branch-only purge (52 files: `legacy/{esp32,uno_q_previous,laptop_logger,
  dataset_logging,oakd}/` + `hardware/cad/oakdmount.stl` — history is the backup) plus a
  SECOND purge `30728e1` (9 files: `robot/uno_q/` pre-Jetson Uno Q project; `robot/
  jetson_nano/` KEPT — current edge).
  Passwords STRIPPED from state files before commit (AGENTS.md §H). Only untracked:
  `tools/realtime/sync_calib.py` (untested, EXCLUDED forever) + "context stuff" folder
  (never commit). `.mcqueen/` state files ARE updated every session end regardless.
- **GITHUB RESTRUCTURE (deferred — run ONLY on the trigger phrase "do github restructure rn"):**
  the purge + first commit + push are DONE (user ordered deletions + push separately).
  What REMAINS for the explicit GO: create recovery tag `pre-purge-2026-08-14` at `57561db`
  (pre-purge point; history keeps everything either way) + any further repo simplification
  per AGENTS.md §J. EXCLUDE forever: `sync_calib.py` (untested) + "context stuff" folder.
  Full plan + fresh-machine reproducibility task in CURRENT_TASK.md FUTURE WORK.
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
- **HARD RULE (2026-08-14 lab):** ViReL train.py (PID 575347 — current 2026-08-14 evening;
  earlier PID 490867 superseded, same job, cwd /home/junior/ViReL/Tasks/vlmgrpo,
  ~/ViReL = vision-language GRPO training, NOT McQueen's) is UNTOUCHABLE. Never pause/kill/
  modify it or anyone else's processes. Plan A exists precisely to not need the GPU.
- The agent is NOT the driving model, not a safety device, never moves the vehicle without
  explicit human authorization.

## 2-WEEK SPRINT (DECISION 022, 2026-08-15)
- **Deadline**: demo day in 2 weeks; lab available all 14 days ~4–8 h/day. Demo bar:
  best-effort openpilot-style, honest floor = smooth autonomous track laps (teleop
  takeover ready); NO new-environment generalization claim.
- **Hardware (user critical path)**: drivetrain redesign — encoder DC+quadrature motors,
  gearbox + differential (drive-side only), 3D-printed gears failed 4–5× so far; steering
  servo FROZEN until post-demo (label/hardware 1:1 rule). Then bench-verify → **Q1
  kachow_probe MUST pass on final hardware** → record ~20 laps (env questions asked at
  recording time).
- **Software de-risk (agent, laptop-only, care protocol)**: training rehearsal (old demos
  → train → checkpoint → MCQUEEN_PPGEO_CKPT → --inference real smoke), Kachow build,
  transport procedure scripts (new files). Nothing on the working pipeline touched;
  no commits (DECISION 013).
- **Training compute**: RTX 4090 at training time (user states resources available then;
  ViReL PID 575347 untouchable until user confirms done).
- **Care protocol (binding)**: sacred list = run_rtp_wan_test.sh, deployed machine copies,
  teleop path, recorder/process_recording.sh, sender/receiver behavior — per-change
  approval required; new work in NEW files first; full test suite after every change.

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

## Session 2m (2026-08-15, HOME) — sprint de-risk state
- **DECISION 023 (binding)**: NO training on the laptop (froze twice under torch load;
  7.6 GB RAM total). Training runs at lab on RTX 4090 after user confirms ViReL done.
- **Training rehearsal**: chain A done (5 sessions → LeRobot datasets, 630 frames/6 eps,
  `data/lerobot/rehearsal/<session>/`); chain B trainer `mcqueen_ml/training/train_temporal_v2.py`
  written, import/argparse/py_compile verified (NOT run — DECISION 023); chain C done —
  `tools/realtime/inference_rtx.py` gains `--checkpoint` (backbone/denorm from ckpt, default
  random-tiny unchanged), new `test_checkpoint_inference.py` 11/11 + existing 18/18 PASS.
- **App build**: SDK present (android-36, JDK 17, adb) but NO gradle dist/wrapper jar →
  lab: fetch gradle-9.4.1 + local.properties sdk.dir then assembleDebug.
- **Transport scripts ready (NEW, lab-run, authorized)**: `measure_true_path_rtt.py`
  (true-path RTT, loopback-smoked) + `run_bitrate_ab.sh` (bitrate A/B evidence into
  `docs/evidence/<date>/ab/`).
- Next lab action: copy/re-convert rehearsal datasets to RTX → run trainer on 4090 →
  `inference_rtx.py --checkpoint <ckpt>` smoke on RTX → then propose receiver
  `--inference real` integration for separate approval.

## Session 2n (2026-08-15, HOME) — DECISION 024: zero torch on the laptop
- **DECISION 024 (binding, supersedes 023's smoke allowance)**: NO torch execution of ANY
  kind on the laptop — no imports, no forwards, no CUDA (3rd freeze happened on the
  lightest possible GPU smoke). Home verification = py_compile + pure-python tests
  (system python3) + bash -n + static review only.
- **`smoke_train_batch.py` (NEW, lab-only)**: single-batch forward-only pipeline smoke
  (RAM guard, 180 s alarm, tiny backbone, no backward) — py_compile-verified, FIRST RUN
  is the 4090 pre-flight at lab.
- **A/B script fixed**: loss = 100×(1 − frames_rx/meta=) + assoc_ok/assoc_miss column
  (was pkts vs frames — would have been garbage).
- **Gradle prep**: gradle-9.4.1-bin.zip in `~/Downloads/` (SHA-256 verified) +
  `gradle-wrapper.jar` fetched + `local.properties` (sdk.dir) created (gitignored).
- **User decisions**: dataset recorded at 10 fps (zero live-latency impact — recorder is
  offline; Q14 = temporal-mismatch open question); encoders = zero work now (wheels zeros
  consistent train/infer).

## Session 2o (2026-08-15) — home phase complete; leaving for lab
- 2n claims RE-VERIFIED (git 24 entries, HEAD==origin==`30728e1`, state files complete,
  compiles green, gradle SHA verified, no strays). No USB needed — gradle zip on laptop;
  transfers via SSH (laptop→RTX scp; laptop↔Jetson USB scp `192.168.55.1`).
- **MODE: HOME → LAB on arrival** (user "im at lab"). First lab gate: **ViReL PID 575347
  confirmation** before any 4090 work; recreate `/tmp/mcq_askpass.sh`.
- Lab order: smoke pre-flight → train → checkpoint → deploy inference_rtx.py →
  `--checkpoint` smoke → deploy sender/kachow_probe to Jetson clone → RTT probe → A/B →
  app build → propose receiver `--inference real` (Q13).

## Session 2p (2026-08-15) — report deliverables + final sanity; heading to lab
- Created `~/Downloads/mcqueen_project_report.txt` (2,865 words) +
  `~/Downloads/mcqueen_project_report_bullets.txt` (1-page PPT sheet) for the
  partner's update PPT — full honest status, transport ("server thing") deep dive,
  every number fact-checked against evidence, sanitized (no decision IDs, no
  shared-GPU job, no laptop freezes, no credentials, no clock timestamps).
- Sanity re-pass: git 24 entries, HEAD==origin==`30728e1`, no commits, reports on
  disk, zero stray processes. **MODE: HEADING TO LAB — on "im at lab" → LAB mode**.

## Session 2s (2026-08-15) — Jio 5G loop test: VERIFIED no improvement; full cleanup
- **5G experiment**: Jetson+camera+phone walked outside on a 10,000 mAh power bank to a
  5G/5G++ spot (phone mode-shifted to 4G sometimes); RTX + laptop stayed in the lab. Resilient
  autostart wrapper (`/home/sravjti/mcqueen_5g/`, append-log + stall-kill + retry) ran the sender
  through the whole walk (0 restarts). RTX: 49,369 frames, fps 20.6, assoc 95.3%, ctrl_sent 46,094.
- **Result**: p50 did NOT improve — best ~223-224 ms at the desk on stable 4G; 5G++ spot window
  ~231-237 ms (≈ stable 4G); cumulative end 257.7 ms; **p95 worsened to ~1239 ms** (mode-shifting).
  **5G++ ≈ 4G median, worse tail — <100 ms NOT achieved via 5G on this phone** (RTT ~50 ms either
  way; queueing is the wall). Evidence: `docs/evidence/2026-08-15/5g/` (REPORT.md + logs);
  ERROR_LOG entry F; AUDIT section 12.
- **En-route bugs FIXED**: Jetson `/tmp` = tmpfs (wiped on reboot → autostart moved to
  `/home/sravjti/mcqueen_5g/`); `mcqueen-edge.service` holds `/dev/video0` at boot (stopped for
  the test, restored after); F7-class pkill-in-cleanup → precise PID kills.
- **Cleanup COMPLETE**: sender + wrapper killed, cron entry removed, `/home/sravjti/mcqueen_5g/`
  deleted, RTX receiver stopped, `mcqueen-edge.service` ACTIVE, tunnel up
  (`carlo-booth-austin-pics.trycloudflare.com`). Git still `30728e1`, zero commits (DECISION 013).
- **Latency outlook**: 5G ruled out; pacing/320×240 = approved flags, future; LAN-link demo day
  = the practical <100 ms path. Q13 + PPGeo training when GPU frees = next session items.
- **GPU gate**: ViReL GONE; new neighbor job `train.py` PID 744309 (20.3 GB VRAM, 82%,
  `~/grpo-gsm8k-output`) — user chose CPU path; GPU NEVER touched (DECISION 014).
- **Training chain verified (CPU)**: `smoke_train_batch.py` PASS (630 samples/6 eps, (8,2));
  `train_temporal_v2.py --backbone tiny --device cpu --epochs 20` →
  `/home/junior/mcqueen_run/rehearsal_temporal.pt` (36 MB, best_val 3.02, keys verified:
  backbone=tiny/history=6/image_size=224/stats/action_names).
- **Inference chain verified with REAL ckpt on RTX**: `test_checkpoint_inference.py` 10/10,
  `test_inference_rtx.py` 18/18, `inference_rtx.py --checkpoint --device cpu` 6.59 ms/frame,
  servo=89.0 pwm=4 (near-center, sane). CUDA single-frame measured 444.75 ms (GPU busy).
- **Jetson deploy**: repo sender + kachow_probe + measure_true_path_rtt.py → clone
  (61a3c91); sender → /tmp too.
- **KACHOW APP BUILT**: gradle 9.4.1 + JDK 17, `assembleDebug` SUCCESS 27 s →
  `apps/android/KachowV8/app/build/outputs/apk/debug/app-debug.apk`. Install HELD.
- **FULL WAN LOOP VERIFIED — port-forward theory RETRACTED (corrected docs)**: pipeline
  binds `0.0.0.0:0` + STUN punch (campus NAT endpoint-independent → NO forward needed).
  Real blocker was DEAD cloudflared + STALE URL (F8) → fresh tunnel
  `carlo-booth-austin-pics.trycloudflare.com` → signaling verified → loop UP:
  **LAT_p50=276.5 ms / p95=486.7 ms** @300 kbps (CTRL_RX n=960), receiver fps 18.3,
  assoc ~94%, infer 0.12 ms; endpoints receiver `14.139.108.62:49995`→`:41820`→`:53591`,
  Jetson `152.59.109.96:59856`. Direct peer-to-peer UDP confirmed (achieved=422 kbps,
  peer=14.139.108.62:53591). cloudflared = STARTUP-ONLY broker (media never on it);
  brokerless removal still a future item (honest — NOT done).
- **Bitrate A/B (150/300/400×2) COMPLETE**: 3 launch failures diagnosed (ssh -t →
  pkill self-match → bracket-pattern STILL self-match; the remote cmdline contains the
  literal script name) → **PID-file kill/check = F7-safe**. 5/6 + manual 400 rerun
  (transient ws 530 on the 6th): ctrl_rx every run, p50 stable 270-280 ms, fps 18-22,
  assoc ~94-96%, 150_1 loss 2.9%. Evidence `docs/evidence/2026-08-15/{REPORT.md,ab/}`;
  script full_loop grep fixed post-run (`CTRL_RX n=`).
- **Docs honest**: ERROR_LOG + AUDIT 2026-08-15 rewritten (dead-tunnel root cause FIXED,
  A/B failure chain entry D, p95 tail note E).
- **Cleanup**: all test procs stopped (PID files); **mcqueen-edge.service RESTORED
  (active)** on Jetson; cloudflared tunnel left UP for next session.
- **Next**: Q13 proposal (receiver `--inference real` w/ tiny ckpt — separate approval);
  PPGeo training when GPU frees; checkpoint copy-back to laptop `data/checkpoints/` if
  user wants; state files handoff-grade; NO commits (DECISION 013).