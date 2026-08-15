## 2026-08-15 — Session 2p: progress-report deliverables created for partner's PPT; sanity re-passed; heading to lab for real

**Mode**: HOME → HEADING TO LAB (LAB mode activates on user "im at lab").

- User requested ONE context report file covering the last 2-3 weeks, transport
  ("server thing") as centerpiece, for their partner's update PPT. 4 scoping
  questions answered: foundation + 2-3 weeks, full honest status, full technical
  detail, Downloads + sanitized (no decision IDs, no shared-GPU job, no laptop
  freezes, no credentials, no clock timestamps).
- Created `~/Downloads/mcqueen_project_report.txt` (2,865 words, ~4.5-5 pages):
  exec summary, architecture ASCII diagram, foundation (git history 82 commits +
  context-stuff files), week-by-week Aug 11-15, transport deep dive (WebRTC+broker+
  cloudflared → CGNAT srflx failure → raw H.264-RTP over punched UDP; all measured
  numbers labeled by date+network), dataset/model, KACHOW+safety, honest status,
  next 7 days, key metrics table, glossary.
- Created `~/Downloads/mcqueen_project_report_bullets.txt` (450 words, 1 page):
  copy-paste PPT bullet sheet.
- FACT-CHECKED: every number grep-verified against sources (29.4/43.1/70.4/75.7 RTT,
  287.1/504.0 loop, 57,641 frames, 25.4 fps, 52,095/3,287 assoc, 242,910 pkts,
  677/478/277 ladder, 281.9 vs 276.8 jitter, 160@400kbps, save 0.96/1.32, 52,100,
  90.8%, 709, 46). Leak-scan clean (no DECISION IDs, no ViReL, no PID, no
  HH:MM, no credentials). Files NOT in repo — nothing committed.
- Sanity re-pass: git 24 entries (16 M + 8 ??), HEAD==origin==`30728e1`, reports
  on disk, zero stray processes. No commits made.
- NEXT on arrival ("im at lab"): confirm ViReL PID 575347 done → recreate
  /tmp/mcq_askpass.sh → smoke_train_batch.py on 4090 → train → checkpoint →
  deploy inference_rtx.py → --checkpoint smoke → deploy sender/kachow_probe to
  Jetson clone (61a3c91) → RTT probe → A/B → app build → propose receiver
  --inference real (Q13).

# SESSION_LOG.md — McQueen session log

Append chronologically. Newest at the top.

## 2026-08-15 — Session 2s: Jio 5G full-loop test — VERIFIED NO improvement (worse tail); clean wrap

**Mode**: LAB (leaving). 5G experiment + full cleanup done; state files handoff-grade.

- **5G test setup**: resilient autostart wrapper (new `/home/sravjti/mcqueen_5g/`, append-log +
  stall-kill + retry); Jetson on a 10,000 mAh power bank (swap reboot handled); RTX receiver + 
  laptop stayed in the lab; user walked Jetson+camera+phone outside to a 5G/5G++/5G++ spot
  (~90 s stand; phone mode-shifted to 4G sometimes).
- **En-route bugs FIXED**: (1) Jetson `/tmp` is tmpfs → wiped on reboot → autostart wrapper in
  `/tmp` vanished after the power-swap reboot (cron fired into a missing file) → moved to
  `/home/sravjti/mcqueen_5g/`; (2) `mcqueen-edge.service` holds `/dev/video0` at boot → camera
  busy → stopped edge for the test (restored after); (3) unanchored `pkill -f` inside a cleanup
  ssh killed the cleanup shell (F7-class) → precise PID kills used.
- **Result (VERIFIED)**: sender ran continuously through the whole walk (0 restarts, 0 stall-kills);
  RTX received 49,369 frames, fps 20.6, assoc 95.3%, ctrl_sent 46,094. p50 did NOT improve: best
  ~223-224 ms at the desk on stable 4G; 5G++ spot window ~231-237 ms (≈ stable 4G); cumulative
  end 257.7 ms; **p95 worsened to ~1239 ms** (mode-shifting). **5G++ ≈ 4G for median, worse tail —
  <100 ms NOT reached via 5G on this phone.** RTT ~50 ms either way → the ~230 ms is queueing
  across the path, not the 5G backhaul.
- Evidence: `docs/evidence/2026-08-15/5g/` (sender.log, receiver.log, REPORT.md); ERROR_LOG +
  AUDIT updated (entry F / section 12).
- **Cleanup COMPLETE**: sender + wrapper killed (PID), cron entry removed, `/home/sravjti/mcqueen_5g/`
  deleted, RTX receiver stopped, `mcqueen-edge.service` ACTIVE, cloudflared tunnel left up
  (`carlo-booth-austin-pics.trycloudflare.com`). Laptop git: still `30728e1`, zero commits
  (DECISION 013).
- NEXT: Q13 proposal (receiver `--inference real` w/ tiny ckpt) at next session; PPGeo training
  when the neighbor GPU job (PID 744309) ends; pacing/320×240 remain approved-but-future latency
  levers (5G did not solve <100 ms).

## 2026-08-15 — Session 2r: LAB COMPLETE — training chain, app build, full WAN loop + bitrate A/B all verified; dead-tunnel root cause found

**Mode**: LAB (RTX `192.168.0.132`/junior, Jetson `192.168.55.1`/sravjti, laptop WiFi; askpass helpers `/tmp/mcq_askpass*.sh` transient).

- **Gate**: neighbor job changed (ViReL gone; NEW `train.py` PID 744309, 20.3 GB VRAM, 82% GPU, `~/grpo-gsm8k-output`) — user chose NOT to touch the GPU; CPU path used throughout.
- **Smoke + training (CPU)**: `smoke_train_batch.py` PASS (630 samples/6 episodes, forward (8,2)); `train_temporal_v2.py --backbone tiny --device cpu --epochs 20` → `/home/junior/mcqueen_run/rehearsal_temporal.pt` (36 MB, best_val 3.02; keys verified).
- **Inference chain verified with REAL ckpt on RTX**: `test_checkpoint_inference.py` 10/10, `test_inference_rtx.py` 18/18 (CUDA infer 444.75 ms with GPU busy), `--checkpoint` CPU infer 6.59 ms/frame → servo=89.0 pwm=4.
- **Jetson deploy**: repo sender `gst_jetson_rtp_wan.py` + `kachow_probe.py` + `measure_true_path_rtt.py` → clone `~/McQueen` (61a3c91); sender also `/tmp/`.
- **APP BUILT**: gradle 9.4.1 + JDK 17 → `assembleDebug` SUCCESS in 27 s → `apps/android/KachowV8/.../app-debug.apk`. Install HELD until user says.
- **Port-forward theory RETRACTED**: real mechanism = ephemeral port `0.0.0.0:0` + STUN punch (endpoint-independent campus NAT, NO forward). Full WAN loop was DOWN because **cloudflared dead (Tunnel server stopped) + stale URL** (F8) → fresh tunnel `https://carlo-booth-austin-pics.trycloudflare.com` (PID 759025) → signaling verified → **loop UP**: `CTRL_RX n=960`, **LAT_p50=276.5 ms / p95=486.7 ms** @300 kbps, receiver fps 18.3, assoc 941/1019 (~94%), infer 0.12 ms; public endpoints receiver `14.139.108.62:49995`→`:41820`→`:53591`, Jetson `152.59.109.96:59856`. Direct peer-to-peer UDP confirmed (SENT pkts=... peer=14.139.108.62:53591, achieved=422kbps).
- **Bitrate A/B 150/300/400×2**: 3 script launch failures diagnosed (ssh -t → pkill self-match F7 → bracket-pattern STILL self-match because cmdline contains the literal script name) → **PID-file kill/check** solved it. 5/6 data runs + manual 400 rerun (6th hit transient websocket 530): all runs ctrl_rx yes; 150_1 loss 2.9%, assoc 4.3%; p50 stable 270-280 ms; fps 18-22. `run_bitrate_ab.sh` full_loop grep fixed post-run (`CTRL_RX n=` not `FULL_LOOP_LATENCY n=`). Evidence: `docs/evidence/2026-08-15/ab/` + `REPORT.md`.
- **Docs corrected (honest records)**: `docs/ERROR_LOG_2026-08-15.md` + `docs/AUDIT_2026-08-15.md` REWRITTEN — wrong port-forward blocker → true root cause (dead tunnel/stale URL, F8) marked FIXED + A/B script failure chain (entries D) + p95 tail note (E).
- **Cleanup**: A/B + manual 400 processes stopped (PID files); **mcqueen-edge.service RESTORED (active)** on Jetson (sudo -S); cloudflared tunnel left up (next-session broker).
- **User Q answered**: "direct UDP?" → YES — media/control are direct punched UDP; cloudflared remains ONLY for startup signaling (brokerless removal = future item, not done — stated honestly).
- NEXT: Q13 proposal (receiver `--inference real` w/ tiny ckpt) + PPGeo training when GPU frees; checkpoint copy-back to laptop `data/checkpoints/` if wanted; state files updated (this session). No commits (DECISION 013).

