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

---

## DECISION 011 — .mcqueen state files are ALWAYS current (user mandate)

- **DATE**: 2026-08-13
- **QUESTION**: How diligently must the `.mcqueen/` state files be maintained?
- **EVIDENCE**: User (audit answers, 2026-08-13): "yes yes yes after each session and i
  really mean this… you must always and always make sure to keep the mcqueen statefiles
  very very well updated… the github we can update at home each night but the mcqueen
  state files gotta be flawlessly perfectly and extremely updated." Also: audit found
  HANDOFF/CURRENT_TASK/SESSION_LOG/AGENT_STATE stale after the commit+push.
- **DECISION**: Update `.mcqueen/` state files at the END of EVERY session (and at any
  material checkpoint), with current git state, task state, decisions, verified facts,
  and open questions. State files are MORE important than GitHub sync: GitHub may lag
  (nightly home sync sanctioned), state files never lag.
- **WHY**: Durable agent memory must be a flawless reflection of reality or it misleads
  every future session (source-of-truth hierarchy, AGENTS.md B).
- **CONSEQUENCES**: Session end is incomplete until state files are updated. This
  decision supersedes any earlier laxer habit; it does not change the push policy.
- **STATUS**: ACCEPTED

---

## DECISION 012 — GitHub sync at home each night is sanctioned

- **DATE**: 2026-08-13
- **QUESTION**: When may repo state be pushed to GitHub?
- **EVIDENCE**: User audit answer: "the github we can update at home each night";
  earlier rule was "update GitHub only when hardware works". The 2026-08-13 push
  (WAN code + evidence + agent system) was confirmed intentional.
- **DECISION**: Nightly home sync of committed work to GitHub is acceptable per user;
  the strict hardware-first rule applies to CLAIMS and milestone records, not to code
  sync. Pushes still require user awareness (never silent/background pushes).
- **WHY**: Evidence durability; user explicitly relaxed the rule.
- **CONSEQUENCES**: Commits may be pushed at home; hardware milestones still need
  hardware verification before being claimed.
- **STATUS**: SUPERSEDED (by DECISION 013, 2026-08-14)

---

## DECISION 013 — Hardware-verified commits/pushes only; state files are the master memory (user mandate)

- **DATE**: 2026-08-14
- **QUESTION**: When may code be committed or pushed to GitHub, and how must the `.mcqueen/`
  state files be maintained?
- **EVIDENCE**: User (2026-08-14): "stuff is pushed and committed onto github only and only
  when the shit is successfully tested on hardware"; "the mcqueen state files be ALWAYS be
  updated regardless of whatever task you do… the statefiles are our way to never let the
  agents and even be hallucinate on whats acheived and whats not… the master memory of the
  project"; next session must be able to "start from exactly where i left the project".
- **DECISION**: (1) Strict hardware-first GitHub policy: NOTHING is committed and NOTHING is
  pushed unless the change has been successfully verified on hardware. Untested or failed
  work stays local, no exceptions, even for small fixes. Software-only changes
  (documentation, state files) ride along in the next hardware-verified commit; they are not
  committed or pushed separately from home. (2) `.mcqueen/` state files are updated at the
  end of EVERY session regardless of task size and brought to handoff grade: a fresh agent
  with zero conversational memory must be able to resume the project exactly where it was
  left (verified state, pending work, blockers, exact NEXT ACTION, Git state).
- **WHY**: User reversed DECISION 012's nightly-sync relaxation — GitHub must reflect only
  hardware-proven work. The state files are the project's anti-hallucination master memory
  and must always be current and handoff-perfect.
- **CONSEQUENCES**: DECISION 012 is SUPERSEDED. The 2026-08-13 uncommitted WAN work
  (fixed sender, packetization test, home-debug doc, harness tweaks) stays local until the
  hardware run of `tools/realtime/run_rtp_wan_test.sh` goes green.
- **STATUS**: ACCEPTED

---

## DECISION 014 — Machine hygiene: RTX/Jetson keep only necessary McQueen stuff (user mandate)

- **DATE**: 2026-08-14
- **QUESTION**: What is allowed to live on / be removed from the RTX and Jetson?
- **EVIDENCE**: User (2026-08-14): "NEVER EVER FUCK ANYBODY ELSE'S STUFF IN THE RTX ITS A
  COMMON MACHINE NOT MY PRIVATE. remove only and only the mcqueen junk which aint useful
  anymore to us". Context: the 2026-08-13 lab left old sender/receiver copies, stale logs,
  pid files and a `~/Downloads/mcqueen_wan_direct_p2p` bundle on the RTX; broker.py was only
  in evidence, not repo-managed.
- **DECISION**: (1) The repo is the single source of truth for McQueen software — machines
  run deployed copies of repo files (e.g. `tools/realtime/broker.py` is scp'd by
  `run_rtp_wan_test.sh` every run), never hand-edited leftovers. (2) On the RTX, remove ONLY
  McQueen junk that is no longer useful: stale McQueen sender/receiver copies, old McQueen
  logs/pid files, outdated run scripts, superseded bundles once repo-managed. (3) NEVER
  touch, modify, or delete anything not verifiably McQueen's — it is a common machine. When
  in doubt, ask the human first, per item. (4) Keep-list (never remove): repo clone,
  gst-webrtc-venv, lerobot conda env, broker.py (repo-managed), cloudflared binary, McQueen
  data/checkpoints.
