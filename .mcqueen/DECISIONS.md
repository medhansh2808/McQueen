# DECISIONS.md — McQueen decision log

Each decision records: DATE, QUESTION, EVIDENCE, OPTIONS, DECISION, WHY, CONSEQUENCES, STATUS.
Statuses: PROPOSED / ACCEPTED / VERIFIED / SUPERSEDED / REJECTED.
Never silently overwrite historical decisions — append and mark superseded.

---

## DECISION 001 — Adopt repository-based agent contract + context system

- **DATE**: 2026-08-13
- **QUESTION**: How does the McQueen agent keep durable context and operating rules across
  sessions without ChatGPT?
- **EVIDENCE**: User bootstrap directive; prior session showed critical context living only in an
  untracked local folder (`context stuff for understanding the mcqueen project/`) and in
  conversational memory. `.mcqueen/`, `.freebuff/`, `.suprmind/` exist but were empty.
  `.gitignore` does not exclude `.mcqueen/` or `AGENTS.md`.
- **OPTIONS**:
  1. Repo-root `AGENTS.md` + `.mcqueen/` Markdown state files (durable, commit-able, model-independent).
  2. Rely on conversational memory / external AI handoffs (ChatGPT) — rejected: user explicitly
     removing ChatGPT dependence.
- **DECISION**: Create `AGENTS.md` (authoritative contract, sections A–Q) and `.mcqueen/`
  state files (`AGENT_STATE`, `CURRENT_TASK`, `DECISIONS`, `SESSION_LOG`, `VERIFIED_FACTS`,
  `OPEN_QUESTIONS`, `HANDOFF`, `PROJECT_INDEX`, `COMMAND_POLICY`) plus read-only startup check
  and self-audit scripts.
- **WHY**: Repository-based memory survives session loss, is version-controllable, and keeps the
  project model-provider-independent.
- **CONSEQUENCES**: Agent must read AGENTS.md + `.mcqueen/` at session start and update them at
  session end. Docs must stay concise (facts/decisions, not repo duplication).
- **STATUS**: ACCEPTED (being verified this session)

---

## DECISION 002 — Proof levels are strictly separated

- **DATE**: 2026-08-13 (recording existing project policy, per docs/HARDWARE_MILESTONES_2026-08-11.md
  and docs/HOME_VALIDATED_2026-08-12.md)
- **QUESTION**: May home/synthetic tests be counted as hardware milestones?
- **EVIDENCE**: Docs explicitly separate hardware-verified lab results from home-validated
  software. Docs state no home/synthetic test is a hardware milestone.
- **DECISION**: Keep the separation. Hardware claims require hardware evidence.
- **WHY**: Prevents inflated claims; matches the project's own scope rules.
- **CONSEQUENCES**: Latency/inference/WebRTC/model claims must be labeled with their true proof
  level (e.g., "synthetic benchmark = 70 ms", not "McQueen realtime loop = 70 ms").
- **STATUS**: ACCEPTED (existing policy, now agent-enforced)

---

## DECISION 003 — Realtime association uses exact frame identity, never FIFO

- **DATE**: 2026-08-13 (recording existing policy from docs/full_loop_benchmark_v2.md and
  docs/REALTIME_INFERENCE_V1.md)
- **QUESTION**: How to pair RTX predictions with Jetson video observations?
- **EVIDENCE**: Benchmark-v2 contract requires Jetson-origin `frame_id` + `capture_mono_ns`,
  echoed by the RTX prediction; FIFO/deque proximity is forbidden; latency computed on the
  Jetson monotonic clock as `receive_mono_ns − capture_mono_ns`; newest-frame-wins on the RTX.
- **DECISION**: Follow the exact-frame-association contract in all realtime work.
- **WHY**: Independently transported frame metadata must not be guessed; a single monotonic clock
  gives the only authoritative latency.
- **CONSEQUENCES**: Any new realtime code must implement frame_id echo + monotonic timestamps.
- **STATUS**: ACCEPTED (existing policy, now agent-enforced)

---

## DECISION 004 — Jetson/RTX access requires explicit per-command human authorization

- **DATE**: 2026-08-13
- **QUESTION**: May the agent SSH/execute on Jetson or RTX unattended?
- **EVIDENCE**: User instruction: passwords required every time; "in absolutely no sense or
  manner or context" will unrestricted access be allowed; machines are expensive.
- **DECISION**: Never SSH/execute remotely without explicit human authorization for each command;
  the human types passwords. Prefer dry-run / mock / local paths first.
- **WHY**: Hardware safety + user mandate (AGENTS.md sections G, H).
- **CONSEQUENCES**: All remote steps in lab runbooks pause for human approval.
- **STATUS**: ACCEPTED

---

## DECISION 005 — Do not commit the agent bootstrap automatically

- **DATE**: 2026-08-13
- **QUESTION**: Should AGENTS.md / .mcqueen/ be committed and pushed now?
- **EVIDENCE**: User: "when everything properly works on hardware then only update github";
  bootstrap says "Do not commit or push anything automatically."
