# COMMAND_POLICY.md — McQueen agent operational command policy

This is NOT a security mechanism. It is the agent's operational command policy.
Freebuff's native tool approval prompts remain the technical gate; this file defines how the
agent SHOULD behave.

Require explicit human approval for REVIEW_REQUIRED, HARDWARE_RISK, REMOTE_RISK, and
DESTRUCTIVE operations (unless Freebuff's native permission system independently provides an
approved mechanism — see `.mcqueen/SESSION_LOG.md` for what Freebuff natively enforces).

## SAFE_READ (no approval needed)
Read-only inspection. Examples:
- `pwd`, `ls`, `find`, `cat`, `head`, `tail`, `wc`
- `grep`, `rg` (code_search)
- `git status`, `git diff`, `git log`, `git rev-parse`
- `python3 -m py_compile <file>` (syntax check, no side effects)
- running unit tests / pytest locally
- reading docs, evidence files, configs
- `df -h`, `free -h` (local info)

## SAFE_LOCAL_WRITE (no approval needed)
Changes confined to the repo, reversible via git. Examples:
- creating/editing source files, tests, documentation inside the repo
- creating `.mcqueen/` state files
- `git add` / `git commit` ONLY when the user explicitly asks for a commit

## REVIEW_REQUIRED (ask before running)
Changes to environment/system/deployment/architecture. Examples:
- installing packages (pip, apt) — see AGENTS.md section I (dependency discipline)
- modifying/starting/stopping system services (systemd)
- modifying network configuration (routes, firewalls, interfaces)
- changing deployment configs
- database/schema migrations
- major architecture changes
- `git push` (never without explicit authorization)

## HARDWARE_RISK (ask before running; prefer dry-run/simulated first)
Anything that could move or damage physical hardware. Examples:
- GPIO writes, PWM, motor, servo, actuator commands
- physical vehicle movement
- flashing MCUs
- powering/cycling hardware
- Jetson GPIO backend (vs MockDriveBackend)

## REMOTE_RISK (ask before running; every single time)
Anything touching Jetson or RTX. Examples:
- `ssh` to Jetson/RTX (passwords are typed by the human, never the agent)
- remote execution, remote installation, remote service modification
- copying files to/from Jetson/RTX
- any `scp`/`rsync` to hardware
- running preflight scripts ON the Jetson/RTX

## DESTRUCTIVE (ask before running; almost never)
Irreversible or data-destroying. Examples:
- `git reset --hard`, `git clean -fd`, `git push --force`
- `rm -rf`, deleting project data or unknown files
- overwriting unknown files
- destructive system commands (disk format, fdisk, etc.)

## Hard rules
1. NO unattended Jetson/RTX access — ever. Human enters credentials/approves each command.
2. NO `sudo` unless explicitly authorized.
3. NO git push without explicit user authorization.
4. Hardware work: dry-run → disconnected → simulated → then, with approval, physical.
5. When in doubt, classify as the higher-risk category and ask.
6. Never bypass safety limits to make a test pass.
