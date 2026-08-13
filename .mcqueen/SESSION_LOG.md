# SESSION_LOG.md — McQueen session log

Append chronologically. Newest at the bottom.

---

## 2026-08-13 — Full-lab-day audit + state refresh + debug kickoff (user "im at home… complete audit of today's day… don't solve problems just list" then "debug it all rn")

**Mode**: HOME. User asked for a complete audit of the 2026-08-13 lab day, then
(gfter answering audit questions) authorized full offline debugging so tomorrow's
lab is hardware-test-only.

**Audit findings (delivered to user, full detail in chat)**
- Day timeline: 15:20 agent bootstrap commit, 15:27 trigger-phrase commit, afternoon
  lab WAN work (WebRTC dead on Jetson → NAT-punched raw RTP transport built),
  20:02–20:05 lab-exit pull, 20:20 run_rtp_wan_test.sh, 20:27 WAN code+evidence
  commit, 20:32 edge-test/preflight/runbook fixes commit, then PUSH to GitHub.
- KEY DISCOVERY: everything is COMMITTED AND PUSHED — origin/jetson-nano == local
  HEAD `6698d41`. The `.mcqueen/` files still described the pre-push state.
- Problem ledger (21 error-log entries + F1–F6): WebRTC srflx (workaround: raw RTP),
  SSH/ARP/pid/username friction (resolved), sender bugs #9/#16/F1 (fixed), #19 stall
  (OPEN), F2 venv receiver (resolved), F3/F4/F5 (documented, redeploy pending),
  4 pre-existing repo issues → 3 fixed in 6698d41, 1 still env-blocked (torch).
- Verified current state: startup check 35/35 PASS; pytest 18 passed / 1 env-blocked;
  F1 fix present at line 414; only untracked item = context folder (intentional).

**User answers to audit questions (binding)**
- GitHub push was INTENTIONAL — evidence stays in repo.
- Next goal: flawless <100ms pipeline — debug everything tonight offline.
- NEW MANDATE (DECISION 011): `.mcqueen/` state files must ALWAYS be updated at
  session end, flawlessly. GitHub can be synced at home each night.
- Next lab hardware: camera yes, drivetrain no.

**Actions taken this session**
- Refreshed AGENT_STATE.md + CURRENT_TASK.md for home-debug mode; recorded
  DECISION 011; resolved OPEN_QUESTIONS Q6 (push done); updated HANDOFF git state;
  added VERIFIED_FACTS for the push. (This entry + final refresh at session end.)
