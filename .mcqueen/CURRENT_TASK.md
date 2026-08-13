# CURRENT_TASK.md — McQueen active task

Updated: 2026-08-13 (bootstrap)

## OBJECTIVE
Establish the durable repository-based agent contract + context system
(`AGENTS.md` + `.mcqueen/`) so a fresh Freebuff session can recover McQueen context
without ChatGPT. Then return to the real engineering goal.

## CURRENT STATE
- Bootstrap in progress (this session): contract + context files being created/verified.
- Project status (docs/PROJECT_STATUS_2026-08-12.md): dataset-v2 + temporal core home-validated;
  2026-08-11 lab proved direct-WAN control return + local-route camera→RTX compute +
  phone→Jetson parsing. Drivetrain hardware NOT yet verified.
- Git: branch `jetson-nano`, HEAD `5cc716c`, clean worktree except untracked local folder
  `context stuff for understanding the mcqueen project/`.

## BLOCKER
- None for the bootstrap itself.
- For lab work: user is not at the lab yet; hardware access requires explicit per-command
  authorization.

## NEXT ACTION
(EXACTLY ONE)
- Run `.mcqueen/agent_startup_check.sh` and `python3 .mcqueen/agent_self_audit.py`, then the safe repo test suite, and record results in `.mcqueen/SESSION_LOG.md` + `.mcqueen/VERIFIED_FACTS.md`.

## ACCEPTANCE CRITERIA
- AGENTS.md exists at repo root.
- All required `.mcqueen/` files exist and are non-empty, with required headings.
- CURRENT_TASK has exactly one NEXT ACTION.
- VERIFIED_FACTS entries carry SOURCE references.
- Startup check + self-audit run read-only and report clean.
- Safe local tests pass (known pre-existing failures documented, not silently fixed).

## TEST PLAN
1. `.mcqueen/agent_startup_check.sh` — read-only env/context verification.
2. `python3 .mcqueen/agent_self_audit.py` — context-system health.
3. Repo tests: `python3 -m pytest tests/ mcqueen_ml/ -q` (safe, local, no hardware).
4. Record exact results.

## STATUS
IN PROGRESS (bootstrap phase)
