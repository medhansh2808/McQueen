# CURRENT_TASK.md — McQueen active task

Updated: 2026-08-13 (lab exit pull)

## OBJECTIVE
Complete the lab-exit data pull (Jetson + RTX -> laptop) so the user can debug
the WAN pipeline from home, with all evidence and repo state recorded.

## CURRENT STATE
- DONE (2026-08-13 lab exit): full pull of Jetson home WAN scripts/logs/pids +
  probe-error log + RTX `/var/tmp/mcqueen-junior/` receiver/broker/cloudflared
  state + ALL lab receiver logs + recordings. Snapshots in
  `docs/evidence/2026-08-13-lab-pull/` (manifest README.md); recordings in
  `data/lab_pull_20260813/` (gitignored).
- DONE: found + fixed sender bug F1 (`% 30 < n` NameError freezing rtp_ts);
  documented F2 (receiver python mismatch), F3 (lab15 depay "waiting for start"
  from old NVENC sender), F4 (deployed sender older than laptop copy).
- Repo state: branch `jetson-nano`, HEAD `cf8ac2c`. Untracked: WAN pipeline
  files (tools/realtime/*), evidence pull, context folder. NOT committed.

## BLOCKER
- None for the pull. Home debugging of the WAN video path needs hardware
  (next lab session) for end-to-end verification; offline analysis possible now.

## NEXT ACTION
(EXACTLY ONE)
- Commit the WAN-pipeline code + evidence (user-authorized at home) OR continue
  offline analysis of `docs/evidence/2026-08-13-lab-pull/` logs; then next lab
  session: deploy fixed sender + venv receiver and confirm rtp_ts advances
  (OPEN_QUESTIONS Q2b).

## ACCEPTANCE CRITERIA
- All deployed machine state is mirrored locally (code, logs, pids, recordings). DONE.
- Sender bug F1 fixed on laptop copy, compiles, unit test passes. DONE.
- Evidence doc `2026-08-13-wan-pipeline-errors.txt` updated with findings #20/#21. DONE.
- All `.mcqueen/` state files updated (SESSION_LOG, VERIFIED_FACTS, OPEN_QUESTIONS,
  HANDOFF, AGENT_STATE, DECISIONS). DONE.
- Transient askpass helper deleted. DONE.

## TEST PLAN
1. `python3 tools/realtime/test_rtp_association.py` — PASS (run).
2. `python3 -m py_compile tools/realtime/*.py` — PASS (run).
3. Startup check + self-audit re-run before ending session.

## STATUS
COMPLETE (lab-exit pull; home debug + next-lab redeploy pending)