- **WHY**: A common machine must not be disturbed; McQueen junk must not accumulate and
  must not be confused with repo code.
- **CONSEQUENCES**: Cleanup happens only at the lab with per-item human approval. This rule
  is written into AGENTS.md §H as binding.
- **STATUS**: ACCEPTED

---

## DECISION 016 — 2026-08-14 lab: Plan A (CPU transport path), three approved receiver/sender fixes, five binding no-go constraints (user mandate)

- **DATE**: 2026-08-14
- **QUESTION**: How to get a flawless, sustained Jetson↔RTX full-loop test while the RTX GPU
  is 100% busy with a non-McQueen job (ViReL train.py)?
- **EVIDENCE**: L0 run proved transport (NAT punch, frames_rx=16, assoc_ok=1, ctrl_sent=1,
  rtp_ts advancing, 0 errors) but stalled at 16 frames — GPU-starved NVDEC ~1 fps → appsrc
  backpressure → socket Recv-Q full → drops. Three code bugs confirmed: (F10) receiver gates
  RTP→appsrc on `elif self.cur_meta is not None:`; (F11) no rtpjitterbuffer in pipeline;
  (F12) sender hardcodes `x264enc bitrate=2500` guess. User: "na do not touch virel at all".
- **DECISION**: (1) **Plan A**: force `avdec_h264` (CPU decode) + CPU dummy inference in the
  RTX receiver so the transport test never touches the GPU — ViReL becomes irrelevant.
  (2) **Fix 1**: decouple association from delivery — ALWAYS push RTP into appsrc, never gate
  on META (missing META → assoc_miss, never a delivery block). (3) **Fix 2**: add a BOUNDED
  rtpjitterbuffer (latency ≤ 50 ms, drop-on-late) between appsrc and rtph264depay. (4) **Fix 3**:
  set sender bitrate from measurement, not guess. (5) All work only in McQueen's own files;
  ViReL train.py (PID 490867, /home/junior/ViReL/Tasks/vlmgrpo) and all non-McQueen processes
  are UNTOUCHABLE. (6) Everything documented in `.mcqueen/` + logs.
- **BINDING NO-GO CONSTRAINTS (user)**: (1) never raise rtpjitterbuffer latency past 50 ms to
  paper over loss — strict 50 ms latency budget; (2) no retransmission/RTX — a late frame is
  useless, drop it; (3) never raise prediction_timeout_ms (250 ms) to stop stutter;
  (4) never go back to webrtcbin; (5) never chase NVENC — it stalls on this Jetpack, fix
  bitrate/resolution instead.
- **WHY**: The 100 ms target must not be gamed by masking loss/latency; the pipeline must be
  proven flawless at its true operating point; the common machine rule is absolute.
- **CONSEQUENCES**: Next session implements A1–A4 (user trigger: "fix the server thing") then
  reruns L0. Latency sub-second acceptable for the flawless proof; clean <100 ms re-measured
  when the GPU is free. Broker removal = separate PROPOSED item (Q9, user to speak).
- **STATUS**: ACCEPTED

---

## DECISION 018 — Broker removal decided (manual peer exchange); at-home approval rule; full-sweep cleanup (user mandates)

- **DATE**: 2026-08-14
- **QUESTION**: (1) Is the broker + cloudflared signaling stack being removed? (2) What code
  may be changed at home? (3) How much cleanup is allowed on the machines?
- **EVIDENCE**: User (2026-08-14): "can we just remove broker service on rtx from our
  equation if we just use manual copy paste… each side gotta learn the other's public ip
  port" → later, after estimates: "we will do both of those tasks tomorrow"; "even at home
  you must ask me for all this and wait for my approval"; cleanup: "remove all old tests and
  stuff that we dont need rn… keep old logs and shit thats fine but no files that were
  required for old shit" → full-sweep answer (junk AND old logs) when re-asked.
- **DECISION**: (1) **Broker REMOVAL APPROVED in direction** — replace broker+cloudflared
  signaling with manual peer exchange (both sides STUN; run script reads both PUBLIC lines
  over SSH; sender `--peer` mode; receiver learns the sender's source from incoming RTP).
  Execution DEFERRED to the next lab session (estimates given: ~1.5–2.5 h incl. live
  verify). Supersedes Q9's earlier "keep broker" run-package choice. (2) **At-home approval
  rule (BINDING):** ANY code/script change made at home (incl. fixing F7/F8/F9 in
  run_rtp_wan_test.sh) must be PROPOSED to the user and await explicit approval — nothing
  changes at home without asking. (3) **Cleanup full sweep executed**: git bundles (~50 MB),
  McQueen_files/, stale pids, old probe copies, __pycache__, old Aug 11–13 logs, install
  artifacts, ~/mcqueen scratch, ~/logs policy_server logs removed from both machines;
  manual-punch tools + today's evidence kept; keep-list verified; non-McQueen stuff never
  touched.
- **WHY**: The broker is signaling-only (NOT in the video/control data path) so removal
  doesn't change latency — it removes failure modes (stale tunnel URL F8, ws death Q11,
  cloudflared management). The at-home rule protects the user's control over the codebase;
  DECISION 014 governs the hygiene scope.
