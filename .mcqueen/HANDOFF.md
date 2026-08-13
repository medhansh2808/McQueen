# HANDOFF.md — McQueen fresh-session recovery

Read this first in a new session, then `AGENTS.md` and the other `.mcqueen/` files.

## MANDATORY SESSION-START PROTOCOL (DECISION 007)

Freebuff cannot auto-load AGENTS.md, so the agent MUST self-trigger at every session open:
1. Run `bash .mcqueen/agent_startup_check.sh` (or `./.mcqueen/agent_startup_check.sh`).
2. Read `AGENTS.md` (the binding contract) and the `.mcqueen/` state files:
   `AGENT_STATE.md`, `CURRENT_TASK.md`, `VERIFIED_FACTS.md`, `OPEN_QUESTIONS.md`.
3. Inspect `git status`.
4. Only then plan/do work.

User backup phrase (if the agent did not self-trigger): "per AGENTS.md, start session".

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
Branch `jetson-nano`, HEAD `5cc716c`, clean. Remote: github.com/medhansh2808/McQueen.git.
Untracked: `context stuff for understanding the mcqueen project/` (local context dumps),
plus newly created agent files (AGENTS.md, .mcqueen/) — NOT committed (user rule: update GitHub
only when hardware works).

## Important machines / paths
- Laptop repo: `/home/kartik/McQueenWork/McQueen`
- Jetson: reachable at lab via USB (192.168.55.1) or hotspot; passwords required every command.
- RTX 4090: lab Wi-Fi; user `junior`/`omen` (verify); `rtx4090_preflight_v2.sh` to inspect.
- WAN pipeline bundle (NOT in repo): `~/Downloads/mcqueen_wan_direct_p2p/` — broker.py on RTX
  at 127.0.0.1:8765 + cloudflared Quick Tunnel rendezvous.
- RTX candidate temporal package: `~/Downloads/mcqueen_rtx_candidate_20260812/`.

## Key constraints
- No fabrication — use VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / BLOCKED / FAILED / UNKNOWN.
- Proof levels separate: home/synthetic ≠ hardware milestone.
- NO unattended Jetson/RTX access — explicit human approval per command.
- No auto git push/reset/clean. No commits without authorization.
- ChatGPT independence: reasoning lives in repo files, not external chat.

## Current task
See `.mcqueen/CURRENT_TASK.md`. At last update: agent bootstrap being verified (startup check +
self-audit + safe tests). After that, next lab objective = make the Jetson→RTX realtime WAN
pipeline solid & reproducible (Option A: broker+tunnel as persistent services on always-on RTX),
so the next session can record datasets + train.

## Verified facts
See `.mcqueen/VERIFIED_FACTS.md` (each fact has SOURCE + confidence). Highlights: dataset-v2 +
temporal core home-validated (2026-08-12); 3 hardware milestones lab-verified (2026-08-11).

## Unresolved questions
See `.mcqueen/OPEN_QUESTIONS.md` (motor-PWM live probe, broker host confirmation, RTX env
readiness, WAN "server" failure specifics).

## Next action (at the lab)
Phase A per `docs/NEXT_LAB_RUNBOOK.md`:
1. Jetson health preflight (`jetson_no_drivetrain_preflight.sh`) + verify `mcqueen-edge.service`.
2. Network matrix (USB/hotspot/lab Wi-Fi/RTX reachability).
3. Live KACHOW probe (motor-PWM blocker check).
4. RTX preflight + temporal-candidate tests + LeRobot conversion.
5. Option A server hardening + full-loop benchmark-v2.