- Started offline debugging of the WAN video path (sender #19 stall + Q2b) — see
  results in the next SESSION_LOG entry / CURRENT_TASK + DECISIONS.

---

## 2026-08-13 — Home debug of WAN video path: root causes pinned, fixes + tests done

**Mode**: HOME. User: "debug it all rn so tomorrow morning we just test on hardware".

**Root-cause findings (from pulled evidence, code-level):**
- lab13/14/15 receiver `frames_rx` counters counted UDP MARKER bits, NOT decoded
  frames (old sender set marker on EVERY packet via `(96 << 1)` PT-byte bug;
  decoded frames were zero — no `[RTX-GST] VIDEO` line anywhere).
- lab15 "waiting for start": FU-A fragments never completing + AUD NALs (type 9)
  flushing the depay mid-fragment. New sender drops AUD + completes FU-A.
- #19 stall = NVENC-era chain (v4l2src/NVDEC/NVENC, log ends at NVENC init); new
  sender uses cv2 (proven) + x264 SW (isolated test: x264 flows, NVENC stalls).
- The NEW sender's cv2→appsrc→x264→probe chain ALREADY ran ~12 min on the Jetson
  (22,209 probe firings at 19:20); only failure was F1 NameError freezing rtp_ts.

**Code changes (laptop copies, tools/realtime/):**
- Refactor (zero behavior change): probe → _on_rtp_probe (map) → handle_au (frame
  logic) → send_au (packetization) — pure path now unit-testable offline.
- NEW hardening: non-VCL AUs (SPS/PPS/SEI as separate buffers) held + prepended to
  the next VCL AU → exactly ONE capture entry + ONE rtp_ts step per video frame
  (protects exact frame_id association contract).
- run_rtp_wan_test.sh: resets /tmp/mcq_sender_probe_errors.log at deploy; RESULT
  now prints probe-error count + last SENT (rtp_ts) + last VIDEO (frames_rx) lines.
- NEW offline unit test tools/realtime/test_rtp_packetization.py (6 tests: AUD
  drop, marker-only-on-last, FU-A S/E bits, per-frame ts, one-META-per-frame,
  non-VCL hold, 100-frame F1 no-crash guard).

**Verified:** test_rtp_packetization 6/6 PASS; test_rtp_association PASS; py_compile
OK; bash -n OK; AST undefined-name scan clean (all flags false positives, verified
line-by-line); pytest tests/ 7 passed; startup check 35/35 PASS.

**Artifacts:** docs/HOME_DEBUG_2026-08-13.md = full findings + tomorrow's checklist.

**Remaining unknowns (hardware-only):** end-to-end latency with new sender; x264 CPU
headroom at 640x480@30; cv2 cadence; SPS/PPS buffer layout (hardening covers both).

**Next action:** tomorrow at lab — `./tools/realtime/run_rtp_wan_test.sh` in a real
terminal; expect green + FULL_LOOP_LATENCY line. This is a TEST-ONLY session.


## 2026-08-13 — Final home-readiness audit + run script (user asked "super sure?")

- Re-verified every item needed for home debug + GitHub update (file-by-file):
  WAN code (fixed sender 5377eccc…, receiver = RTX md5-identical), 78-file evidence
  pull, recordings 22M, all preflight docs, direct-UDP proof code. All present.
- Found + pulled 3 more Jetson artifacts: `/tmp/gst_jetson_rtp_wan.py` (the EXACT
  buggy 584-line sender, md5 ecd09a69 = pre-fix laptop copy — smoking gun for the
  NameError flood), install_jetson_static.sh, preflight_jetson_webrtc.sh, preflight.sh.
- RTX check: outputs/ + wandb/ empty (nothing unique); ~/logs has old policy_server
  logs (Jul 30, not part of WAN work). RTX venv python `import websocket` OK.
- Git: origin/jetson-nano is 2 commits behind (cf8ac2c + 3038cbc — agent contract
  + trigger phrases, committed earlier, never pushed). Everything up to 5cc716c
  already on origin. "Update GitHub at home" = commit the untracked WAN code +
  evidence + push those 2 pending commits. Fully doable from home, no hardware.
- GAP FOUND + FIXED: no run script existed for the NEW RTP transport (only the
  WebRTC-era run_direct_wan_test.sh). Created `tools/realtime/run_rtp_wan_test.sh`
  (chmod +x, bash -n OK): auto-detects RTX IP (wired→wifi), starts broker +
  cloudflared, deploys the FIXED sender to Jetson + receiver to RTX, starts
  receiver with the venv python (F2), starts sender, waits 35s, reports stage-
  by-stage result. Encodes lessons F1/F2/F3. To run tomorrow: real terminal,
  `./tools/realtime/run_rtp_wan_test.sh` (interactive passwords).
- Helper deleted again after final sweep.

---

## 2026-08-13 — Lab exit: full Jetson + RTX pull to laptop (user "get all the stuff")

**Mode**: LAB (user at lab, leaving for home). Explicit authorization to pull
all code + logs + recordings from both machines and update repo state.

**What happened**
- Startup protocol: `agent_startup_check.sh` 35 PASS; git clean except 5 untracked
  WAN-pipeline files + context folder; HEAD `cf8ac2c`.
- Verified reachability: Jetson `sravjti@192.168.55.1` (USB, 2ms), RTX
  `junior@192.168.0.132` (wired, 5ms) + `.179` (wifi). Passwords user-provided
  (Jetson + RTX passwords REDACTED from git — user supplies them interactively); used
  transient SSH_ASKPASS helper (error-log
  workaround #1), helper DELETED after use.
- Pulled (tar-over-SSH, timestamps preserved) into `docs/evidence/2026-08-13-lab-pull/`:
  Jetson home WAN scripts/logs/pids + `/tmp/mcq_sender_probe_errors.log`;
  RTX `/var/tmp/mcqueen-junior/` receiver scripts, broker.py, cloudflared state,
  ALL 15 `gst_rtx_rtp_receiver_lab*.log` runs. Recordings into
  `data/lab_pull_20260813/` (jetson_spool 2 sessions, rtx_raw 7.2M).
- Machine state at pull: Jetson mcqueen-edge.service inactive+enabled, camera
  present, kernel 4.9.253; RTX broker + cloudflared RUNNING
  (URL disposition-cabinets-mariah-glad.trycloudflare.com).

**What was tested / found (home-debug gold)**
- **F1 (critical, FIXED)**: laptop sender `tools/realtime/gst_jetson_rtp_wan.py`
  line 414 `if self.sent_pkts % 30 < n:` — `n` undefined. Probe-error log =
  22,209 identical NameError lines. Exception fires BEFORE rtp_ts increment, so
  rtp_ts never advances -> all frames sent with ts=0 -> rtph264depay merges to
  1 AU (matches frames_rx=0 symptom). Fixed to `% 30 == 0` (matches deployed
  sender). py_compile + test_rtp_association.py PASS.
- **F2**: RTX lab16 log = `ModuleNotFoundError: websocket` — receiver started
  with system python; must use gst-webrtc-venv python.
- **F3**: lab15 (4.6MB, 4m27s) shows depay stuck "waiting for start" with FU-A
  S=1/E=0 + AUD (NAL 9) packets — the orphan pattern the new sender's AUD-drop
  + manual packetization fix. lab15 ran the OLDER NVENC-era sender.
- **F4**: deployed Jetson sender (17:25, 411 lines, v4l2src/NVENC) is OLDER
  than laptop copy (19:20, 584 lines, cv2+x264). RTX deployed receiver md5
  IDENTICAL to laptop copy.
- Unit tests: `test_rtp_association.py` PASS (5 frames exact order); all three
  realtime scripts py_compile OK.

**Git state**: branch jetson-nano, HEAD `cf8ac2c`; worktree now has untracked
WAN files + evidence pull + data pull (gitignored `data/`). Nothing committed.

**What remains (home)**: diff/deploy fixed sender next lab; start RTX receiver
with venv python; re-run full loop and confirm SENT-throttle prints + rtp_ts
advances. Recordings pulled for offline analysis.

---

## 2026-08-13 — Session trigger phrases updated (user instruction)

- Replaced the single backup phrase "per AGENTS.md, start session" with two mode-signaling
  trigger phrases (DECISION 009): "im at home" (HOME mode — software-validation, laptop-only)
  and "im at lab" (LAB mode — hardware-verification, Jetson/RTX work with per-command
  authorization). Both trigger the mandatory startup protocol. Updated HANDOFF.md,
  AGENT_STATE.md, DECISIONS.md; committed locally.

---

## 2026-08-13 — Re-verification pass (Freebuff, user requested rerun from step 6)

**Re-ran all verification fresh. Results identical to first pass:**
- `.mcqueen/agent_startup_check.sh`: **35 PASS / 0 FAIL / 0 WARN — OK** (branch jetson-nano,
  HEAD 5cc716c, 3 untracked paths).
- `python3 .mcqueen/agent_self_audit.py`: **20 checks, 0 problems — healthy**.
- Full suite `pytest tests/ mcqueen_ml/`: **3 collection errors** (unchanged, pre-existing):
  1. `test_jetson_edge_app.py` — module-level assert `started["recording"] is True` fails
     (`/api/log/start` returns `recording: False` in this env).
  2. `test_jetson_http_server.py` — stale: expects `OAK-D/WebRTC` in HTML that
     `http_server.py` no longer emits (current page says "McQueen Camera").
  3. `test_temporal_policy_v2.py` — `ModuleNotFoundError: torch` (torch lives in
     `mcqueen-laptop` env, not system python 3.10).
- Suite excluding those 3: **18 passed in 0.47s**.
- Git integrity: `git diff HEAD` empty; test files byte-identical to HEAD; only untracked
  additions (`AGENTS.md`, `.mcqueen/`, pre-existing context folder). Bootstrap caused zero
  changes to tracked code.

**Absolute current condition (2026-08-13):** agent context system fully healthy;
project test suite = 18 pass + 3 pre-existing broken collectors (documented in
VERIFIED_FACTS / OPEN_QUESTIONS, to be fixed when user authorizes).

**Completeness audit (user asked "is the setup fully complete?")**: re-checked every phase
against the bootstrap spec. Found one gap: `agent_startup_check.sh` and `agent_self_audit.py`
were not executable (Phase 9/10 "make it executable if appropriate"). Fixed with `chmod +x`,
re-ran both via `./` — both still pass (35/35, 20/20). Full checklist now green: 17/17 AGENTS.md
sections, all 11 .mcqueen files non-empty, 5 decisions, 21 facts, exactly 1 NEXT ACTION,
Freebuff discovery recorded, both scripts executable.

---

## 2026-08-13 — Agent bootstrap (Freebuff)

**What happened**
- Executed the "FINAL LOCAL AGENT BOOTSTRAP": created `AGENTS.md` (sections A–Q) and the
  `.mcqueen/` context system (state files, index, command policy, startup check, self-audit).
- Phase 0 inspection (read-only): branch `jetson-nano`, HEAD `5cc716c`,
  remote `https://github.com/medhansh2808/McQueen.git`, worktree clean except untracked
  `context stuff for understanding the mcqueen project/`. All 13 key docs present. Python 3.10.12.
- Freebuff native discovery: config lives in `~/.config/manicode/` (`settings.json`,
  `freebuff-metadata.json`, `projects/McQueen/chats/...`). `settings.json` contains only
  `mode`, `adsEnabled`, `freebuffModel`, `hasSubmittedFirstPrompt`.

**What was tested (Phase 11, 2026-08-13)**
- `.mcqueen/agent_startup_check.sh`: **35 PASS / 0 FAIL / 0 WARN** — repository, AGENTS.md,
  all 11 state/script files, git, 11 docs, 7 realtime files, 13 test files, python3.10.12.
- `python3 .mcqueen/agent_self_audit.py`: **20 checks, 0 problems — healthy**. One fix during
  verification: CURRENT_TASK NEXT ACTION was a paragraph; reformatted to a single bullet so the
  exactly-one-action rule is countable.
- Safe repo tests `python3 -m pytest tests/ mcqueen_ml/ -q` (excluding 3 known-bad collectors):
  **18 passed**. Pre-existing collection errors (unchanged code, NOT caused by bootstrap):
  1. `tests/test_jetson_edge_app.py` — asserts at import time; `/api/log/start` returns
     `recording: False` in this environment.
  2. `tests/test_jetson_http_server.py` — stale test expects old `OAK-D/WebRTC` HTML;
     current `http_server.py` no longer emits it (already flagged in VERIFIED_FACTS).
  3. `mcqueen_ml/training/test_temporal_policy_v2.py` — needs `torch`, which lives in the
     `mcqueen-laptop` env, not system python3.10.
- `git status` after bootstrap: only untracked additions (`AGENTS.md`, `.mcqueen/`, plus the
  pre-existing untracked context folder). `git diff` = empty; HEAD `5cc716c` unchanged.

**What remains**
- User returns to lab → Phase A lab runbook (Jetson preflight → PWM live probe → RTX candidate
  tests → Option A server hardening → full-loop benchmark-v2). See HANDOFF.md.

**Git state**
- Clean except new untracked agent files (AGENTS.md, .mcqueen/*). NOT committed (per user rule).

**Freebuff capability notes**
- Native command-approval: Freebuff's terminal tool prompts the user for approval on
  non-trivial commands (implemented in the Freebuff runtime, not in repo files).
- Persistent project memory: NOT SUPPORTED BY FREEBUFF as a configurable feature — Freebuff
  stores per-chat history under `~/.config/manicode/projects/McQueen/chats/`, but there is no
  exposed project-instructions or persistent-memory configuration surface. The repo-based
  `.mcqueen/` system is the durable memory instead.
- Path restrictions: Freebuff scopes file reads/writes to the project root
  (`/home/kartik/McQueenWork/McQueen`); Markdown rules enforce behavior, not technical sandboxing.