## 2026-08-15 — Session 2o: home phase COMPLETE — leaving for lab; full 2n verification re-passed (user "update the state files everything should be pristine")

**Mode**: HOME → LEAVING (LAB mode activates on user "im at lab").

- **Full re-verification of session 2n claims (evidence-checked, all passed)**: git tree 24
  entries (16 modified + 8 untracked), HEAD == origin == `30728e1`; 2n content confirmed in
  all 6 state files; DECISION 023/024 blocks complete; Q13/Q14 present; py_compile all 5
  python files OK; `bash -n` A/B OK; gradle SHA-256 matches official; wrapper jar + 
  local.properties (gitignored) present; no stray processes; pure-python suite green.
- **Clarification recorded**: no USB needed — gradle zip lives on the laptop (app builds
  locally); all transfers via SSH (laptop→RTX scp over lab LAN; laptop↔Jetson USB scp on
  `192.168.55.1`); Jetson stays USB-tethered to the laptop.
- **Physical carry**: laptop (datasets `data/lerobot/rehearsal/` 305 MB, PPGeo ckpt 87 MB,
  spools 57 MB, gradle-9.4.1-bin.zip). Recreate `/tmp/mcq_askpass.sh` at lab.
- **Lab entry order (locked)**: ViReL confirm (PID 575347) → askpass → `smoke_train_batch.py`
  on 4090 → train → checkpoint → deploy new `inference_rtx.py` + `--checkpoint` smoke →
  deploy repo sender + `kachow_probe.py` to Jetson clone (`61a3c91`) → RTT probe
  (`14.139.108.62`, port-forward 5955) → bitrate A/B (fixed loss) → app build → propose
  receiver `--inference real` (Q13, separate approval).
- **No commits** (DECISION 013). Nothing changed in this session beyond state files.

---

## 2026-08-15 — Session 2n: laptop froze a THIRD time (single-batch GPU smoke) → DECISION 024: zero torch on laptop; A/B loss fix, gradle prep, lab-only smoke (user "NIGGEE THE LAPTOP FREZED AGAIN… DO NOT EVER EVER DO THIS SHIT AGAIN")

**Mode**: HOME.

- **Third freeze**: the approved single-batch forward-only GPU smoke (`smoke_train_batch.py`,
  tiny backbone, batch 8, no backward, RAM guard 5.2 GB available, 180 s alarm) FROZE the
  laptop anyway → evidence: torch/CUDA execution itself is the trigger, not training loops.
  **DECISION 024 (binding)**: zero torch execution of any kind on the laptop — no imports,
  no forwards, no CUDA. Everything torch-related runs at the lab (smoke = first 4090
  pre-flight). The smoke script is written + py_compile-verified, lab-only.
- **A/B script fixed**: `run_bitrate_ab.sh` loss now = 100×(1 − `frames_rx`/`meta=`) (was
  computing against `SENT pkts` — packets, not frames) + new `assoc_ok/assoc_miss` loss
  column; summary header updated; `bash -n` OK. This would have produced garbage loss
  numbers at the lab.
- **Gradle prep done**: `gradle-9.4.1-bin.zip` (~135 MB) downloaded to `~/Downloads/`
  (restarted after freeze; SHA-256 `2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb`
  verified); missing `gradle-wrapper.jar` (48,966 B) fetched into
  `apps/android/KachowV8/gradle/wrapper/`; `local.properties` created (sdk.dir, gitignored).
  App build now only needs the gradle dist carried to lab.
- **Decisions recorded (user-confirmed)**: (a) dataset recorded at **10 fps** — recorder
  is offline teleop, ZERO latency impact on the live 30 fps loop; temporal-rate mismatch
  (10 fps training vs 30 fps inference) logged as Q14 with future subsampling option;
  (b) **encoders: zero work** — wheels channel stays zeros (NullEncoderSource) at record
  AND inference (consistent train/infer); real quadrature reading only if time allows
  post-Q1 (needs new code + bench, authorized).
- **Torch tests NOT re-run at home** (DECISION 024): last green = session 2m
  (18/18 + 11/11 + temporal-policy 3/3 + PPGeo 5/5). Pure-python suite re-run: protocol/
  drive/realtime-contract all OK (system python3, no torch).
- **No commits** (DECISION 013). HEAD == origin == `30728e1`; tree = prior work +
  smoke_train_batch.py (untracked, lab-only) + local.properties (gitignored) + wrapper jar.
- **At lab (in order)**: confirm ViReL done → `smoke_train_batch.py` on 4090 (pre-flight) →
  train → checkpoint → deploy new inference_rtx.py + `--checkpoint` smoke → RTT probe →
  A/B (fixed loss) → app build (gradle from USB) → propose receiver integration (Q13).

---

## 2026-08-15 — Session 2m: laptop-freeze lesson → DECISION 023; training rehearsal completed at home (A/B/C), app build prep, transport scripts (user "gng continue im really sorry my laptop had freezed midway…", pre-leave approvals granted)

**Mode**: HOME (user left; full-todo autonomy pre-approved before leaving).

- **Laptop froze TWICE during rehearsal training** (tiny-backbone 10-epoch runs). Cause 1
  (agent bug, fixed): image cache stored FULL-RES 720×1280 float32 tensors ≈ 7 GB on a
  7.6 GB-RAM machine. Cause 2: memory-fixed run STILL froze → hardware is the limit.
  User mandate recorded as **DECISION 023: no training on the laptop ever; training runs
  at lab on the RTX 4090.**
- **Rehearsal Chain A (done)**: 5 usable old sessions (630 frames / 6 episodes) converted
  to LeRobot datasets `data/lerobot/rehearsal/<session>/` (repo-id `mq-rehearsal-<session>`);
  read-back verified. 2 sessions empty; `session_20260810_133136` FAILED validation
  (110 frames @ 5.00 Hz < 9–11 Hz contract) — excluded honestly.
- **Chain B (trainer written, NOT run)**: NEW `mcqueen_ml/training/train_temporal_v2.py` —
  dataset discovery, episode-level train/val split, MSE on normalized actions, PPGeoResNet34
  (MCQUEEN_PPGEO_CKPT) or `--backbone tiny`, checkpoint dict (model_state_dict/config/stats/
  history/image_size/losses), image cache resized to 224×224 (~380 MB, memory-safe). Verified
  at home: import + argparse + py_compile only (DECISION 023). First run = lab 4090.
