# OPEN_QUESTIONS.md — McQueen unresolved questions

Each entry: question, why it matters, who/what can resolve it, status.

---

## Q12 — 10 fps measured WORSE latency than 30 fps — RESOLVED (fps ladder + RTT probe)
- **Question**: At the same 150 kbps cap on the new network, 10 fps gave p50 462 ms vs
  30 fps p50 224 ms. Is sparse 10 fps traffic confusing the jitter-buffer clock recovery,
  or was it link variance between the two runs?
- **Why**: Decides whether --max-fps low-rate operation is viable, and which fps to choose.
- **Resolve**: Full ladder 10/15/30 fps @150 kbps, back-to-back on the same network, with a
  per-second link RTT probe (Jetson pings 1.1.1.1) during every run.
- **Status**: **RESOLVED 2026-08-14 (hardware proof)** — the link was HEALTHY during the
  10 fps run (RTT p50 46 ms / p95 73 ms) yet loop latency was 677 ms → NOT link variance;
  the penalty is the SPARSE TRAFFIC itself (jitter-buffer clock recovery + path/NAT
  scheduling with one burst per 100 ms). Ladder: 10→677 ms, 15→478 ms, 30→277 ms p50.
  True 20 fps is impossible from a 30 fps camera (rates are 30/N only: 30/15/10).
  **Winner: 30 fps** (best latency AND quality). Bonus: 25 ms jitter buffer at 30 fps gave
  p50 281.9 ms — statistically identical to 50 ms → the buffer was never the latency driver.

---

