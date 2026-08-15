# DECISIONS.md — McQueen decision log

Each decision records: DATE, QUESTION, EVIDENCE, OPTIONS, DECISION, WHY, CONSEQUENCES, STATUS.
Statuses: PROPOSED / ACCEPTED / VERIFIED / SUPERSEDED / REJECTED.
Never silently overwrite historical decisions — append and mark superseded.

---

- **DATE**: 2026-08-13
## DECISION 001 — Adopt repository-based agent contract + context system

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

## DECISION 019 — Brokerless re-punch trick; one-tap RESUME re-engage; bitrate A/B replaces theory (user mandates, 2026-08-14 home session 2i)

- **DATE**: 2026-08-14 (home planning session)
- **QUESTION**: (1) What replaces the broker/cloudflared signaling for re-punch on road
  hole-death? (2) How does the car resume after an automatic link-loss stop? (3) Is the
  150 kbps bitrate choice final?
- **EVIDENCE**: User (2026-08-14 evening): broker should be gone for lab AND road sessions;
  only a tiny fallback for road hole-death ("extremely simple and extremely functional");
  rejected aiohttp/cloudflared rewrite ("why tf we using aiohttp if we dropped aiortc and
  why tf still cloudflare"); accepted the re-punch trick; "both holes dead we can plan a
  fallback for that but not rn… we fix it only when we face it"; approved one-tap RESUME
  button ("i dont have a problem with a simple resume button which i gotta tap once");
  "i would say yes run a proper bitrate test at the lab… we need a reason to stick to 150
  or simply find a better one". 2b evidence: 400 kbps on the new network → p50 ~160 ms vs
  150 kbps → 224–287 ms; 400-run loss was NEVER LOGGED (gap); 400 kbps on the OLD network
  lost ~55% of frames (14.1 fps, p95 1.67 s).
- **OPTIONS**: (a) tiny broker rewrite (no aiohttp, no cloudflared); (b) **brokerless
  re-punch trick** — NAT mappings are destination-independent: the RTX's hole stays alive
  via keepalives even when the Jetson rebinds, so the Jetson re-STUNs and sends a NEWCAND
  datagram to the RTX's known endpoint through its still-open mapping; (c) keep 150 kbps
  on theory; (d) bitrate A/B at the lab.
- **DECISION**: (1) **Brokerless re-punch trick is THE fallback** — no broker rewrite, no
  aiohttp, no cloudflared in the new design; validate the trick at the lab (kill hole →
  rebind → NEWCAND recovery) BEFORE removing broker.py from the repo; once lab-proven,
  broker.py + cloudflared wiring are removed from the repo in the same hardware-verified
  commit. (2) **Both-holes-dead** (RTX reboot/ISP rebind + Jetson rebind simultaneously):
  FUTURE TASK — design/fallback only when we face it. (3) **One-tap RESUME re-engage**:
  Kachow app RESUME button (visible only when the gate is in resume-required state) →
  sends `R` packet → gate clears `resume_required` → existing neutral-before-motion rule
  applies. Watchdog (automatic) stops require RESUME; manual E-stop does NOT. (4)
  **Bitrate is NOT final** — 150 kbps was a network-specific choice on the old link, never
  A/B-proven; the lab runs a proper bitrate A/B (150/300/400 kbps ×2 cycles, same network,
  per-run loss + frames_rx + p50/p95 logged — the 400-run loss gap must never recur).
- **WHY**: Broker/cloudflared are signaling-only (NOT in the media path — DIRECT_UDP
  proven), so removal changes robustness, not latency; the re-punch trick removes the
  broker dependency entirely using already-proven mechanisms (STUN + punched UDP +
  keepalives). Auto-resume after a blackout is unsafe — human re-engage is the safety
  gate's explicit acknowledgment. Bitrate affects queueing AND model-visible quality, so
  it must be data-driven on the actual network.
- **CONSEQUENCES**: Tomorrow's lab order: (1) TRUE PATH RTT (Jetson pings RTX public IP
  14.139.108.62, NOT 1.1.1.1) → (2) bitrate A/B (150/300/400 ×2, loss-logged) → (3)
  320×240+pacing only if the floor justifies → (4) re-punch trick validation → (5) real
  dataset recording → (6) evidence + first-commit-plus (broker.py removal rides it if
  validation passed). RESUME Jetson-side code (protocol `R` + gate `resume_required` +
  tests) is laptop-implemented now (this session, approved); Kachow button code-only now,
  build+verify at lab. Re-punch watcher + both-holes-dead fallback = future tasks.
