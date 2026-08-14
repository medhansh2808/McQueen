# HANDOFF.md — McQueen fresh-session recovery

Read this first in a new session, then `AGENTS.md` and the other `.mcqueen/` files.

## MANDATORY SESSION-START PROTOCOL (DECISION 007)

Freebuff cannot auto-load AGENTS.md, so the agent MUST self-trigger at every session open:
1. Run `bash .mcqueen/agent_startup_check.sh` (or `./.mcqueen/agent_startup_check.sh`).
2. Read `AGENTS.md` (the binding contract) and the `.mcqueen/` state files:
   `AGENT_STATE.md`, `CURRENT_TASK.md`, `VERIFIED_FACTS.md`, `OPEN_QUESTIONS.md`.
3. Inspect `git status`.
4. Only then plan/do work.

User trigger phrases (user includes one at the start of every session — they signal the
start of the startup protocol AND set the working mode):
- **"im at home"** → HOME mode: software-validation mode, laptop-only work, no hardware
  claims, no Jetson/RTX access.
- **"im at lab"** → LAB mode: hardware-verification mode, Jetson/RTX available, remote work
  begins (each remote command still requires explicit human authorization).

Binding rules = AGENTS.md + `.mcqueen/` ONLY (DECISION 008). The local folder
`context stuff for understanding the mcqueen project/` is reference material, not binding.

## Project identity
McQueen: autonomous RC-car / small-UGV. Human teleops via the KACHOW Android app; the car
records demonstrations; goal is a temporal driving policy (PPGeo ResNet-34 backbone first,
Drive-JEPA ViT second) trained from demos that drives autonomously from live camera.

## Architecture (final desired runtime)
    CAMERA → JETSON NANO → WebRTC/low-latency → RTX 4090 → driving model
           → control return → JETSON SAFETY GATE → SERVO + MOTOR

- **Jetson Nano 2GB**: capture/encode, teleop runtime, raw recording, frame IDs + monotonic
  timestamps, safety gate, actuator I/O. Ubuntu 18.04-era — conservative deps.
- **RTX 4090**: decode, temporal-policy inference, direct-UDP action return, training.
  COMMON machine — DECISION 014 hygiene (never touch non-McQueen stuff; remove only McQueen
  junk with per-item human approval).
- **Laptop**: dev/coding/Git/SSH/replay only — NOT part of runtime.
- **Phone (KACHOW)**: teleop, E-stop/takeover, AUTO authorization.

## Realtime target
<100 ms end-to-end is a TARGET, NOT a proven result. Proven: direct-WAN UDP control return
60/60 ACKs p50 43.1 ms / p95 70.4 ms (2026-08-11). **FULL LOOP measured on separate WAN
(2026-08-14):** old hotspot p50 391 ms / p95 1.67 s @400 kbps; new network ~160 ms
(30fps/400), ladder @150: 10→677, 15→478, 30→277 ms p50; 25 ms jitter ≈ 50 ms → ~280 ms
is wire/RTT, compute <10 ms. <100 ms needs a better link (43 ms control RTT proven on the
good route) — NOT yet achieved.

## Safety contract (never weaken)
Steering 45–115° center 90; forward cap +100 PWM; reverse cap −70; prediction timeout 250 ms;
stale → zero PWM + center + cancel AUTO; phone authorizes AUTO (model never does).

## Realtime association contract
Exact `frame_id` + `capture_mono_ns` echoed by prediction; latency = `receive_mono_ns −
capture_mono_ns` on Jetson clock; newest-frame-wins; benchmark-v2 reports stages independently
(SIGNALING_P2P … FULL_LOOP_LATENCY) with n/p50/p95 — see docs/evidence/MILESTONE_TEMPLATE.md.

## Current Git state
Branch `jetson-nano`. Local HEAD = `6632913`; **origin/jetson-nano is 1 commit AHEAD**
(`57561db` "actaul audit", user web-pushed 2026-08-14 00:17 — only edits
docs/AUDIT_2026-08-13.md; local working copy has its OWN uncommitted AUDIT edit — reconcile
at the first commit). **DECISION 013 (binding): NOTHING committed or pushed until
hardware-verified.** All 2026-08-14 work (home prep H1–H5 + lab fixes F7/F8/F9 in
run_rtp_wan_test.sh) is uncommitted/untracked (full list in CURRENT_TASK.md); it rides along
in the FIRST hardware-verified commit. Remote: github.com/medhansh2808/McQueen.git.
**GITHUB RESTRUCTURE PLANNED (user-approved, awaiting GO — NOT executed):** tag
`pre-purge-2026-08-14`, reconcile `57561db` (local AUDIT wins), branch-only purge of
`legacy/` (esp32, uno_q_previous, laptop_logger, dataset_logging, oakd) +
`hardware/cad/oakdmount.stl` (52 files; history is the backup — user chose git-history
over a local backup folder), commit all pending work, push. New BINDING rule AGENTS.md §J:
GitHub updates = simple + functional + maximally reproducible (user mandate). Future task:
fresh-machine reproducibility (runbook, pinned deps, F7/F8/F9 fixes, checkpoint doc,
cloudflared, KACHOW build) — full detail in CURRENT_TASK.md FUTURE WORK.

