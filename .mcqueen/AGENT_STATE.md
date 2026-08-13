# AGENT_STATE.md — McQueen agent durable state

Updated: 2026-08-13 (bootstrap)

## Identity
- Agent: McQueen coding/repository engineering agent (contract: `AGENTS.md` at repo root).
- Scope: software engineering only. NOT part of the realtime driving loop.

## Machines (roles, not IPs)
- **Laptop** (`/home/kartik/McQueenWork/McQueen`): development, coding, Git, SSH/admin,
  debugging, offline replay/analysis, setup. Python 3.10.12 verified present.
- **Jetson Nano 2GB**: robot edge computer — camera capture, H.264 encode, teleop runtime,
  raw recording, frame IDs / monotonic timestamps, safety gate, actuator I/O. Ubuntu 18.04-era,
  old Python/GStreamer/NVIDIA stack — dependency changes must be conservative.
- **RTX 4090**: heavy ML/inference — video receive/decode, temporal-policy inference,
  direct-UDP action return, training/evaluation.

## Data flow (final desired runtime)
CAMERA → JETSON NANO → low-latency transport / WebRTC → RTX 4090 → autonomous-driving model
→ control return → JETSON SAFETY GATE → SERVO + MOTOR

## Realtime target
- Target: <100 ms end-to-end. **TARGET, NOT A PROVEN RESULT.**
- No authoritative separate-WAN capture→inference→returned-command full-loop latency exists yet.
- Proven to date (2026-08-11 lab): direct-WAN UDP control return 60/60 ACKs,
  p50 43.1 ms / p95 70.4 ms RTT (Jetson dry-run, zero GPIO). Camera→H.264→WebRTC→RTX
  decode→CUDA dummy action proven only on the local lab route.

## Current working mode
- **Home / software-validation mode** (laptop). Lab hardware-verification mode is not active.
- User rule: NO unattended Jetson/RTX access. Every Jetson/RTX command requires explicit
  human authorization (human enters passwords). Do not damage hardware.

## Session-start protocol (DECISION 007 — mandatory)
At every new session open: (1) run `.mcqueen/agent_startup_check.sh`; (2) read AGENTS.md +
`.mcqueen/` state files; (3) `git status`; (4) then work. User backup phrase:
"per AGENTS.md, start session".

## Key constraints (see AGENTS.md for full contract)
- No fabrication; use VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / BLOCKED / FAILED / UNKNOWN.
- Exact frame identity (`frame_id` + `capture_mono_ns`) for all realtime association.
- Newest-frame-wins; stale predictions must not control the vehicle.
- Safety: steering 45–115 deg center 90, forward cap +100 PWM, reverse cap −70, prediction
  timeout 250 ms, stale → zero PWM + center steering + cancel AUTO.
- Jetson/RTX IPs change — discover/verify/inspect before acting.
- Do not commit datasets/weights/artifacts (`.gitignore` covers `data/`, `*.pt`, etc.).