- **STATUS**: ACCEPTED (RESUME gate implemented + laptop-tested this session; A/B + re-punch
  validation pending lab)

---

## DECISION 020 — Strict todo-list discipline (user mandate 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: The human wants a hard, binding rule that a live, accurate, visible todo
  list exists for EVERY agent session — the todo panel is the human's real-time view of
  agent work, and it kept going stale or vanishing.
- **EVIDENCE**: User observed: (a) todo statuses not updated to match the actual task
  being performed, (b) completed items not marked as done, (c) the list disappearing
  "so quickly" — cause: a fully-completed list auto-collapses in the TUI, and the list
  is session-scoped (fresh sessions start empty).
- **OPTIONS**: (1) soft guideline in state files; (2) binding AGENTS.md section with no
  exceptions; (3) binding section with a carve-out for pure conversational Q&A. User
  chose STRICT (2) — every session, even a single trivial task.
- **DECISION**: New binding AGENTS.md section R "TODO LIST DISCIPLINE": always open a
  detailed todo list first (no generic placeholders; state-file/verification/commit
  items included); update in real time with exactly one item `in_progress`; never mark
  the final item `completed` until the session is genuinely wrapped up (trailing
  verification item) so the list never collapses mid-session; recreate the list from
  `.mcqueen/CURRENT_TASK.md` at session start (§N updated with the cross-reference).
- **WHY**: The todo panel is the human's only live UI view of agent work; a stale or
  missing list is indistinguishable from the agent not working. Auto-collapse on
  full-completion was silently eating the list before the human could read it.
- **CONSEQUENCES**: Every future session starts with a todo list; the final item stays
  open until verification + state-file updates are done; fully-completed lists appear
  only at genuine session end. This session (2j) is the first application of the rule.
- **STATUS**: ACCEPTED (mandate executed this session)

---

## DECISION 021 — 10-second todo auto-dismiss + fresh-list-per-request (user mandate 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: Two observed failures: (1) the todo list did not disappear after the last
  task completed — the old completed list stayed on the human's screen; (2) when the human
  asked the push-verification question, they still saw the old list and NO new list — the
  agent answered a tool-using question with zero todo list, violating strict §R.
- **EVIDENCE**: (a) opencode TUI bug #30382 — completed todo items linger on screen;
  `clear()` is never called (non-reactive `session_working()` in the SolidJS store); a
  fully-completed list does NOT auto-hide, contradicting §R rule 3's original premise.
  (b) The push question was answered with git-verification tool calls and no todo list
  created first — a real contract violation by the agent (self-reported).
