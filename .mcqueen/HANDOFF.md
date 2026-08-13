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
records demonstrations; goal is a temporal driving policy trained from demos that drives
autonomously from live camera.

## Architecture (final desired runtime)
    CAMERA → JETSON NANO → WebRTC/low-latency → RTX 4090 → driving model
           → control return → JETSON SAFETY GATE → SERVO + MOTOR

- **Jetson Nano 2GB**: capture/encode, teleop runtime, raw recording, frame IDs + monotonic
  timestamps, safety gate, actuator I/O. Ubuntu 18.04-era — conservative deps.
- **RTX 4090**: decode, temporal-policy inference, direct-UDP action return, training.
- **Laptop**: dev/coding/Git/SSH/replay only — NOT part of runtime.
- **Phone (KACHOW)**: teleop, E-stop/takeover, AUTO authorization.

## Realtime target
<100 ms end-to-end is a TARGET, NOT a proven result. Proven so far: direct-WAN UDP control
return 60/60 ACKs p50 43.1 ms / p95 70.4 ms (dry-run, zero GPIO, 2026-08-11). Camera→RTX compute
proven only on the local lab route. NO authoritative separate-WAN full-loop latency exists yet.

## Safety contract (never weaken)
Steering 45–115° center 90; forward cap +100 PWM; reverse cap −70; prediction timeout 250 ms;
stale → zero PWM + center + cancel AUTO; phone authorizes AUTO (model never does).

## Realtime association contract
Exact `frame_id` + `capture_mono_ns` echoed by prediction; latency = `receive_mono_ns −
capture_mono_ns` on Jetson clock; newest-frame-wins; benchmark-v2 reports stages independently
(SIGNALING_P2P … FULL_LOOP_LATENCY).

## Current Git state
Branch `jetson-nano`, HEAD == origin/jetson-nano == `6698d41` (ALL 2026-08-13 work
committed AND pushed: WAN RTP transport code, lab-exit evidence pull, agent system,
edge-test/preflight/runbook fixes). Remote: github.com/medhansh2808/McQueen.git.
Only untracked item: `context stuff for understanding the mcqueen project/` (reference
material, intentionally not committed). DECISION 012: nightly home sync of committed
work to GitHub is user-sanctioned; state files (DECISION 011) must ALWAYS be current.

## Important machines / paths
- Laptop repo: `/home/kartik/McQueenWork/McQueen`
- Jetson: `sravjti@192.168.55.1` (USB) — VERIFIED 2026-08-13; kernel 4.9.253; camera present;
  mcqueen-edge.service inactive+enabled. Passwords required every command.
- RTX 4090: `junior@192.168.0.132` (wired) / `.179` (wifi), hostname `omen` — VERIFIED 2026-08-13;
  broker + cloudflared RUNNING; receiver must use `/var/tmp/mcqueen-junior/gst-webrtc-venv/bin/python`.
- WAN pipeline bundle (NOT in repo): `~/Downloads/mcqueen_wan_direct_p2p/` — broker.py on RTX
  at 127.0.0.1:8765 + cloudflared Quick Tunnel rendezvous.
- RTX candidate temporal package: `~/Downloads/mcqueen_rtx_candidate_20260812/`.
- 2026-08-13 lab-exit pull (complete machine snapshots + logs): `docs/evidence/2026-08-13-lab-pull/`;
  recordings: `data/lab_pull_20260813/`. Manifest: `docs/evidence/2026-08-13-lab-pull/README.md`.

## Key constraints
- No fabrication — use VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / BLOCKED / FAILED / UNKNOWN.
- Proof levels separate: home/synthetic ≠ hardware milestone.
- NO unattended Jetson/RTX access — explicit human approval per command.
- No auto git push/reset/clean. No commits without authorization.
- ChatGPT independence: reasoning lives in repo files, not external chat.

## Current task
See `.mcqueen/CURRENT_TASK.md`. Last update (2026-08-13 lab exit): full Jetson+RTX pull to
laptop complete; sender bug F1 found+fixed on laptop copy; evidence + recordings mirrored.
Next: home debugging / commit decision, then next lab objective = make the Jetson→RTX realtime
WAN pipeline solid & reproducible (Option A: broker+tunnel as persistent services on always-on
RTX), so the next session can record datasets + train. Redoploy fixed sender + venv receiver
first (see `docs/evidence/2026-08-13-lab-pull/README.md` + OPEN_QUESTIONS Q2b).

## Verified facts
See `.mcqueen/VERIFIED_FACTS.md` (each fact has SOURCE + confidence). Highlights: dataset-v2 +
temporal core home-validated (2026-08-12); 3 hardware milestones lab-verified (2026-08-11).

## Unresolved questions
See `.mcqueen/OPEN_QUESTIONS.md` (motor-PWM live probe, broker host confirmation, RTX env
readiness, WAN "server" failure specifics).

## Next action (home: now)
1. Decide commit: WAN pipeline code + evidence are untracked and ready (user said "safely update
   github at home") — commit locally, push only when user says (hardware-works rule).
2. Home debug: analyze `docs/evidence/2026-08-13-lab-pull/` logs (F1/F2/F3/F4 in README).

## Next action (at the next lab)
Phase A per `docs/NEXT_LAB_RUNBOOK.md`, PLUS first: deploy the FIXED laptop sender
(`tools/realtime/gst_jetson_rtp_wan.py`) to the Jetson and start the RTX receiver with the
venv python; confirm rtp_ts advances + frames_rx > 0 (OPEN_QUESTIONS Q2b). Then:
1. Jetson health preflight (`jetson_no_drivetrain_preflight.sh`) + verify `mcqueen-edge.service`.
2. Network matrix (USB/hotspot/lab Wi-Fi/RTX reachability).
3. Live KACHOW probe (motor-PWM blocker check).
4. RTX preflight + temporal-candidate tests + LeRobot conversion.
5. Option A server hardening + full-loop benchmark-v2.
