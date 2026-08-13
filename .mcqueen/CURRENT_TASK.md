# CURRENT_TASK.md — McQueen active task

Updated: 2026-08-13 (home debug session, evening)

## OBJECTIVE
Offline-debug the WAN video path from home so that the next lab session is
TEST-ONLY (no from-scratch debugging): resolve/understand sender #19 stall,
confirm the F1 fix + venv receiver are sufficient for rtp_ts to advance and
frames_rx > 0 (Q2b), and hand over a precise hardware test checklist.

## CURRENT STATE
- 2026-08-13 lab day fully audited; everything COMMITTED + PUSHED to GitHub
  (HEAD = origin/jetson-nano = 6698d41, user-authorized).
- HOME DEBUG COMPLETE (2026-08-13 evening): root causes of the lab failures pinned
  from pulled evidence; sender hardened + refactored; new offline unit test suite
  (test_rtp_packetization.py 6/6 PASS). Details:
  docs/HOME_DEBUG_2026-08-13.md + SESSION_LOG + VERIFIED_FACTS.
- FIXED (laptop copy): F1 `% 30 == 0` rtp_ts advance; marker-only-on-last-packet;
  FU-A S/E complete; AUD drop; non-VCL (SPS/PPS) hold-and-prepend; #19 stall chain
  removed by design (cv2 + x264 SW); probe-error log reset + result checks in
  run_rtp_wan_test.sh.
- BLOCKED (env): test_temporal_policy_v2.py needs torch (mcqueen-laptop env).
- Test suite: pytest tests/ 7 passed + 11 mcqueen_ml passed (18 total, excluding
  torch collector); startup check 35/35 PASS.

## BLOCKER
- Hardware proof pending: tomorrow's lab run of run_rtp_wan_test.sh. No hardware
  at home; HOME mode forbids Jetson/RTX access anyway.

## NEXT ACTION
(EXACTLY ONE)
- Tomorrow at lab (TEST-ONLY): `./tools/realtime/run_rtp_wan_test.sh` in a real
  terminal. Green = NAT punch + RTX decoded frames + control return +
  FULL_LOOP_LATENCY + 0 errors + 0 probe errors. Then record latency, log the
  result in evidence/, and update these state files.

## ACCEPTANCE CRITERIA (tomorrow)
- run_rtp_wan_test.sh green end-to-end; FULL_LOOP_LATENCY logged.
- If not green: diagnose per docs/HOME_DEBUG_2026-08-13.md section 4 watch list.
- Evidence + state files updated after the lab run.

## STATUS
COMPLETE (home debug) — pending hardware verification tomorrow