## Q11 — Sender websocket has NO reconnect — robustness gap (FOUND 2026-08-14 lab)
- **Question**: When the Jetson's broker/tunnel websocket drops (observed: `No PONG received
  after 7.5s` → broker disconnected the session), the sender's `_ws_loop` exits and the sender
  never learns candidate changes again — it stays pointed at a dead peer mapping until
  restarted. Should the sender auto-reconnect the ws (bounded backoff) so mid-run receiver
  restarts / tunnel blips self-heal?
- **Why**: Today a receiver restart required a manual sender restart because of this.
  Candidate updates are ONLY used before/at rendezvous in the current flow (RTP is direct UDP
  after punch), so the impact is limited to peer-restart scenarios — but those are exactly the
  failure-prone ones.
- **Resolve**: NOT one of the user's 3 fixes (left unfixed deliberately). Propose to the user
  when they next approve code changes; implement with a bounded reconnect loop in the sender's
  ws handling (McQueen files only).
- **Status**: OPEN (finding recorded; fix deferred — user scoped this session to the 3 fixes).

---

## Q9 — Broker removal: manual/SSH peer exchange vs broker+cloudflared (user wants to discuss)
- **Question**: Can broker.py + cloudflared be dropped from the equation? Each side needs the
  other's public IP:port to punch a hole. Proposal: both peers STUN their own public endpoint;
  run script reads each PUBLIC line via SSH (no literal copy-paste needed — laptop has SSH to
  both machines) and passes as `--peer`; RTX auto-learns Jetson's source from incoming RTP.
- **Why**: Today's failure was stale tunnel URL churn; removing the broker removes a whole
  failure class (no cloudflared binary mgmt, no URL re-read, no public-internet signaling
  dependency — Jetson just needs to reach RTX's public:port UDP, proven reachable 2026-08-11).
- **Caveats to resolve**: public endpoints change per restart (re-read every run); hotspot
  CGNAT public port changes across sender restarts (observed 36620→57379); STUN still needed
  on both sides; campus NAT must allow inbound UDP to RTX (proven on 2026-08-11).
- **Resolve**: Implement the manual exchange: sender gains `--peer` mode (skip ws, punch
  direct), receiver learns the sender's source from incoming RTP, run script reads both
  PUBLIC lines via SSH and passes `--peer`. Caveats: public endpoints change per restart
  (re-read every run); CGNAT public port changes across sender restarts; STUN on both sides.
- **Status**: **DECIDED 2026-08-14 — user wants the broker REMOVED (manual peer exchange);
  execution DEFERRED to tomorrow (estimates given: ~1.5–2.5 h incl. live verify).** The
  earlier "keep broker" (Q9, run-package choice) is superseded. Removes broker + cloudflared
  + tunnel URL + the Q11 ws-reconnect failure class; NOT in the latency path (video/controls
  are direct UDP after punch), so no latency change — it removes failure modes. Also note:
  the sender re-pointing to a new receiver port WITHOUT a fresh restart does NOT re-establish
  the NAT path (observed 0 RTP) — fresh sender restart required per session.

---

## Q10 — GPU contention: ViReL train.py on the 4090
- **Question**: RTX GPU is 100% busy with `/home/junior/ViReL/Tasks/vlmgrpo` `python train.py`
  (PID 490867). Who owns it? Can it ever be paused?
- **Why**: NVDEC + CUDA dummy inference queue behind it (169 ms/op, ~1 fps, stalls).
- **Resolve**: VERIFIED 2026-08-14 — runs as `junior`, cwd ~/ViReL/Tasks/vlmgrpo, NOT
  McQueen's (outside McQueen dirs). User: "na do not touch virel at all." Plan A (CPU
  decode/infer) makes the test independent of the GPU.
- **Status**: RESOLVED — and moot as of later 2026-08-14: **train.py is GONE** (nvidia-smi 0%
  util, 27 MiB). GPU free; full-loop run was uncontended. CPU path still used per approval.
  **UPDATE 21:41: a NEW train.py (PID 575347, started 20:17, 90% util / 20.4 GiB VRAM) is
  running again** — still NOT McQueen's, still untouchable; Plan A (CPU path) proven
  GPU-independent (jitter25 run sustained 25.4 fps while it ran).

---

## Q1 — Is the motor-PWM label path actually healthy? (UNCHANGED — still open)
- **Question**: Does live phone throttle → Jetson `throttle_command`/`motor_pwm` change correctly?
- **Why**: A 138-frame recording had 130 frames with zero throttle/steering input; the
  "motor_pwm stuck at 0" claim is not reproducible from the data (PWM math is correct in
  non-zero frames). Dataset collection should not start until confirmed live.
- **Resolve**: Run `tools/realtime/kachow_probe.py` on the Jetson with a real phone at the lab.
  (2026-08-14 prep: probe now prints per-packet `pwm` via the recorder's exact
  `throttle_to_pwm` + LABEL_PATH coverage stats + verdict — exit 0 = control AND PWM path
  proven, exit 3 = control OK but PWM unproven.)
- **Status**: UNVERIFIED (probe prepared; blocked until lab + human authorization). Probe
  not yet run — deferred until the pipeline is flawless (user decision).

## Q2 — What exactly was "broken" with the WAN server thing?
- **Question**: What failure mode drove the "fix the server thing" goal?
- **Why**: Determines the fix target (crash? URL churn? babysitting? receiver pipeline bug?).
- **Resolve**: Inspect `~/Downloads/mcqueen_wan_direct_p2p/` fix bundles + RTX logs at the lab.
- **Status**: PARTIALLY VERIFIED — concrete causes found and fixed on laptop copies
  (F1 sender `% 30 < n` NameError freezing rtp_ts; F2 receiver started with wrong python;
  nothing committed/random tunnel URL/ad-hoc debugging pain points). Residual at lab: harden
  broker + cloudflared as persistent services (Option A) and confirm broker host.

## Q2b — Sender rtp_ts advancement after F1 fix
- **Question**: With the `% 30 == 0` fix, does the sender's per-frame rtp_ts advance and does the
  RTX decode >1 frame (frames_rx > 0) end-to-end?
- **Resolve**: `./tools/realtime/run_rtp_wan_test.sh` (deploys FIXED sender + venv-python
  receiver + repo broker automatically), check `SENT pkts` throttle prints + `rtp_ts` +
  `frames_rx` + 0 probe errors.
- **Status**: **RESOLVED 2026-08-14 lab (hardware proof)**: rtp_ts advances on hardware
  (F1 fix live), frames decoded continuously, EXACT_FRAME_MATCH assoc_ok≈5.7k / assoc_miss≈950
  (~14% honest WAN-loss misses), control return verified (CTRL_RX n≈1.8k), FULL_LOOP_LATENCY
  measured (final p50 ≈ 391 ms / p95 ≈ 1.67 s on the hotspot link, CPU path).

## Q8 — Old sender's marker-every-packet `(96 << 1)` bug — resolved?
- **Question**: lab13/14/15 showed frames_rx climbing with zero decoded frames — marker on every
  packet. Was that bug in the deployed sender?
- **Resolve**: RESOLVED 2026-08-13 home debug — yes; new sender sets marker only on the last
  packet (unit-tested). No action needed beyond tomorrow's hardware proof.

## Q3 — Where did the broker/tunnel actually run on 2026-08-11?
- **Question**: Host of broker.py + cloudflared during the proof.
- **Why**: Decides where the permanent broker service should live — now moot if Q9 (broker
  removal) is accepted.
- **Resolve**: Confirmed 2026-08-14: broker RUNNING on RTX at 127.0.0.1:8765 (health ok);
  cloudflared running with a NEW url (stale 2026-08-13 url file caused a run failure — F8).
- **Status**: RESOLVED (broker lives on RTX today; superseded by Q9 broker-removal proposal).

## Q4 — RTX env readiness (LeRobot, W&B, disk, GPU jobs)
- **Question**: Does the RTX have a working LeRobot env, W&B login, disk for datasets/checkpoints,
  and are any GPU jobs running that must not be disturbed?
- **Why**: Required for temporal-candidate tests, LeRobot conversion, and training tomorrow.
- **Resolve**: Run `tools/preflight/rtx4090_preflight_v2.sh` at the lab (read-only).
- **Status**: UNKNOWN.

## Q5 — Camera / drivetrain presence at the next lab session
- **Question**: Is the Lenovo camera with the Jetson? Is any drivetrain (servo/motor/encoder) present?
- **Why**: Camera needed for camera→WebRTC→RTX path; drivetrain determines Phase A vs A+B.
- **Resolve**: Ask the user / inspect hardware at the lab.
- **Status**: UNKNOWN (user said drivetrain will not be available; camera expected yes).

## Q6 — Agent bootstrap commit
- **Question**: When should AGENTS.md + `.mcqueen/` be committed/pushed?
- **Why**: User rule: update GitHub only when things properly work on hardware; also wants the
  agent guidelines respected like a constitution.
- **Resolve**: RESOLVED 2026-08-13 — user chose "Commit now": committed locally (no push).
  Push still deferred per user rule (GitHub updates only when hardware works).
- **Status**: RESOLVED (local commit done; push pending future lab milestone)

## Q6 — RESOLVED (2026-08-13 audit): bootstrap + WAN code + evidence all committed AND pushed
- Everything through `6698d41` is on GitHub (origin == local). User confirmed the push was
  intentional (DECISION 012: nightly home sync sanctioned).

## Q7 — Per-machine Freebuff reachability
- **Question**: Is this laptop the machine that goes to the lab (it is, per user), and can it
  reach Jetson (USB 192.168.55.1) and RTX over lab Wi-Fi/hotspot paths when there?
- **Why**: Determines orchestration path for the lab runbook.
- **Resolve**: VERIFIED 2026-08-14: laptop→Jetson USB SSH ok; laptop→RTX wired .132 ok
  (wifi .179 dead); Jetson has internet via hotspot. Orchestration = laptop SSH to both.
- **Status**: RESOLVED (lab paths verified; re-verify if network changes).