## Important machines / paths
- Laptop repo: `/home/kartik/McQueenWork/McQueen`; torch env:
  `/home/kartik/miniforge3/envs/mcqueen-laptop/bin/python` (3.12.13, torch 2.11.0+cu128,
  CUDA). System python3 = 3.10.12 WITHOUT torch (torch tests are ignored in system pytest
  and run via unittest in mcqueen-laptop).
- Jetson: `sravjti@192.168.55.1` (USB) — VERIFIED 2026-08-13/14; kernel 4.9.253; camera present;
  hotspot ON (wlan0 10.147.40.55); sudo REQUIRES password; mcqueen-edge.service currently
  STOPPED. Passwords required every command.
- RTX 4090: `junior@192.168.0.132` (wired; wifi .179 dead today), hostname `omen` — VERIFIED
  2026-08-14: i9-13900K 24C/32T, 62 GB RAM, venv torch 2.6.0+cu124, avdec_h264 + nvcodec
  present; receiver MUST use `/var/tmp/mcqueen-junior/gst-webrtc-venv/bin/python` (F2).
- **Passwords: user-provided, live ONLY in the transient helper `/tmp/mcq_askpass.sh`
  (SSH_ASKPASS_REQUIRE=force) on the laptop — NEVER in repo files (AGENTS.md §H); recreate
  the helper or ask the user if gone.**