- **OPTIONS**: (1) rely on UI auto-dismiss (proven broken — bug #30382); (2) encode the
  10-second rule as agent behavior: replace a completed list with the next task's list
  immediately, never leave a completed list visible while the conversation continues;
  (3) patch the opencode TUI source (out of scope — external project, not McQueen's).
- **DECISION**: AGENTS.md §R amended (user mandate, strict): rule 3 corrected (completed
  lists do NOT reliably auto-hide — bug #30382; never rely on it); NEW rule 6 = the list
  must be gone from the human's screen within ~10 seconds of the last item completing —
  any follow-up request gets its fresh list FIRST (instant replacement), genuine session
  end closes the list; NEW rule 7 = every new user message starting any task (even quick
  verifications) opens a fresh todo list before the first tool call — the human must
  never see a previous task's items during a new task.
- **WHY**: The todo dock is the human's only live view of agent work; a stale completed
  list is indistinguishable from "agent not working" and hides the new task's list. The
  contract is followed by reading, not enforced by tooling — so the rules must close the
  exact failure modes observed, and the agent must obey at every step.
- **CONSEQUENCES**: This session (2k) demonstrates the amended contract end-to-end.
  Future sessions: completed lists are replaced within ~10 seconds by the next task's
  list, or closed at session end. Stale-list-while-working = contract violation.
- **STATUS**: ACCEPTED (mandate executed this session)

---

## DECISION 022 — 2-week sprint: demo bar, freeze-hardware, care protocol, training compute (user mandate 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: Project deadline is 2 weeks out (lab available all 14 days, ~4–8 h/day). The
  drivetrain is being redesigned (encoder DC motors + quadrature on the drive side,
  gearbox + differential; servo steering UNCHANGED) and 3D-printed gears failed 4–5 times
  — no drivetrain exists today. How do we maximize the chance of landing the final demo?
- **EVIDENCE**: No trained policy exists; Q1 motor-PWM label path still unverified; L1 real
  inference never run; transport proven (p50 ~160–290 ms, control 43 ms); dataset tooling
  home-validated; 8 old demos are NOT real driving data (user verdict). User's goal
  aspiration: comma-ai/openpilot-style autonomy in NEW environments (simcity99-style demo).
- **OPTIONS**: (1) Full openpilot-level generalization as hard requirement (honest verdict:
  mathematically out of reach in 2 weeks from a 20-lap imitation dataset); (2) best-effort
  openpilot with honest floor = track autonomy; (3) track-only demo.
- **DECISION**: (a) DEMO BAR = best-effort openpilot, honest floor = smooth autonomous laps
  on the training track with teleop takeover; stretch = direction flips, layout variations,
  augmentation. No claim of new-environment generalization at the demo. (b) FREEZE-HARDWARE
  RULE (binding): steering stays the existing servo until after the demo — dataset labels
  must match deployment hardware 1:1; encoder-servo idea is post-demo. (c) CARE PROTOCOL
  (binding): sacred list never touched without per-change approval — run_rtp_wan_test.sh,
  deployed Jetson/RTX copies, teleop path (app→protocol→drive.py→GPIO), recorder +
  process_recording.sh, sender/receiver pipeline behavior; new work in NEW files first;
  full test suite after every change; no commits (DECISION 013); no remote access without
  authorization. (d) TRAINING COMPUTE: real policy training runs on the RTX 4090 — user
  states full resources will be available at training time; ViReL untouchable rule STANDS
  until the user personally confirms that job is done. (e) DATASET: ~20 laps by Tuesday
  (drivetrain must pass Q1 kachow_probe on final hardware FIRST); environments decided at
  recording time — agent will ask the user then. (f) PARALLEL SOFTWARE DE-RISK starts now
  (laptop-only): training rehearsal (train→checkpoint→MCQUEEN_PPGEO_CKPT→inference_rtx.py
  --inference real smoke on old demos), Kachow build, transport procedure scripts.
- **WHY**: Dataset quality + hardware freeze + proof of the full train→deploy→infer chain
  before real data exists are the only levers that move the 2-week odds; untested chain
  links on the critical path are how deadlines die.
- **CONSEQUENCES**: Next lab: gearbox/differential/encoder motors → bench → Q1 probe pass →
  record 20 laps (env questions asked at recording time). Agent: state files updated this
  session; rehearsal scripts NEW files; nothing on the working pipeline touched.
- **STATUS**: ACCEPTED (this session; rehearsal + state files in progress)

---

## DECISION 023 — NO training on the laptop; training runs only on the RTX 4090 (user mandate 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: Can the rehearsal training run on the laptop while the user is away?
- **EVIDENCE**: The laptop FREEZES under sustained torch training load — twice observed
  2026-08-15 (tiny-backbone 10-epoch run). First freeze coincided with a ~7 GB full-res
  image cache (agent bug, since fixed to ~380 MB resized cache); the SECOND freeze happened
  on the memory-fixed run → the hardware itself (7.6 GB RAM total, GTX 1650 Max-Q 4 GB)
  is the constraint, not just the cache. User verdict after the second freeze: "do not at
  all freeze my laptop once again… we will do that at lab today on 4090".
- **OPTIONS**:
  1. Run training on the laptop with conservative settings (rejected — froze twice already).
  2. No laptop training at all; trainer runs on the RTX 4090 at lab (chosen).
- **DECISION**: Training (any torch training loop) NEVER runs on the laptop. All training
  happens at the lab on the RTX 4090 (after the user confirms the ViReL job is done —
  DECISION 014 rule still binds until then). At home: CPU-light work only; any run that
  risks sustained CPU/GPU load or large RAM is deferred to the lab.
- **WHY**: Observed hardware freeze, twice, with zero exceptions; user mandate. A frozen
  laptop kills the home session and wastes the user's time.
- **CONSEQUENCES**: The trainer is verified at home only by import/argparse/py_compile;
  its first real execution is the lab 4090 run. Rehearsal chain C was verified CPU-only
  with a synthetic checkpoint. All tests at home run CPU-light.
- **STATUS**: ACCEPTED (user mandate).

---

## DECISION 024 — NO torch execution of ANY kind on the laptop — strengthening of DECISION 023 (user mandate 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: Is a single-batch, forward-only, GPU smoke of the training pipeline acceptable on the laptop (as scoped in DECISION 023)?
- **EVIDENCE**: The laptop FROZE a THIRD time during exactly that smoke (tiny backbone, batch 8, ONE forward, NO backward, RAM guard passed with 5.2 GB available, 180 s alarm). Earlier the same day it froze twice under the training loop. Combined with the CPU-only data-pipeline debugging that ran fine all day, the freeze is triggered by torch/CUDA execution itself (model.to(cuda) + forward), not just training loops. User verdict: "DO NOT EVER EVER DO THIS SHIT AGAIN ON THIS LAPTOP THAT MAKES IT FREEZE".
- **OPTIONS**:
  1. Keep DECISION 023 as-is (no training loops; single forward allowed) — rejected: the smoke froze the machine.
  2. Zero torch execution on the laptop: no imports of torch/lerobot, no model construction, no forward, no CUDA — all of it at the lab (chosen).
- **DECISION**: NO torch execution of ANY kind on the laptop — no training loops, no single-batch forwards, no CUDA init, no lerobot/torch imports in runs. At home, verification is limited to: py_compile, pure-python tests (system python3, no torch), bash -n, static review. Everything torch-related (smoke, training, inference tests) runs at the lab on the RTX 4090.
- **WHY**: Three observed freezes, the last one on the lightest possible torch workload. The laptop is not reliable under any torch execution; each freeze costs the user a reboot and risks losing session state.
- **CONSEQUENCES**: `mcqueen_ml/training/smoke_train_batch.py` is WRITTEN + py_compile-verified but NEVER runs on the laptop — its first run is the lab 4090 pre-flight (first thing before real training). `test_inference_rtx.py`, `test_checkpoint_inference.py`, `test_temporal_policy_v2.py`, `test_backbones_ppgeo_resnet34.py` are NOT re-run at home anymore — their last green run was session 2m; they re-run at lab.
- **STATUS**: ACCEPTED (user mandate, binding).

---

## DECISION 025 — HOME = ONLY laptop + phone (user mandate, binding 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: Which devices are ever present at the user's home?
- **EVIDENCE**: User made this a HARD rule while angry that the agent assumed the Jetson
  had come home: "HOME ALWAYS AND ALWAYS MEAN THAT ONLY THE LAPTOP AND MY PHONE WILL BE
  WITH ME AT HOME". The Jetson was left at the lab (unreachable from home — behind campus
  NAT/firewall, no tunnel). The agent's wrap-up had wrongly listed the Jetson in the
  carry-bag and claimed "everything covered"; the correct home-scope was laptop+phone only.
- **DECISION**: HOME always contains ONLY this laptop and the user's phone — nothing else.
  No Jetson, no RTX, no camera, no power banks, no other hardware. Never assume otherwise;
  at session end verify the carry list is laptop + phone only. Any plan requiring a
  non-laptop device at home is invalid by definition. Remote-machine work at home is only
  possible via established remote-access infrastructure (reverse tunnels — see DECISION 026
  task), never via device presence. Also: never claim remote-machine access works without
  an actual connectivity test (the SSH-from-home claim was made without a test — timeout
  was the real result).
- **WHY**: User mandate; repeated assumption failures erode trust. The Jetson does not
  belong to the home environment; expecting it there breaks the user's workflow and the
  agent's honesty rules.
- **CONSEQUENCES**: Home sessions are laptop+phone only by default; Jetson/RTX debug is a
  lab activity unless reverse-tunnel infrastructure (DECISION 026) provides remote access.
- **STATUS**: ACCEPTED (user mandate, binding).

---

## DECISION 026 — Remote-access infrastructure for Jetson + RTX (approved 2026-08-15)

- **DATE**: 2026-08-15
- **QUESTION**: How can home sessions reach the lab machines (Jetson, RTX) despite the
  campus firewall blocking ALL inbound ports from the home ISP?
- **EVIDENCE** (verified from home, 2026-08-15): RTX public IP `14.139.108.62` is CONSTANT
  (static campus 1:1 NAT — same IP across Aug 14 and 15 runs, 8+ evidence logs). SSH port
  22 and all probed ports (22/80/443/8765/8080) time out from the home network — the campus
  firewall drops inbound from the home ISP; only outbound-punched (STUN) ephemeral UDP
  ports ever worked. The RTX is ALIVE: the trycloudflare quick tunnel
  (`carlo-booth-austin-pics.trycloudflare.com`) resolves via external DNS (8.8.8.8, 1.1.1.1)
  and answers HTTP (404 on plain GET — ws-only endpoint). Home DNS (systemd-resolved
  upstream) REFUSED trycloudflare lookups — a local resolver quirk, NOT a dead tunnel;
  external-DNS checks are the reliable test. Cannot restart/start anything on the RTX from
  home without a shell route (circular — needs the tunnel first).
- **DECISION**: At the NEXT LAB SESSION, set up persistent remote-access infrastructure so
  home sessions can reach BOTH machines regardless of campus inbound filtering:
  1. Jetson: install cloudflared + its own tunnel; evaluate TCP-capable options for SSH
     (cloudflared quick tunnel `--url tcp://localhost:22` + `cloudflared access tcp`
     client, or frp / ngrok-TCP) — compare on evidence, pick one, make it a systemd
     service so it survives reboots.
  2. RTX: same treatment for SSH (its public IP is firewall-blocked on 22).
  3. Document the exact client-side connect recipe in the repo.
  Until then: no remote machine work from home; lab-only for Jetson/RTX operations.
- **WHY**: The user wants home sessions to include real Jetson/RTX debug; the campus
  firewall makes direct inbound impossible; the only reliable path is outbound tunnels.
- **CONSEQUENCES**: Next lab session includes this setup task before other work. Until
  done, home = laptop+phone only (DECISION 025).
- **STATUS**: APPROVED (user 2026-08-15, "yes add that persistent reverse tunnel on jetson
  thing"); IMPLEMENTATION PENDING (lab session required).