- **DECISION**: Create files locally only. No git add/commit/push in this bootstrap.
- **WHY**: User's explicit git discipline.
- **CONSEQUENCES**: Files remain untracked until the user authorizes a commit.
- **STATUS**: SUPERSEDED (by DECISION 006)

---

## DECISION 006 — Commit the agent system locally (no push)

- **DATE**: 2026-08-13
- **QUESTION**: Should AGENTS.md + .mcqueen/ be committed to git so the guidelines survive
  re-clones/resets?
- **EVIDENCE**: User answered "Commit now" when asked, explicitly separating agent files from
  the "update GitHub only when hardware works" production rule.
- **DECISION**: `git add AGENTS.md .mcqueen/` and commit locally. NO push. The untracked
  `context stuff for understanding the mcqueen project/` folder stays out of git.
- **WHY**: Guidelines must survive re-clones/resets; committing is the only durable guarantee.
- **CONSEQUENCES**: The agent contract becomes part of the repo history.
- **STATUS**: ACCEPTED

---

## DECISION 007 — Session-start trigger: agent self-triggers AND user phrase as backup

- **DATE**: 2026-08-13
- **QUESTION**: How is a fresh Freebuff session guaranteed to follow the guidelines, given
  Freebuff cannot auto-load AGENTS.md?
- **EVIDENCE**: Freebuff discovery (SESSION_LOG) — no native project-instructions mechanism.
  User answered "Both". Later superseded the backup phrase (see below).
- **DECISION**: Every new session starts by running `.mcqueen/agent_startup_check.sh` and
  reading AGENTS.md + `.mcqueen/` state files before any work; user may also open sessions with
  trigger phrases as a backup.
- **WHY**: Robustness — two independent triggers.
- **CONSEQUENCES**: Startup protocol is mandatory at session open; recorded in HANDOFF.md.
- **STATUS**: SUPERSEDED (phrase updated by DECISION 009)

---

## DECISION 009 — Session trigger phrases: "im at home" / "im at lab"

- **DATE**: 2026-08-13
- **QUESTION**: Which phrase(s) does the user use to start a session?
- **EVIDENCE**: User instruction — replace the single phrase with two: "im at home" and
  "im at lab"; one of them will be at the start of every session (even in big prompts).
- **DECISION**: The trigger phrases are "im at home" (HOME mode: software-validation,
  laptop-only, no hardware claims, no Jetson/RTX access) and "im at lab" (LAB mode:
  hardware-verification, Jetson/RTX available, remote work begins with per-command human
  authorization). Both also trigger the mandatory startup protocol.
- **WHY**: The phrase doubles as a working-mode switch, matching the project's
  home-vs-lab proof separation.
- **CONSEQUENCES**: Sessions without either phrase still self-trigger via the startup protocol;
  the phrases add explicit mode signaling.
- **STATUS**: ACCEPTED

---

## DECISION 010 — Lab-exit pull: mirror all machine state to laptop; fix confirmed sender bug

- **DATE**: 2026-08-13
- **QUESTION**: User is leaving the lab and needs everything (Jetson + RTX) on the laptop for
  home debugging, plus repo state updated.
- **EVIDENCE**: WAN-pipeline work lives only on the machines + untracked laptop files; 19-error
  log documented the session; deployed scripts differ from laptop copies (md5s).
- **OPTIONS**: (1) Pull everything and mirror into repo evidence; (2) pull nothing, rely on
  memory. (2) rejected — machine state would be lost.
- **DECISION**: Pull all WAN scripts/logs/pids + recordings from Jetson and RTX into
  `docs/evidence/2026-08-13-lab-pull/` + `data/lab_pull_20260813/` (gitignored); fix the
  confirmed `% 30 < n` NameError on the laptop sender copy; document findings; update all
  `.mcqueen/` files. Use transient SSH_ASKPASS helper (error-log #1 pattern), delete after.
- **WHY**: Home debugging + a future safe GitHub update need exact machine snapshots; the
  NameError is a verified root-cause candidate for the frozen rtp_ts / frames_rx=0 symptom.
- **CONSEQUENCES**: Evidence is now durable in-repo; sender must be redeployed next lab; RTX
  receiver needs venv python. Code remains uncommitted until user authorizes.
- **STATUS**: ACCEPTED (pull + fix done, verified)

---

## DECISION 008 — Supermind context dumps are reference material, not binding rules

- **DATE**: 2026-08-13
- **QUESTION**: Do the Supermind context files (`context stuff for understanding the mcqueen
  project/`) count as binding guidelines?
- **EVIDENCE**: User answered "Reference only".
- **DECISION**: AGENTS.md + .mcqueen/ are the binding rules. Supermind dumps are background
  reading only and never override AGENTS.md.
- **WHY**: Structured contract beats unstructured dumps; avoids contradictory "constitutions".
- **CONSEQUENCES**: Where Supermind dumps conflict with AGENTS.md, AGENTS.md wins.
- **STATUS**: ACCEPTED