- **CONSEQUENCES**: Tomorrow: broker-removal code (needs approval first) + live verify;
  diagnostics (control-only RTT probe + 320×240); then the first hardware-verified commit
  (DECISION 013) incl. docs/ERROR_LOG_2026-08-14.md.
- **STATUS**: ACCEPTED (broker removal deferred; at-home rule + cleanup executed)

---

## DECISION 015 — Backbone weights never enter the repo; adapters refuse silent fallback

- **DATE**: 2026-08-14
- **QUESTION**: Where do pretrained backbone checkpoints (PPGeo ResNet-34, later Drive-JEPA)
  live, and what happens when a checkpoint is missing at inference time?
- **EVIDENCE**: PPGeo released checkpoint (Google Drive id `1GAeLgT3Bd_koN9bRPDU1ksMpMlWfGXbE`,
  BaiduYun backup code `itqi`) verified as a plain torchvision ResNet-34 state dict; `.gitignore`
  already excludes `*.pt/*.pth`. The older mcqueen_ml pattern silently substituted architectures
  when classes were missing — explicitly rejected for the realtime path.
- **DECISION**: (1) Checkpoints live OUTSIDE the repo (laptop `~/Downloads/mcqueen_ppgeo/`;
  machines: `data/checkpoints` keep-list per DECISION 014); the repo contains only the adapter
  code plus env-var override (`MCQUEEN_PPGEO_CKPT`). (2) Adapters must raise `RuntimeError` when
  the checkpoint is missing — never silently fall back to ImageNet or a different architecture.
- **WHY**: Weights are artifacts, not code; silent substitution produced the "real inference"
  lie risk this project is explicitly fighting (AGENTS.md C, F).
- **CONSEQUENCES**: Missing checkpoints fail loudly at load time; tests skip (not fail) when the
  checkpoint is absent so suites stay green without weights.
- **STATUS**: ACCEPTED

---

## DECISION 017 — 2026-08-14 lab: reset loop-test files to GitHub HEAD, apply ONLY the user-listed fixes; GStreamer 1.20 uses drop-on-latency (user mandate)

- **DATE**: 2026-08-14
- **QUESTION**: The peer/probe iteration from earlier today (broker-removal + bitrate probe
  experiments) produced a run of errors. User asked: reset ALL files we debugged to GitHub
  state and apply ONLY the listed fixes, so the session stops churning. What exactly gets
  reset, what gets applied, and how is the jitter buffer expressed on the deployed stack?
- **EVIDENCE**: User (2026-08-14): "reset all the files which we debugged and fixed yesterday
  and today and right now as well, to the files that are already at the github then make only
  the changes that i listed and not your probe pkill self kill changes… if you hit ALL the
  same bugs then stop the process urgently and lmk the bugs". Committed run script still
  contains F7/F8/F9 (pkill self-kill, stale URL read, sudo hang) — leave them, note the bugs.
  Live verification on the RTX showed GStreamer 1.20.3's rtpjitterbuffer has `drop-on-latency`
  and NOT `drop-on-late` (parse error on the old name).
- **DECISION**: (1) `git checkout HEAD --` sender/receiver/run-script; apply ONLY: Fix 1
  (decouple association from delivery — always push RTP), Fix 2 (rtpjitterbuffer latency=50
  drop-on-latency=true, no rtx), Fix 3 (bitrate from measurement via `--bitrate-kbps` +
  achieved-kbps print), CPU decode (avdec_h264) + CPU dummy inference, and the rolling
  FULL_LOOP_LATENCY print (user-approved: needed to see the number). Run script UNTOUCHED.
  (2) The jitter buffer uses the stack's actual property name — `drop-on-latency` on
  GStreamer 1.20 (1.20 removed `drop-on-late`); verify against the deployed element before
  relying on any property. (3) If the committed script's known bugs (F7/F8/F9) re-manifest:
  note them; if ALL manifest, stop and report to the user (for their senior) before any
  workaround; manual start is pre-approved when bugs are partial.
- **WHY**: Stop implementation churn; trust the committed baseline + only the approved fixes;
  the deployed GStreamer is the source of truth for element properties (AGENTS.md I).
- **CONSEQUENCES**: All peer/probe/direct-mode experiments from earlier today are DISCARDED
  (broker flow kept, per user). F7/F8/F9 stay in the committed script until the user approves
  fixing them. DECISION 016's Fix 1/2/3 are now implemented and hardware-verified (FULL LOOP
  p50 ≈ 391 ms on the hotspot link).
- **STATUS**: VERIFIED