- **UNTOUCHABLE on RTX:** PID 490867 `python train.py`, cwd `/home/junior/ViReL/Tasks/vlmgrpo`
  (VLM-GRPO training, NOT McQueen's). Never pause/kill/modify (DECISION 014 + user hard rule).
- PPGeo ResNet-34 checkpoint (OUTSIDE repo): `~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth`
  (87.3 MB; Google Drive id `1GAeLgT3Bd_koN9bRPDU1ksMpMlWfGXbE`, BaiduYun code `itqi`).
  For lab/RTX use: copy to `data/checkpoints` (keep-list, DECISION 014) + `MCQUEEN_PPGEO_CKPT`.
- 2026-08-13 lab-exit pull (complete machine snapshots + logs): `docs/evidence/2026-08-13-lab-pull/`;
  recordings: `data/lab_pull_20260813/`. Manifest: `docs/evidence/2026-08-13-lab-pull/README.md`.

## Key constraints
- No fabrication — use VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / BLOCKED / FAILED / UNKNOWN.
- Proof levels separate: home/synthetic ≠ hardware milestone.
- NO unattended Jetson/RTX access — explicit human approval per command.
- No auto git push/reset/clean. No commits without hardware verification (DECISION 013).
- Checkpoint weights never enter the repo; adapters must raise (no silent fallback) (DECISION 015).
- ChatGPT independence: reasoning lives in repo files, not external chat.

## Current task
See `.mcqueen/CURRENT_TASK.md`. **2026-08-14 LAB: approved 4-part plan COMPLETE** (all
hardware-verified): (1) cleanup RTX+Jetson done, keep-list intact; (2) save-latency test
(`--save-frames`, JPEG+CSV async writer) — recv→decode→save p50 1.14 ms / p95 1.54 ms,
0 dropped, completeness 90.8%; (3) fps ladder + RTT probe — 10→677, 15→478, 30→277 ms p50
loop @150 kbps, link healthy all runs (RTT 46 ms) → sparse-traffic penalty CONFIRMED;
30 fps = winner (20 fps impossible: 30/N rates); (4) 25 ms jitter buffer @ 30fps — p50
281.9 ms ≈ identical to 50 ms → buffer was never the latency driver (~280 ms = wire/RTT).
Absolute capture→save latency dropped per user (needs clock offset; sync_calib.py written,
unused). **ALL procs STOPPED at session end** (see below).

Then: cleanup round 2 FULL SWEEP done (both machines now hold only what the current
pipeline needs + punch tools + today's evidence; keep-list verified). `docs/ERROR_LOG_2026-08-14.md`
created (user-approved for the next GitHub push). Pending user go/no-go (estimates given):
broker removal via manual peer exchange (~1.5–2.5 h; punch_peer.py tooling exists) and
<100 ms diagnostics — control-only RTT probe + 320×240 run (~30–45 min).

**2026-08-14 session end:** ALL test procs STOPPED (sender/receiver/broker/cloudflared —
precise PID kills, verified). Recordings stay on disk (save_test_201750/, jitter25_204850/).
No GitHub today (DECISION 013). **BINDING at-home rule (user):** ANY code/script change at
home must be PROPOSED and await explicit approval — including fixing F7/F8/F9 in the run
script (they are still in it; the documented manual-start procedure is the current fallback).

**Session 2f (21:47–21:50):** EVIDENCE ALREADY FILED on the laptop —
`docs/evidence/2026-08-14/wan-loop-measured/` (14 files + REPORT.md; numbers: FULL_LOOP
n≈48.6k p50 287.1 / p95 504.0 ms; CONTROL_RETURN proven, CTRL_RX n=48,650; EXACT_FRAME_MATCH
~94 %; save path p50 0.96 / p95 1.32 ms). Deployed sender/receiver/inference/broker verified
md5-IDENTICAL to repo; **Jetson clone `kachow_probe.py` is STALE — deploy repo version before
the live Q1 probe**. Recordings raw JPEGs left on RTX (not needed; meta.csv pulled).
**ViReL train.py is BACK on RTX: PID 575347 (started 20:17, 90 % GPU, 20.4 GiB) — untouchable
(DECISION 014); Plan A CPU path proven GPU-independent (jitter25 ran 25.4 fps while busy).**

**Session 3 (home, after lab):** PLANNING ONLY — no GitHub, no machines, no code. (1) Day
AUDIT created (`docs/AUDIT_2026-08-14.md`) — was missing; error log timestamp-cleaned.
(2) NEW BINDING RULE (AGENTS.md §C): audits/error logs/evidence REPORTs must NEVER contain
clock timestamps (dates + IP:ports OK). (3) GitHub restructure PLANNED (purge legacy/
52 files branch-only, reconcile `57561db`, tag `pre-purge-2026-08-14`, commit all pending
work, push; history = backup; EXCLUDE sync_calib.py + context folder) — awaiting user GO.
(4) **FINALIZED next-lab scope = transport/latency ONLY:** TRUE PATH RTT FIRST (Jetson pings
RTX public IP, NOT Cloudflare — decisive floor), then 320×240 @ 150 kbps + packet pacing if
worth it; constants: 30 fps, 50 ms jitter, CPU decode/infer, no retransmission.
(5) **NO TRAINED POLICY EXISTS** — only PPGeo encoder (features, NOT actuators) + 8 old demos
(not real driving data per user); L1 real inference gated until real dataset → train → L0
green → approval. (6) REAL SPEC: camera→actuator as fast as possible on real roads; <100 ms
was aspirational; Jio 5G ideal (RTT ~10–30 ms → comfortably <100 ms).

## Verified facts
See `.mcqueen/VERIFIED_FACTS.md` (each fact has SOURCE + confidence). Highlights: dataset-v2 +
temporal core home-validated (2026-08-12); 3 hardware milestones lab-verified (2026-08-11);
F1 sender bug fixed + packetization unit-tested (2026-08-13); H1–H5 prep verified (2026-08-14).

## Unresolved questions
See `.mcqueen/OPEN_QUESTIONS.md`: Q1 motor-PWM probe (NOT yet run — tomorrow with a real
phone), Q2b rtp_ts/frames_rx (RESOLVED — rtp_ts advances, frames_rx>0, exact match, full
loop measured), **Q9 broker removal (DECIDED — remove via manual peer exchange, DEFERRED to
tomorrow; estimates ~1.5–2.5 h)**, Q11 sender ws no-reconnect (OPEN — becomes moot once the
broker is gone), Q10 GPU contention (RESOLVED: ViReL untouchable, CPU path), Q4/Q5 still open.

## Next action (next lab — FINALIZED scope: transport/latency ONLY; machines IDLE, all procs stopped)
1. Deploy + start the pipeline (broker/cloudflared → receiver venv python → sender;
   manual-start procedure — run_rtp_wan_test.sh still has F7/F8/F9 unless user approves
   fixing them; at-home rule: ask + wait before ANY change).
2. **TRUE PATH RTT FIRST (~10 min, decisive):** Jetson pings the RTX's ACTUAL public IP
   (NOT Cloudflare). ≈46 ms → floor ≈60 ms, <100 ms fightable on 4G, easy on Jio 5G;
   100+ ms → link is the wall.
3. Queueing attacks if floor says worth it: 320×240 @ 150 kbps + packet pacing.
4. Broker removal (manual peer exchange; punch_peer.py exists) if time allows (~1.5–2.5 h).
5. Live KACHOW probe: `tools/realtime/kachow_probe.py` (REPO version — Jetson clone STALE)
   → expect exit 0 (closes Q1); exit 3 → drive forward AND reverse, re-run.
6. If healthy: RECORD A REAL DATASET (the collection the whole inference chain waits on) →
   `tools/realtime/process_recording.sh` (must print PASSED) → LeRobot conversion.
7. First hardware-verified commit of ALL pending prep + lab work (DECISION 013) incl.
   docs/ERROR_LOG_2026-08-14.md + filed evidence; reconcile origin `57561db` (AUDIT doc
   local-vs-remote).
8. L1 (`--inference real`, PPGeo) ONLY after: real dataset → policy TRAINED → L0 green →
   user approval. NO trained policy exists yet (only PPGeo encoder + 8 non-real demos).
   Checkpoint to `data/checkpoints` + `MCQUEEN_PPGEO_CKPT`.

**Constants (confirmed):** 30 fps, 50 ms jitter buffer (25 ms identical — keep margin), CPU
decode + CPU inference, newest-frame-wins, no retransmission, 250 ms timeout. **Real spec:**
camera→actuator as fast as possible on real roads; <100 ms aspirational; Jio 5G ideal.
