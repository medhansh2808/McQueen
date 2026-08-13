# OPEN_QUESTIONS.md — McQueen unresolved questions

Each entry: question, why it matters, who/what can resolve it, status.

---

## Q1 — Is the motor-PWM label path actually healthy?
- **Question**: Does live phone throttle → Jetson `throttle_command`/`motor_pwm` change correctly?
- **Why**: A 138-frame recording had 130 frames with zero throttle/steering input; the
  "motor_pwm stuck at 0" claim is not reproducible from the data (PWM math is correct in
  non-zero frames). Dataset collection should not start until confirmed live.
- **Resolve**: Run `tools/realtime/kachow_probe.py` on the Jetson with a real phone at the lab.
- **Status**: UNVERIFIED (blocked until lab + human authorization).

## Q2 — What exactly was "broken" with the WAN server thing?
- **Question**: What failure mode drove the "fix the server thing" goal?
- **Why**: Determines the fix target (crash? URL churn? babysitting? receiver pipeline bug?).
- **Resolve**: Inspect `~/Downloads/mcqueen_wan_direct_p2p/` fix bundles + RTX logs at the lab.
- **Status**: PARTIALLY VERIFIED — known pain points: nothing committed, random tunnel URL per
  restart, no persistence/restart, ad-hoc debugging rounds. Root incident specifics UNKNOWN.

## Q3 — Where did the broker/tunnel actually run on 2026-08-11?
- **Question**: Host of broker.py + cloudflared during the proof.
- **Why**: Decides where the permanent broker service should live.
- **Resolve**: Evidence in run_direct_wan_test.sh suggests broker ran on the RTX
  (`/var/tmp/mcqueen-junior/`, 127.0.0.1:8765). Confirm on the RTX at the lab.
- **Status**: UNVERIFIED (inferred from script inspection).

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

## Q7 — Per-machine Freebuff reachability
- **Question**: Is this laptop the machine that goes to the lab (it is, per user), and can it
  reach Jetson (USB 192.168.55.1) and RTX over lab Wi-Fi/hotspot paths when there?
- **Why**: Determines orchestration path for the lab runbook.
- **Resolve**: Network matrix test at the lab (per NEXT_LAB_RUNBOOK).
- **Status**: UNVERIFIED.