- **Chain C (done)**: minimal edit to `tools/realtime/inference_rtx.py` — `--checkpoint`
  load (backbone from ckpt, history/image_size from ckpt, stats denorm before safety clamp);
  default random-tiny path byte-identical behavior. NEW `tools/realtime/test_checkpoint_inference.py`
  (synthetic checkpoint) 11/11 PASS; existing `test_inference_rtx.py` 18/18 PASS (proves the
  tested/working path unchanged — user's hard rule).
- **Full suite green**: tests/test_jetson_protocol.py OK, tests/test_jetson_drive.py PASS,
  tests/test_realtime_contract.py OK (5), mcqueen_ml/training/test_temporal_policy_v2.py OK (3),
  test_backbones_ppgeo_resnet34.py OK (5, real PPGeo ckpt).
- **Kachow app build**: laptop HAS Android SDK (android-36, build-tools 36.0.0, JDK 17, adb,
  sdkmanager) but NO gradle distribution / gradle-wrapper.jar / local.properties → build
  deferred to lab (fetch gradle-9.4.1-bin.zip + write local.properties sdk.dir first).
- **Transport scripts (NEW files)**: `measure_true_path_rtt.py` (true-path UDP RTT probe;
  loopback smoke 30/30, loss 0% — mechanics verified, loopback latencies meaningless for
  WAN) + `run_bitrate_ab.sh` (150/300/400 kbps ×2, mirrors run_rtp_wan_test.sh pattern,
  deploys repo copies, per-run sender+receiver logs → docs/evidence/<date>/ab/; bash -n OK).
  Lab-run only, requires authorization.
- **No commits** (DECISION 013). HEAD == origin == `30728e1`; tree = prior modifications +
  new files (trainer, 2 transport scripts, test_checkpoint_inference.py) all untracked/modified.
- **Approvals pre-granted (before user left)**: inference_rtx.py minimal edit (hard rule:
  never break tested/working — proven), long training runs approved (superseded by DECISION 023),
  full-todo autonomy.

---

## 2026-08-15 — Session 2l: 2-week sprint planning — demo bar set, care protocol, training rehearsal kickoff (user "see have got just 2 weeks left…", answers given, "go")

**Mode**: HOME. User: project deadline = 2 weeks; drivetrain being redesigned (encoder DC
motors + quadrature drive-side, gearbox + differential; steering servo unchanged);
3D-printed gears failed 4–5 times; no drivetrain today; dataset ~20 laps targeted by
Tuesday.

- **Honest assessment given**: a Tuesday dataset is necessary but NOT sufficient (~35% of
  remaining work). Full openpilot-level new-environment generalization is out of reach in
  2 weeks from 20 laps — committed to best-effort openpilot, honest floor = track
  autonomy.
- **DECISION 022 (recorded)**: demo bar (floor = track autonomy, stretch = generalization),
  FREEZE-HARDWARE rule (steering locked until post-demo), CARE PROTOCOL (sacred list,
  new-files-first, full tests after every change, no commits, no unauthorized remote),
  training compute = RTX at training time (user confirms ViReL done first), dataset env
  questions deferred to recording day, parallel software de-risk GO.
- **Answers locked**: lab all 14 days 4–8 h/day; motor type = DC+quadrature (user to
  confirm later); dataset environments decided at recording time.
- **Software de-risk plan (this session starts)**: (1) state files (this entry +
  DECISION 022); (2) training rehearsal — convert old demos → train temporal policy →
  checkpoint → MCQUEEN_PPGEO_CKPT → inference_rtx.py --inference real smoke (NEW scripts
  only); (3) Kachow app build prep; (4) transport procedure scripts (new files: true-path
  RTT, bitrate A/B).
- **No commits** (DECISION 013). Nothing on the working pipeline touched.

---

---

## 2026-08-15 — Session 2k: 10-second todo auto-dismiss + fresh-list-per-request rules (user "also another hard rule… the todo list should disappear after 10 seconds… how tf were you able to override and create no todo")

**Mode**: HOME. User reported: (a) the old completed todo list lingered on screen instead
of disappearing after the last task; (b) during the push-verification question they saw
the old list and NO new list — a real §R violation (question answered with git-verification
tool calls and zero todo list).

- **Root cause (evidence-based)**: opencode TUI bug #30382 — completed todo items linger;
  `clear()` is never called (non-reactive `session_working()` in the SolidJS store); a
  fully-completed list does NOT auto-hide. §R rule 3's original premise ("auto-collapses")
  was factually wrong and is corrected. The push-question violation was the agent's own
  failure — no technical enforcement exists; AGENTS.md is followed by reading only.
- **DECISION 021 (user mandate, strict):** §R amended — rule 3 corrected (never rely on
  auto-hide; bug #30382); NEW rule 6 = list must be gone within ~10 s of the last item
  completing (follow-up request → fresh list FIRST, instant replacement; genuine session
  end → list closes); NEW rule 7 = every new user message starting any task, even quick
  verifications, opens a fresh todo list before the first tool call. This session is the
  amended contract's first end-to-end application.
- **Files changed**: AGENTS.md (§R rules 3/6/7), .mcqueen/DECISIONS.md (+DECISION 021),
  .mcqueen/SESSION_LOG.md (this entry), AGENT_STATE.md + CURRENT_TASK.md headers bumped.
- **No commits** (DECISION 013 — rides next hardware-verified commit).

---

## 2026-08-15 — Session 2j: strict todo-list discipline mandate (user "i wanna add a hard rule for the agent… why the todo just disappear so quickly")

**Mode**: HOME. User observed the todo panel going stale (status not matching the actual
task), completed items not marked done, and the list vanishing "so quickly".

- **Cause explained**: a fully-completed todo list auto-collapses in the TUI (that is why
  it vanished at session ends); the list is also session-scoped UI state, so fresh
  sessions start empty; past updates were batched at the end instead of real-time.
- **DECISION 020 (user mandate, strict — no exceptions, no chat carve-out):** new binding
  AGENTS.md section R "TODO LIST DISCIPLINE": every session opens a detailed todo list
  first; exactly one `in_progress` at a time, marked `completed` the moment it is done;
  never mark the final item completed until the session is genuinely wrapped up (trailing
  verification/state-file item — a fully-completed list disappearing mid-session is a
  contract violation); recreate the list from `.mcqueen/CURRENT_TASK.md` at session start;
  §N SESSION START gained the cross-reference step. Recorded in DECISIONS.md as DECISION
  020. This session is the rule's first application.
- **Files changed**: AGENTS.md (§R added after §Q, §N step 9→10), .mcqueen/DECISIONS.md
  (+DECISION 020), .mcqueen/SESSION_LOG.md (this entry).
- **No commits** (DECISION 013 — rides next hardware-verified commit).

---

## 2026-08-14 — Session 2i: DECISION 019 locked — brokerless re-punch trick, bitrate A/B, one-tap RESUME gate implemented (home planning, user "go")

**Mode**: HOME. User asked for in-depth transport explainer, then locked the broker/future
decisions; approved implementation of the RESUME gate at home.

- **Correction delivered**: broker/cloudflared are signaling-ONLY (media = DIRECT_UDP punched
  P2P, 242,910 pkts proven) — removing them changes robustness, NOT latency. The "46 ms RTT"
  yesterday was Jetson→1.1.1.1 (Cloudflare DNS), NOT the Jetson↔RTX path (`mcq_rtt_30.log`
  shows PING 1.1.1.1) — TRUE path RTT remains unknown → tomorrow's first test.
- **DECISION 019 (user mandates, appended to DECISIONS.md):** (1) brokerless lab AND road;
  fallback = **re-punch trick** — NAT mappings are destination-independent: the RTX's hole
  stays alive via keepalives (even to a dead address), so on road hole-death the Jetson
  re-STUNs and sends NEWCAND to the RTX's known endpoint through the still-open mapping.
  No broker rewrite, no aiohttp, no cloudflared. (2) Both-holes-dead = FUTURE TASK (fix
  when faced). (3) **One-tap RESUME re-engage** (Kachow button → `R` packet → gate
  `resume_required` cleared → neutral-before-motion applies; watchdog stops need it, manual
  E-stop doesn't). (4) **Bitrate NOT final** — 150 was a network-specific choice on the old
  link, never A/B-proven; 400 kbps on the new network hit p50 ~160 ms vs 224–287 at 150;
  the 400-run loss was NEVER LOGGED (gap, recorded in VERIFIED_FACTS); lab runs a proper
  bitrate A/B (150/300/400 ×2 cycles, per-run loss + frames_rx + p50/p95 logged).
- **RESUME gate IMPLEMENTED + laptop-tested (this session, approved):** `protocol.py`
  `PACKET_RESUME="R"` (5-field, old app unaffected); `drive.py` `resume_required` flag —
  set on failsafe timeout (watchdog/automatic stop) + `session_armed=False`; C rejected
  with "resume-required" while set; R clears it; snapshot() exposes it (HTTP /status).
  Tests extended (protocol parse + drive flow: watchdog → resume-required → C rejected →
  R → neutral re-arms; E-stop does NOT set resume_required). Kachow RESUME button: code-only
  (build/verify at lab). All uncommitted — rides the next hardware-verified commit.
- **FINALIZED LAB ORDER (next lab):** (1) deploy repo sender + kachow_probe to Jetson
  (drift fix — clone at `61a3c91`) + askpass helper; (2) TRUE PATH RTT (→ `14.139.108.62`,
  NOT 1.1.1.1); (3) bitrate A/B; (4) 320×240+pacing only if justified; (5) re-punch trick
  validation; (6) kachow_probe live (Q1); (7) real dataset; (8) hardware-verified commit
  (broker.py removal rides it only if (5) passed).
- **No commits/pushes** (DECISION 013); state files updated to handoff grade.

## 2026-08-14 — Session 2h: second purge — robot/uno_q removed + pushed (user "why tf am i able to see uno q in robot… did you not properly clean github")

**Mode**: HOME. User spotted `robot/uno_q/` still on GitHub — my first purge only covered
`legacy/` + `oakdmount.stl`, missing the separate `robot/uno_q/` pre-Jetson project.

- **Confirmed dead:** `robot/uno_q/` (STM32 firmware `UnoQDrive.ino`, OAK-D + YOLOv6
  phone-control app.py, mcqueen-mcu/mcqueen services, uv setup) — the pre-Jetson Uno Q
  generation, ZERO current references (grep of README/docs/tools/hardware/robot clean).
  `robot/jetson_nano/` is CURRENT (referenced by `tools/realtime/kachow_probe.py` +
  `tools/preflight/`) — KEPT.
- **Android stale backup** `MainActivity.kt.before_direct_unoq_20260803_183406` was
  UNTRACKED (never on GitHub) — nothing to purge; left on disk.
- **Commit `30728e1`** "Purge dead old-hardware Uno Q project (robot/uno_q)" — 9 files,
  −1,624 lines. **PUSH VERIFIED**: `8f35564..30728e1`, sync 0/0. Cumulative old-hardware
  purge = 61 files (`8f35564` 52 + `30728e1` 9).
- No restructure tag (still deferred to explicit trigger). State-file edits from this
  session remain UNCOMMITTED (ride next hardware-verified commit, DECISION 013).

## 2026-08-14 — Session 2g: GitHub organize DONE — first hardware-verified commit pushed (user "okay do the github organize shit then… delete and remove all this shit… then only start pushing")

**Mode**: HOME. User order: organize GitHub (commit + push pending verified work) BUT NOT the
full restructure (that runs ONLY on trigger "do github restructure rn"); FIRST delete the
scheduled junk, THEN push.

- **Reconcile**: `git reset --soft origin/jetson-nano` absorbed `57561db` keeping the LOCAL
  AUDIT version (fixes "Jetson Sends" typo); worktree untouched.
- **Junk deleted (branch-only, 52 files, history is the backup):** `legacy/esp32/`,
  `legacy/uno_q_previous/`, `legacy/laptop_logger/`, `legacy/dataset_logging/`,
  `legacy/oakd/`, `hardware/cad/oakdmount.stl`.
- **Security fix:** passwords were present in 3 state files (AGENT_STATE, HANDOFF, SESSION_LOG)
  — STRIPPED before commit (AGENTS.md §H binding: never in repo files; they live only in
  `/tmp/mcq_askpass.sh`).
- **Evidence logs force-added** (`git add -f`): `*.log` is gitignored (`.gitignore:45`) but
  `docs/evidence/*/` logs are a tracked convention (41 files from 08-13) — all 14 evidence
  files committed.
- **Commit `8f35564`** "First hardware-verified commit…" — 91 files, +107,876/−5,436: all
  H1–H5 prep, lab fixes, evidence/REPORT, AUDIT/ERROR_LOG 08-14, state files, purge.
- **PUSH VERIFIED**: `57561db..8f35564` origin/jetson-nano; `git status` clean except the two
  intended exclusions (`sync_calib.py` untested + "context stuff" folder — NEVER committed).
- **No tag created** (deferred per user — only on "do github restructure rn": tag
  `pre-purge-2026-08-14` at `57561db` + further §J simplification).
- State-file updates from this session are UNCOMMITTED — they ride the next hardware-verified
  commit (DECISION 013).

## 2026-08-14 — Session 2f: evidence filed to laptop, machines verified clean (user heading home, "get everything we could need at home")

**Mode**: LAB (user at lab, authorized SSH for read-only sweep + pulls). User: pull EVERYTHING
potentially needed at home (GitHub update + debugging).

- **Machine sweep (read-only, 21:38–21:50):** Jetson CLEAN — no sender/probe procs
  (only intentional `mcqueen_discovery.py`), no bundles/pids/pycache/old logs; `/tmp` holds
  punch tools (natprobe/punch_peer/rtp_loopback_test — kept by design) + today's logs.
  RTX CLEAN of junk — ~/logs empty, keep-list intact, no McQueen procs. **ViReL train.py is
  BACK: PID 575347 (started 20:17, 90% GPU / 20.4 GiB VRAM)** — untouchable (DECISION 014).
  ~/Downloads + home = junior's own stuff, untouched.
- **Evidence filed** → `docs/evidence/2026-08-14/wan-loop-measured/` (14 files + REPORT.md):
  Jetson sender logs ×2 + 5× mcq_rtt probes, RTX receiver/broker/cloudflared logs + url,
  2× meta.csv (jitter25 + save_test frame timestamps). REPORT numbers (from logs):
  FULL_LOOP_LATENCY n≈48.6k **p50 287.1 / p95 504.0 ms** (30 fps @ 150 kbps, 25 ms jitter,
  Jetson clock); **CONTROL_RETURN proven at scale — CTRL_RX n=48,650** (was inconclusive);
  EXACT_FRAME_MATCH 52,095 ok / 3,287 miss (~94 %); RTX_INFERENCE ~0.08 ms; VIDEO_FRAMES
  57.6k @ 25.4 fps; save path p50 0.96 / p95 1.32 ms, 52,100 saved, 0 dropped.
- **Deployed-vs-repo md5:** sender/receiver/inference_rtx/broker byte-IDENTICAL to laptop
  repo copies. **Jetson clone `tools/realtime/kachow_probe.py` is STALE (Aug 13 copy) —
  deploy repo version before the live Q1 probe.**
- **Recordings:** raw JPEGs NOT pulled (gitignored, numbers already extracted; 709 MB
  partial pull deleted); RTX keeps recordings on disk. Only meta.csv files pulled.
- **State file corrections applied** (AGENT_STATE, OPEN_QUESTIONS Q10, ERROR_LOG): ViReL
  train.py returned (PID 575347) — "GPU free" claims were stale; Plan A proven GPU-independent.
- No deletions on machines, no .mcqueen conflicts (other AI's last write 21:41, then quiet),
  no commit (DECISION 013). User left for home.

---

## 2026-08-14 — LAB session 2e: wrap-up — everything stopped, tasks deferred to tomorrow

**Mode**: LAB (user heading home, ~10 min). Decisions locked:
- **Broker removal + <100 ms diagnostics: BOTH DEFERRED TO TOMORROW.** User: "we will do
  both of those tasks tomorrow".
- **At-home rule (BINDING, user mandate):** even at home, ANY code/script changes (incl.
  fixing F7/F8/F9 in run_rtp_wan_test.sh) MUST be proposed to the user and wait for their
  explicit approval. Nothing gets changed at home without asking first.
- **GitHub:** NO push today. Error log + state files ride with tomorrow's hardware-verified
  commit (DECISION 013).
- **Procs stopped (precise PID kills, no pkill):** Jetson sender (20156/20155) killed +
  verified no sender proc; RTX receiver (581633) + broker (180532) + cloudflared (180818)
  all killed + verified RTX_ALL_STOPPED. Recordings stay on disk
  (recordings/save_test_201750/ + jitter25_204850/).
- **Tomorrow (verify-first)**: broker removal (code needs user approval at home first, then
  live verify) + diagnostics (control-only RTT probe via punch_peer.py, 320×240 run) +
  evidence filing + kachow_probe (Q1) + first hardware-verified commit (incl.
  docs/ERROR_LOG_2026-08-14.md; reconcile origin `57561db`).
- Honest confidence note delivered: pipeline itself proven (hours, ~0% loss, all errors
  root-caused in ERROR_LOG); the ONLY known repeat-risk is F7/F8/F9 still in the run
  script (per earlier order) — fix needs approval; documented manual-start fallback exists.

---

## 2026-08-14 — LAB session 2d: cleanup round 2 (full sweep) + error log + broker/estimates

**Mode**: LAB. User: "why are there still so many files on the jetson", asked for the final
setup verdict, <100 ms suggestions, broker status, and an error log file.

**Cleanup round 2 — FULL SWEEP (user-approved, option 1: junk AND old logs):**
- Jetson ~: removed 6 git bundles + tar (~50 MB), McQueen_files/, 12 old logs (Aug 11–13),
  4 stale .pid files, old kachow_probe.py (pre-repo), __pycache__, tailscale tgz + sha256 +
  websocket whl install artifacts. Home now = Desktop, examples.desktop, McQueen (clone),
  safety_contract_250ms.py only.
- Jetson /tmp: removed sync_calib.py + __pycache__. KEPT the manual-punch tools
  natprobe.py / punch_peer.py / rtp_loopback_test.py (McQueen's own, from the kilobit
  tests — punch_peer.py is the SSH-orchestrator hole-punch tool, directly relevant to
  broker removal) + mcq_rtt_*.log (today's RTT-probe evidence) + working sender + logs.
- RTX /var/tmp/mcqueen-junior: removed 15 old lab logs (lab2–16) + Aug 11–12 WAN logs
  (finish_udp_rtx, finish_video_rtx, full_loop_bench_rtx, gst_rtx_lowlat, gst_rtx_receiver*,
  leave_lab_rtx, rtx_peer, udp_latency_rtx, gst_rtx_probe, broker.log, cloudflared.log) +
  sync_calib.py. Removed ~/gst_rtx_receiver_wan.pid, ~/mcqueen scratch, ~/logs policy_server
  logs (all McQueen junk, all mirrored in docs/evidence where applicable).
- Post-sweep verification: sender (Jetson PID 20156) + receiver (RTX PID 581633, 25 ms
  jitter, saving) + broker + cloudflared ALL alive; broker health {"ok": true}; keep-list
  intact (venv, clone, lerobot, mcqueen_ml, inference_rtx.py, cloudflared, recordings).
  Broker session shows only "rtx" — the jetson ws died again (Q11), sender still flowing
  on its current mapping; no action needed for this session's wrap-up.

**Error log created**: `docs/ERROR_LOG_2026-08-14.md` — F1/F2/F7/F8/F9/F10/F11/F12,
`drop-on-late` crash, cd-mistake restart, Q11 ws death, NAT re-point failure, NVDEC
starvation, 10-fps + jitter-buffer findings, cleanup-gap note. User-approved for the next
GitHub push.

**Answers delivered**: verdict = 30 fps @ 150 kbps, 50 ms buffer, CPU path (loop p50 ~280 ms,
wire-dominated); <100 ms plan = control-only RTT probe + 320×240 + pacing, honest caveat that
the hotspot link may be the hard floor; broker = signaling-only (NOT in data path), manual
peer exchange viable and kills Q11 failure class.

**Estimates given (awaiting go/no-go)**: broker removal ~1.5–2.5 h full (code ~1 h home +
live verify ~30–45 min lab; debugging buffer included); <100 ms diagnostics ~30–45 min.
User asked for estimates BEFORE starting. Error log + state files updated; nothing committed.

---

## 2026-08-14 — LAB session 2c: approved 4-part plan COMPLETE (cleanup, save test, fps ladder+RTT, 25 ms jitter)

**Mode**: LAB. User approved the 4-part plan (cleanup → save-latency test → fps ladder +
RTT probe → 25 ms jitter buffer) and said implement in order. All 4 done, hardware-verified.

**1. Cleanup (RTX + Jetson) — DONE, keep-list intact**
- Removed only old setup files/tools/stale pids: old WAN scripts (direct_control_peer*,
  rtx_peer*, udp_latency_*, gst_rtx_lowlat*, gst_rtx_receiver* old copies, rtx_full_loop_bench.py,
  jetson old senders + pids), dead webrtc-venv/, __pycache__, stale broker/cloudflared .pid.
  Old LOGS kept per user. Post-removal check: receiver/broker/cloudflared/sender all alive;
  ~/McQueen clone + edge service + data + HF cache + current tools present → KEEPLIST_INTACT.

**2. Save-latency test — DONE**
- Receiver gained opt-in `--save-frames <dir>` (default OFF = current behavior unchanged):
  JPEG every decoded frame + meta.csv (frame_id, capture_mono_ns, recv_mono_ns, save_mono_ns)
  via async writer thread (bounded queue — disk never blocks control path). venv has cv2 4.11.
- Run (30fps@150, ~3 min): recv→decode→save **p50 1.14 ms / p95 1.54 ms**; 5,277 saved vs
  5,270 assoc_ok ≈ 100%, 0 dropped; completeness vs received 90.8% (lost-META frames not
  saved by design); 161 MB in recordings/save_test_201750/.
- Note: sender's tunnel ws died mid-test (Q11) → sender restarted fresh (known workaround).

**3. FPS ladder + RTT probe — DONE, mystery SOLVED**
- Back-to-back on the same network @150 kbps, Jetson pings 1.1.1.1 every second per run:
  10 fps → loop **677 ms** (link RTT p50 46 / p95 73 ms — HEALTHY); 15 fps → **478 ms**
  (two 15-fps-equivalent runs agreed 478/467 → reproducible); 30 fps → **277 ms**.
- Verdict: NOT link variance — SPARSE TRAFFIC itself (jitter-buffer clock recovery + path/NAT
  scheduling with one burst per 100 ms). True 20 fps impossible (30/N rates: 30/15/10).
  **Winner: 30 fps.**
- Sender `--max-fps` reworked to time-gate that ONLY applies when throttling; regression
  caught+fixed: the gate had skipped jittery camera frames at default 30 (sent ~20 fps) —
  default 30 now pushes every camera frame (original path), verified 31.3 fps sent.

**4. 25 ms jitter buffer @ 30fps — DONE**
- Receiver gained `--jitter-ms` (default 50 = unchanged). Run: loop **p50 281.9 ms /
  p95 425.4 ms** — statistically identical to 50 ms (276.8/393) → jitter buffer was never
  the latency driver; ~280 ms is wire/RTT. SAVED n=21,400, 0 dropped, recv2save p50 0.93 ms.
- Finding: sender re-pointing to a new receiver port WITHOUT a fresh restart does NOT
  re-establish the NAT path (CGNAT/campus mapping per-session) — receiver got 0 RTP until
  the sender was restarted fresh (new public 152.58.29.56:48655). In-place re-point = dead.

**Dropped (per user)**: absolute capture→save latency (needs Jetson↔RTX clock offset).
sync_calib.py (NTP-style 4-timestamp offset over direct UDP, no broker) written + deployed
but not run to completion — kept untracked in tools/realtime/. RTX-side recv→decode→save IS
measured (~1 ms).

**State**: sender (30fps@150) + receiver (25 ms jitter, saving to recordings/jitter25_204850)
+ broker + cloudflared still RUNNING. GPU free. Nothing committed (DECISION 013). State
files updated to handoff grade.

**Next (user green-light)**: evidence filing, kachow_probe (Q1), recording, FIRST
hardware-verified commit (reconcile origin `57561db`), L1 real inference (approval only).

---

## 2026-08-14 — LAB session 2b: better network + measurement runs (10 fps vs 30 fps; kbit/loss/receipt metrics)

**Mode**: LAB. User switched the phone to a better network and asked for the measurement
rerun: kbit sent, frame/control efficiency+loss, 10 fps (not 30), receipt proof, recommendations.

**Network change verified**: Jetson public 152.58.29.86 → 152.58.29.56 (new CGNAT). Same
pipeline, 30 fps @ 400: **p50 391 → ~160 ms, p95 1.67 s → ~380 ms** — bottleneck was the link.

**Code change (only one, least-disruptive per user)**: sender `--max-fps` flag; default 30 =
byte-identical original path (frame_step 1 / rtp_ts_step 3000 / frame_ns 33.3 ms); 10 = every
3rd captured frame (step 3 / 9000 / 100 ms), skipped frames get NO capture_q entry or frame_id
(META stays 1:1 with sent frames). Verified: py_compile, packetization 5/5, pytest 18,
10 fps pacing live (rtp_ts 14,724,000 = 1636×9000). No receiver changes.

**Run 1 — 10 fps @ 150 kbps (2.5 min):** p50 462 ms / p95 679 ms. Frames ≈1,645 sent vs
≈1,590 received (~96–97%; window overlapped prior stream tail — approximate). META loss ~1%.
Controls 98.5%. EXACT_FRAME_MATCH 98.9%. achieved ~56–75 kbps.

**Run 2 — 30 fps @ 150 kbps (2.5 min, drained baselines):** p50 224 ms / p95 368 ms.
Frames 5,020 → 4,995 (**99.5%**), packets 21,260 → 21,000 (1.2%), META 5,019 → 4,987 (0.6%),
controls 4,593 → 4,600 (~0%), EXACT_FRAME_MATCH 95.0%, CPU infer 0.04–0.14 ms, achieved
169 kbps (incl. ~12% RTP header overhead).

**FPS ANOMALY (unconfirmed)**: 10 fps latency WORSE than 30 fps at same bitrate — bandwidth no
longer the constraint; likely jitter-buffer clock recovery with sparse traffic or link variance.
Needs a repeated pair. Recommendations delivered: repeat pair, 25 ms jitter buffer (loss ~0 →
margin), control-only RTT probe, per-leg timestamps, sender ws reconnect (Q11), 10-min
stability run.

**State**: GPU free; receiver PID 554982 + sender (30 fps @ 150) still running; nothing
committed (DECISION 013); state files updated.

---

## 2026-08-14 — LAB session 2: fixes implemented on reset baseline → FULL LOOP FLAWLESS, latency measured (user "fix the server thing… gimme final loop latency number")

**Mode**: LAB. User ordered: reset the loop-test files to GitHub state, apply ONLY the listed
fixes (no Plan-A package), then run the loop latency test. Answer to Q2 (manual start) pre-\
approved; broker KEPT ("keep broker (recommended)"); CPU decode approved ("yes, force CPU decode").

**Reset + fixes (git checkout HEAD -- sender/receiver/run-script; then applied ONLY):**
- Fix 1: receiver always pushes RTP into appsrc — never gates on `cur_meta`; lost META →
  assoc_miss. Fix 2: rtpjitterbuffer latency=50 drop-on-latency=true (50 ms budget, no rtx).
  Fix 3: sender --bitrate-kbps + achieved-kbps print. CPU path: avdec_h264 + CPU dummy infer.
  Rolling FULL_LOOP_LATENCY (LAT_p50/LAT_p95) every 10 controls. Run script UNTOUCHED.
- test_rtp_packetization.py adapted to the committed sender API (run via _on_rtp_probe with
  real Gst.Buffer; non-VCL-hold test dropped — that behavior was reset away): 5/5 PASS +
  association PASS + pytest 18 passed + py_compile/bash -n clean.

**Committed-script run (as ordered — bug-watch):** F7 CONFIRMED (pkill -f self-kills remote
shell in steps 6+7 → peers never start; step-8 "evidence" was STALE morning logs — identified,
not misreported). F9 CONFIRMED (sudo fails without tty / hangs with tty). F8 NOT hit (URL file
refreshed this morning). Bugs noted, NOT fixed (user order).

**Manual start (user pre-approved) — two receiver crashes fixed on the way:**
1. `drop-on-late` doesn't exist on RTX GStreamer 1.20.3 (removed in 1.20) → verified the live
   property list → `drop-on-latency` (1.20's replacement).
2. Agent mistake: restart command omitted `cd /var/tmp/mcqueen-junior` → python couldn't find
   the script → died silently; stray log cleaned; restarted with cd.
3. Broker finding: Jetson tunnel ws died (`[BROKER] ws error jetson No PONG received after
   7.5 seconds` → disconnected) → sender has NO ws-reconnect → stayed blind to the receiver's
   new public port → kept sending to a dead mapping. Sender restarted → fresh rendezvous;
   receiver re-punch on PEER_CANDIDATE change VERIFIED working.

**RESULT — FULL LOOP FLAWLESS, GPU free (ViReL train.py GONE — 0% util):**
- SIGNALING_P2P ✓ (Jetson pub 152.58.29.86 ↔ RTX pub 14.139.108.62:60072); frames sustained;
  EXACT_FRAME_MATCH assoc_ok≈5.7k / assoc_miss≈950 (~14% honest WAN loss — Fix 1 delivering);
  CPU infer 0.13–0.2 ms; ctrl_sent ↔ CTRL_RX n≈1.8k; servo 90 / pwm 0.
- Bitrate sweep (Fix 3 verified live: achieved 2495 / 719 / 380 kbps matched targets):
  2500 → p50 709 ms / p95 2.5 s / 8.7 fps; 800 → 408 ms / 1.76 s / 12.3 fps;
  400 → **p50 391 ms / p95 1.67 s / 14.1 fps (FINAL)**.
- Not <100 ms: the phone-hotspot link loses ~55% of frames and adds ~390 ms RTT; 2026-08-11
  proof (43 ms control-only RTT) shows the pipeline can do better on a good link. Sub-second
  accepted by user.

**Leftover McQueen test procs still running** (not stopped — user hasn't said): Jetson sender
(python3 /tmp/gst_jetson_rtp_wan.py, --bitrate-kbps 400), RTX receiver PID 554981, broker +
cloudflared. Camera held by sender.

**Git**: nothing committed (DECISION 013). origin still 1 ahead (`57561db` AUDIT doc — reconcile
at first commit).

**Next**: user decides — evidence (capture_evidence.sh), kachow_probe (Q1), recording,
first hardware-verified commit, L1 real inference (approval required).

---

## 2026-08-14 — LAB session: L0 transport PROVEN; GPU contention stalls clean numbers (user "im at lab")

**Mode**: LAB. Goal: get the 100 ms loop test done. User provided SSH passwords (RTX + Jetson)
and authorized the runs; transient askpass helper
`/tmp/mcq_askpass.sh` created (delete after session; NEVER write passwords into repo files).

**Preflight (VERIFIED)**: Jetson USB SSH ok, camera present, hotspot ON (wlan0 10.147.40.55),
internet ok; RTX wired .132 ok (.179 dead), broker HEALTHY, venv python + cloudflared present;
GPU 100% busy with `/home/junior/ViReL/Tasks/vlmgrpo` `python train.py` (PID 490867, ~18.6 GB
VRAM) — inspected read-only (cwd, cmdline, exe, parent) → **NOT McQueen's, untouchable**.

**Fixes found during runs (all in uncommitted run_rtp_wan_test.sh):**
- F7: `pkill -f <script>` self-killed the remote shell (its cmdline contains the script name in
the nohup line) → sender/receiver never started, stale log misread as failure. Fixed with
ANCHORED patterns (`^python3 /tmp/gst_jetson_rtp_wan.py`, `^…/gst-webrtc-venv/bin/python
gst_rtx_rtp_receiver.py`). PROVEN via SURVIVED test.
- F8: stale `cloudflared.url` (2026-08-13 URL dead; running tunnel = new URL
`unfortunately-wrestling-kim-traveller.trycloudflare.com`) → refreshed; tunnel verified live.
- F9: Jetson sudo needs password (tty_tickets — cache doesn't cross PTYs) → step 7 sudo now
conditional on service active + `sudo -n` + bounded `timeout 10 sudo`; never hangs.

**L0 run 4 result (best)**: SIGNALING_P2P READY (Jetson pub 152.58.42.132 ↔ RTX
14.139.108.62:48699); sender SENT pkts 12060+, rtp_ts 39000→3327000 (F1 fix CONFIRMED live);
RTX frames_rx=16, assoc_ok=1 assoc_miss=0, ctrl_sent=1, infer_avg=169.75ms; 0 probe errors;
0 GST errors. **Then stalled**: GPU-starved NVDEC ~1 fps → appsrc backpressure → UDP thread
blocked → socket Recv-Q 216,192 B full → kernel dropped packets (12,000 sent, ~210 received).

**Findings → approved fixes (NEXT session implements):**
- F10 (BUG, approved): receiver `udp_loop` gates RTP→appsrc on `elif self.cur_meta is not None:`
— META loss drops delivered RTP. Fix: always push RTP; association separate (loss → assoc_miss).
- F11 (approved): NO rtpjitterbuffer in pipeline (`appsrc→rtph264depay→h264parse→decodebin→
videoconvert→queue(1,leaky)→appsink`). Fix: bounded rtpjitterbuffer, latency ≤50 ms,
drop-on-late, no retransmission.
- F12 (approved): sender hardcodes `x264enc tune=zerolatency bitrate=2500 speed-preset=ultrafast`
(line ~563) — bitrate is a GUESS. Fix: set bitrate from measurement.
- Plan A APPROVED: force `avdec_h264` + CPU dummy inference on RTX → pipeline never touches
GPU → ViReL irrelevant. User constraints (BINDING): jitter buffer latency never >50 ms; NO
retransmission/rtx (late frames dropped); do NOT raise prediction_timeout_ms (250 stays); NO
webrtcbin; do NOT chase NVENC (stalls on this Jetpack — fix bitrate/resolution instead).
- CTRL_RX invisibility explained: Jetson logs CTRL_RX only every 10th control → 1 control =
no log line. Control return path INCONCLUSIVE (needs sustained run).

**Broker**: user asked whether broker/cloudflared can be dropped using manual peer exchange
(each side learns the other's public IP:port; STUN on both sides; run script can read both
PUBLIC lines over SSH — no literal copy-paste). PROPOSED — user has more to say NEXT session.

**Leftover McQueen procs still running** (user: leave until decision): Jetson sender PID 11216,
RTX receiver PID 518003, RTX broker + cloudflared.

**Git**: local HEAD `6632913`; origin/jetson-nano ahead 1 (`57561db` "actaul audit", user web
push, only docs/AUDIT_2026-08-13.md — reconcile at first commit). NOTHING committed (013).

**Next**: user ends session, will open a new one and say "fix the server thing" → implement
A1–A4 + broker decision → rerun L0 → document → evidence → first hardware-verified commit.

---

## 2026-08-14 — Home prep H1–H5 complete (user "im at home")

**Mode**: HOME. Approved the home-prep plan (H1 broker/hygiene → H2 real-inference glue →
H5 probe prep → H3 PPGeo ResNet-34 → H4 evidence automation) so the next lab is TEST-ONLY.

**H1 — broker + machine hygiene (DONE)**
- `tools/realtime/broker.py` created from `docs/evidence/2026-08-13-lab-pull/rtx/broker.py`
  (py_compile OK); run_rtp_wan_test.sh step 1b now scp's the repo broker + checks
  `$RTX_PY` (exit 10) and `$RTX_DIR/cloudflared` (exit 11 + download hint).
- AGENTS.md §H machine-hygiene rule added; DECISIONS.md DECISION 014 (RTX = COMMON machine;
  remove only McQueen junk; keep-list; per-item human approval for deletions).
- DECISION 012 SUPERSEDED by DECISION 013 (hardware-verified commits/pushes only) earlier.

**H2 — real-inference engine (DONE)**
- `tools/realtime/inference_rtx.py`: InferenceEngine with newest-frame-wins 6-frame buffer,
  exact frame_id/capture_mono_ns echo, safety clamps (servo 45–115, pwm −70..100),
  numpy-only I420 decode, `_load_policy_classes` raises RuntimeError — no silent backbone
  substitution. `gst_rtx_rtp_receiver.py` integrated (`--inference dummy|real`,
  `_real_inference`/`_dummy_inference`, `meta=pred` echo, ENGINE stats in final report).
  `model_config_v2.py` SUPPORTED_BACKBONES += "tiny". run script steps 5/6 deploy
  inference_rtx.py + mcqueen_ml and set PYTHONPATH=$RTX_DIR.
- `test_inference_rtx.py`: **18/18 PASS** (CPU + CUDA, numpy decode, frame identity, clamps,
  newest-wins, config errors). Standalone CLI smoke: laptop GPU warmup 172 ms then steady
  ~3–4 ms/forward (LAPTOP number, NOT the 4090).

**H5 — kachow_probe label-path reporting (DONE)**
- Probe now prints per-packet `pwm` via the recorder's exact `throttle_to_pwm` (motor_enabled
  gating, clamp, ×255/1000) + final LABEL_PATH stats (throttle n/nonzero/min/max/distinct,
  pwm n/forward/reverse/min/max, steering extremes) + verdict: exit 0 = control AND PWM path
  proven, exit 3 = control OK but PWM unproven (drive forward AND reverse next time). PWM
  math re-verified (1000→255, −1000→−255, 500→128, disabled→0).

**H3 — PPGeo ResNet-34 adapter (DONE)**
- Cloned official OpenDriveLab/PPGeo (read-only, /tmp/opencode/PPGeo). Verified released
  "Visual Encoder (ResNet-34)" = `ResnetEncoder(34, num_input_images=1)` = PLAIN torchvision
  resnet34, forward normalize=True → layer4 → pool → 512-dim.
- Downloaded real checkpoint (87.3 MB, gdown; Google Drive id `1GAeLgT3Bd_koN9bRPDU1ksMpMlWfGXbE`,
  BaiduYun backup `itqi`) to `~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth`. Inspected:
  dict {"state_dict": OrderedDict}, **218 keys, standard torchvision names, NO prefix**.
- `mcqueen_ml/training/backbones.py` `PPGeoResNet34Backbone`: output_dim 512, internal
  ImageNet normalization (matches PPGeo), strict load, `RuntimeError` when checkpoint missing
  (no silent fallback — DECISION 015), lazy torchvision import. `test_backbones_ppgeo_resnet34.py`
  **5/5 PASS** (incl. strict torchvision equivalence); full TemporalDrivingPolicy end-to-end
  OK (2×6×3×224×224 → (2,2)).

**H4 — evidence automation (DONE)**
- `tools/realtime/capture_evidence.sh`: files milestone logs → `docs/evidence/<date>/<milestone>/`,
  exit 2 on missing/empty sources, prints unmissable `LOGS FILED →` banner (smoke-tested).
- `docs/evidence/MILESTONE_TEMPLATE.md`: n/p50/p95 per benchmark-v2 stage, stage-identity +
  zero-sample rules, artifact inventory, verdict.
- `tools/realtime/process_recording.sh`: validate_spool → convert_spool → capture_evidence;
  failed validation BLOCKS conversion (never convert bad spools). bash -n + behavior smoke OK.

**Verified (2026-08-14)**
- System python3 pytest: `pytest tests/ mcqueen_ml/ --ignore=test_temporal_policy_v2.py
  --ignore=test_backbones_ppgeo_resnet34.py` → **18 passed** (torch tests follow the existing
  ignore convention).
- mcqueen-laptop env unittest: temporal 3 + backbones 5 = **8 OK**; test_inference_rtx
  standalone **18/18**. Env: Python 3.12.13, torch 2.11.0+cu128, CUDA True (gdown added).
- All new/edited scripts py_compile / bash -n clean.

**Git state**: branch jetson-nano, HEAD == origin == `6632913`. NOTHING committed/pushed
(DECISION 013 — hardware-first). Pending files listed in CURRENT_TASK. User said they will
end the session after prep; state files brought to handoff grade.

**Next action**: TEST-ONLY lab — run_rtp_wan_test.sh green → capture_evidence + probe exit 0
+ real recording (process_recording.sh) → first hardware-verified commit (DECISION 013).

**Post-session audit fixes (same day, user asked "are you sure… flawless")**
- FOUND + FIXED: `kachow_probe.py` `self.results[result] += 1` had been dropped in the H5
  edit — without it the probe ALWAYS reported "NO VALID KACHOW PACKETS SEEN" (exit 2) and Q1
  could not be answered. Counter restored; also inlined `throttle_to_pwm` (removes recorder's
  cv2/record_row import chain from the probe). SIMULATED PROBE: full phone session through
  `_handle_packet` (hello → neutral-arm → fwd → rev → estop → re-neutral) → results counter,
  throttle/pwm collection, and the exit-0 verdict path all proven; inline PWM math verified
  byte-identical to recorder.throttle_to_pwm for the full input range; py_compile OK.
- FOUND + FIXED: `agent_self_audit.py` reported the context system NOT healthy — CURRENT_TASK.md
  was missing the required `## TEST PLAN` section. Section added (test-only lab sequence).
- FOUND + FIXED: OPEN_QUESTIONS.md Q2 ("WAN server thing") had been accidentally deleted;
  restored as PARTIALLY VERIFIED with the persistent-service residual.
- FOUND + FIXED: SESSION_LOG header said "Newest at the bottom" but actual convention is
  newest-at-top; header corrected. HANDOFF seniors-rule line removed (strict compliance).
- Re-verified after fixes: agent_self_audit healthy; startup check 35/35; pytest 18 passed;
  unittest 8 OK; test_inference_rtx 18/18.

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

---

## 2026-08-14 — Home session 3 (post-lab): GitHub restructure PLANNED, user updates GitHub later

**Mode**: HOME. User is at home; the 2026-08-14 lab session is fully wrapped (see sections
above). This session was PLANNING ONLY — zero GitHub changes, zero commits, zero pushes,
zero machine access.

**Arduino/ESP32 audit (Item 1):** verified repo has ZERO arduino/esp32 code references, BUT
GitHub (jetson-nano branch) still contains old-hardware files:
- `legacy/esp32/` (McQueenReverseFix + kachow_esp32_ap_v2, C firmware)
- `legacy/uno_q_previous/` (Arduino sketch UnoQDrive.ino + MCU services + old teleop)
- `legacy/oakd/` + `hardware/cad/oakdmount.stl` (OAK-D depth camera)
- `legacy/laptop_logger/` + `legacy/dataset_logging/` (superseded laptop-in-loop logging)

**Decisions made this session (user):**
- Purge scope = ALL of the above (52 files total), branch-only. KEEP `servohorn.stl` +
  `servomount.stl` + oakd… NO — user final word: remove oakd + laptop_logger + dataset_logging
  + esp32 + uno_q_previous + oakdmount.stl. Keep `hardware/cad/servohorn.stl` +
  `servomount.stl` + README (current servo hardware).
- History IS the backup (user accepted git-history approach over a local backup folder;
  tag `pre-purge-2026-08-14` will be created at commit time as the recovery point).
- New BINDING RULE (added to AGENTS.md §J): GitHub updates must keep the repo simple,
  functional, maximally reproducible.
- Fresh-machine reproducibility = FUTURE TASK (honestly NOT true yet; full gap list in
  CURRENT_TASK.md FUTURE WORK; est. 1–2 h laptop + lab verify).

**Status:** full restructure plan recorded in CURRENT_TASK.md FUTURE WORK + AGENT_STATE +
HANDOFF. User will update GitHub in a while (not now — "first we got some shit to do").
NOTHING executed. Next: await user's GO for the restructure, or whatever task comes first.

---

## 2026-08-14 — Home session 4 (evening): finalized next-lab plan + audits cleaned

**Mode**: HOME. PLANNING ONLY — no GitHub changes (user will do the GitHub update himself
after this; restructure plan untouched), no machines, no code changes.

**Day audit + error log brought to spec:**
- `docs/AUDIT_2026-08-14.md` CREATED (was missing — only 08-13 audit existed). Format matches
  AUDIT_2026-08-13.md: accomplishments, full problem table with fix statuses, current state,
  still-open. **No timestamps.**
- `docs/ERROR_LOG_2026-08-14.md` — was properly structured (F1–F12 + findings); removed the
  clock times it contained (21:41, 20:17).
- `docs/evidence/2026-08-14/wan-loop-measured/REPORT.md` — removed clock times (20:48–21:26,
  21:00→21:26, 21:47–21:50); kept IP:port values (NOT timestamps).
- **NEW BINDING RULE (AGENTS.md §C):** audits/error logs/evidence reports NEVER contain
  clock timestamps. Dates (day identity) allowed; IP:port values are not timestamps.

**Finalized next-lab scope (user decisions this session):**
- **Transport/latency ONLY. No training, no real inference.** The 8 old demos
  (`data/jetson_recordings/`, Aug 9–10) are NOT real driving data (user verdict) — no point
  training on them.
- **NO TRAINED POLICY EXISTS (verified):** find for *.pt/*.pth found only
  `~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth` (PPGeo encoder = feature extractor,
  outputs features NOT actuator commands). Training must wait for a real recorded dataset.
- **TRUE PATH RTT FIRST:** tomorrow's first diagnostic = Jetson pings the RTX's ACTUAL public
  IP (today's 46 ms was to Cloudflare 1.1.1.1 — gap identified). Decisive: ≈46 ms → floor
  ≈60 ms; 100+ ms → link is the wall.
- **Queueing attacks:** 320×240 @ 150 kbps + packet pacing (only if the floor says worth it).
- **Constants:** 30 fps, 50 ms jitter buffer (25 identical — keep margin), CPU decode/infer,
  no retransmission, 250 ms timeout.
- **REAL SPEC (user):** on real roads, camera→actuator as fast as possible. <100 ms was
  aspirational, NOT a hard requirement. Ideal road link: Jio 5G (RTT ~10–30 ms → <100 ms
  comfortably achievable); 4G borderline (~60 ms floor + queueing).

**Git/GitHub:** nothing touched. Restructure plan (CURRENT_TASK FUTURE WORK + AGENT_STATE +
HANDOFF) intact, awaiting user's own GitHub update.

**Freebuff capability notes**
- Native command-approval: Freebuff's terminal tool prompts the user for approval on
  non-trivial commands (implemented in the Freebuff runtime, not in repo files).
- Persistent project memory: NOT SUPPORTED BY FREEBUFF as a configurable feature — Freebuff
  stores per-chat history under `~/.config/manicode/projects/McQueen/chats/`, but there is no
  exposed project-instructions or persistent-memory configuration surface. The repo-based
  `.mcqueen/` system is the durable memory instead.
- Path restrictions: Freebuff scopes file reads/writes to the project root
  (`/home/kartik/McQueenWork/McQueen`); Markdown rules enforce behavior, not technical sandboxing.

---
