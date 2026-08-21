# CURRENT_TASK.md — ARCHIVED SECTIONS (superseded history)

> Moved here 2026-08-20 (session 3u) per DECISION 028 (state-file growth control).
> Live file: .mcqueen/CURRENT_TASK.md. This archive preserves superseded sections verbatim.

--- extracted verbatim from CURRENT_TASK.md ---

## CURRENT STATE — ENCODER BENCH TEST (session 3n, 2026-08-18 — SUPERSEDED by the car session 3s: bench abandoned, channel-B card obsolete)
The bench never completed (0-pulse diagnostic, user left). Car session 3s
superseded it: car wiring = channel A, wire colors corrected, bench card
obsolete (see docs/CAR_WIRING.md + ENCODER_BENCH.md correction header). Keep
below for history only.
- **Wiring done (bench card v2, channel B)** — TB6612/HW-166: PWMB←33, BIN1←16, BIN2←18,
  STBY→VCC, motor B01/B02, VCC←17, GND←6; VM←PSU+ 7.4 V; encoder blue→1 (3.3 V), white→6
  (GND), green→29 (A), yellow→31 (B). Runbook: `docs/ENCODER_BENCH.md` (channel B).
- **Tools built + tested 8/8 + deployed `~/encoder_bench/` on Jetson** (USB 192.168.55.1,
  key-auth SSH): identify/calibrate/sweep + gpio_probe + analyze + deploy script.
  Python 3.6 fix: `--mode` flag instead of subparsers `required=` (3.7+ only).
- **Results**: identify 0 pulses; probe = pins 29+31 constant HIGH, 0 transitions (×2
  runs, both shaft ends spun). Driver fault (partner) does NOT explain this — encoder is
  direct-to-Jetson. Next lab = fault isolation + polarity check per NEXT ACTION.
- Git: no commits (DECISION 013). State files 3n; mirror pushed; HOME mode.
## CURRENT STATE — DONKEY SIM-TRAINING (session 3k, 2026-08-18)
- **DONE**: full pipeline — dataset → torch-free converter (`tools/donkey/tub_to_sessions.py`)
  → prepack (14,337 frames, 2.8 GB) → frozen-supercombo + MLP head training
  (`models/train_frozen_action.py`) → offline eval (`eval_donkey_predictions.py`) →
  gym_donkeycar sim validation (`tools/donkey/sim_pilot.py`).
- **Trunk**: `driving_supercombo_master_batch.onnx` = batch-patched COPY of the verified
  60.9 MB master (6 reshape fixes + p_pad drop; `tools/donkey/patch_onnx_batch.py`); original
  untouched, SHA 659727c4…f8009b. action_adapter now batch-aware (2576/2574).
- **v1 results (25 epochs)**: best val_mse 0.49777; eval: head combined 0.0355 vs zero-shot
  1.2998 (36x better). Sim: head@no-cap crash@43 steps; zero-shot never steers
  (479 steps creep); head@throttle 0.1 "worked quite well" (user).
- **v2 RUNNING (100 epochs)**: `~/mcqueen/run/donkey/train_v2.log`, out
  `~/mcqueen/models/donkey_head_best_v2.pt`. Epoch ~8s at full GPU (robovista job — ViReL,
  NOT ours — held GPU early, now gone; it ran `evaluation.py --mode robovista --domain
  open_datasets --max_samples 20` from `/home/junior/ViReL/Tasks/vlmgrpo`, user-aware).
- **GPU-UTIL NOTE (user mandate, for TONIGHT'S DEBUG RUN)**: training uses only ~760 MiB VRAM
  and ~26% util — NORMAL for this workload (60 MB fp16 model, batch 32, onnx2pytorch = ~1500
  sequential kernel-launch-bound ops). VRAM can't be "filled" with a 60 MB model. FIX for the
  debug run: batch-size 128+ (more work per kernel → fewer launch stalls; epoch 8s → ~4-5s),
  measure epoch time + util % before/after, report honestly. Do NOT restart mid-run.
- **Sim env wiring fixed**: gym_donkeycar 1.3.1 (local clone) installed into mcqueen-openpilot
  env; class-based env API + Gymnasium tuples; `_yuv` exact mirror of rgb_to_supercombo_yuv;
  sim binary boots ~30s (Unity + Mesa Intel iGPU — NOT the RTX GPU), start_delay now 5s.
  `--max-throttle` + `--steer-gain` knobs added to sim_pilot.
- **REMAINING**: v2 eval + sim run @0.03/gain2.0, REPORT.md (skeleton exists in
  docs/evidence/2026-08-18/donkey-sim-training/), state files → 3k, mirror push, home hygiene.

## CURRENT STATE — DONKEY FILES RESTORED TO ORIGINAL PATHS (session 3j, user mandate; ONLY this done)
- **Restored on RTX** (verified): `~/mcqueen/donkeycar` → **`~/mysim`**, `~/mcqueen/datasets` →
  **`~/donkey_datasets`**, `~/mcqueen/donkey_sim` → **`~/donkey_sim`**, `~/mcqueen/gym-donkeycar` →
  **`~/gym-donkeycar`**. ~/mcqueen keeps ONLY non-donkey dirs (envs, mcq, models, openpilot, run,
  training, visualization).
- **Path refs fixed back**: myconfig.py `DONKEY_SIM_PATH = /home/junior/donkey_sim/DonkeySimLinux/
  donkey_sim.x86_64`; git-lfs/build-git-lfs.sh `sudo cp ~/go/bin/git-lfs /usr/local/bin`. No stray
  references to the old consolidated paths remain (grep CLEAN).
- Dataset intact: `~/donkey_datasets/circuit_launch_ed_1/` = 14,337 images + tarball 48,216,082 B.
  Sim binary executable at `~/donkey_sim/DonkeySimLinux/donkey_sim.x86_64`.
- Donkeycar still PAUSED (user: "we will continue when i say do donkeycar now okay").

## CURRENT STATE — SECURED + AWAITING NEW GOAL (user: "our goal has changed... fix everything for now stop and secure and manage... then i will give you the new goal")
- **Everything stopped/secured**: RTX clean (no test/training/donkey processes; broker
  intentional); laptop fine; mirror pristine; repo uncommitted-but-verified (DECISION 013).
- **Openpilot pipeline DONE** (smoke PASSED) — see `docs/OPENPILOT_PIPELINE.md` (say "show me
  the open pilot shit" to review it). Open design decision from §9 of that doc (frozen
  plan-based vs custom head) — pending, NOT blocking the new goal.
- **Jetson UNREACHABLE (BLOCKED)**: USB + Wi-Fi both dead (likely being moved to wall power by
  lab mate). mcqueen-edge.service restart pending (was stopped for the latency test). USER to
  check physically at the lab.
- **Donkeycar PAUSED** (user trigger "do donkeycar now" — steps below unchanged).

## CURRENT STATE — OPENPILOT PIPELINE COMPLETED (RTX, smoke PASSED 2026-08-17)
- **Model**: comma 2026-master `driving_supercombo.onnx` (60,881,999 B, SHA-256 VERIFIED
  `659727c4…f8009b`) at RTX `~/mcqueen/models/driving_supercombo_master.onnx`. Inputs = repo
  contract exactly; output = [1,2576] (hidden_state 1064:1576, plan 1576:2566); NO action head
  (old contract fabricated — see VERIFIED_FACTS).
- **Deployed**: `action_adapter.py` (frozen 29,996,510 params, plan-derived action),
  `smoke_frozen_action.py`, `extract_action_subgraph.py` (identity re-export) — repo + RTX.
- **SMOKE PASSED**: 0 trainable, action (1,4)/hidden (1,512)/plan (1,33,3), temporal step-2 OK.
- **OPEN DECISION (user, next session)**: fully frozen plan-based control (works NOW) vs add
  OUR OWN trainable head on features[512] (restores DECISION 027 retrain intent; requires
  training data + train_frozen_action.py rework). Then: real-frame path
  (`--real_frame` from Jetson), RTX latency measurement, Jetson safety-gate wiring.
- **Big model note**: big_driving_supercombo.onnx download corrupt → deleted; not needed.

## CURRENT STATE — DONKEYCAR PAUSED (user: "we will continue when i say do donkeycar now okay")
- **RESUME TRIGGER = user says "do donkeycar now"**. Everything staged, nothing running.
- **DONE**: dataset `circuit_launch_ed_1.tar.gz` COMPLETE (48,216,082 B) + SHA-256 VERIFIED
  (LFS OID a23d1df2…5cf00) + extracted → `~/donkey_datasets/circuit_launch_ed_1/` =
  **14,337 records** (15 catalogs + images/ + manifest.json) — official race-track tub.
- **BLOCKER (one command fixes it)**: donkey env MISSING `albumentations` (donkeycar 5.3.0 dep)
  → `donkey train` crashes ModuleNotFoundError. Fix: `pip install albumentations` in the
  `donkey` env. Env TF = CPU build 2.21.0 — GPU TF needs ~2–4 GB CUDA pip install, NOT feasible
  on this link; CPU training OK (~30–60 min for 100 epochs on i9-13900K).
- **NEXT when resumed** (physical commands on RTX; user is at the machine):
  1. `conda activate donkey && pip install albumentations`
  2. `cd ~/mysim && nohup donkey train --tub ~/donkey_datasets/circuit_launch_ed_1 --model models/pilot.h5 > ~/donkey_datasets/train_pilot.log 2>&1 &`
  3. SIM validation: `~/donkey_sim/DonkeySimLinux/donkey_sim.x86_64` + `python manage.py drive --model models/pilot.h5` (web UI localhost:8887 → Local Pilot); optional pretrained-pilot comparison from `circuit_launch_20210716/models/`.
- Agent watches `~/donkey_datasets/train_pilot.log` over SSH once training starts.

## CURRENT STATE — LAB SESSION 3i (2026-08-17); CURRENT TASK = DONKEYCAR AUTOPILOT (plan only)
- **NEW USER TASK (2026-08-17, user mandate)**: donkeycar route to an autopilot — download
  official donkeycar datasets → train an autopilot per the official docs (docs.donkeycar.com
  `guide/deep_learning/train_autopilot/`). NO donkey work done yet — plan + explanation only
  (user: "do not do anything related to donkey now just propose plan and explain shit").
- **DONKEYCAR READY ON RTX (discovered this session)**: miniconda env `/home/junior/miniconda3/envs/donkey`
  ALREADY has donkeycar 5.3.0 + TensorFlow 2.21.0 + keras 3.15.1 + gym_donkeycar 1.3.1 (simulator)
  + numpy/pandas, Python 3.11.15 — zero installs needed. Training machine = RTX (GPU).
- **Dataset**: `autorope/donkey_datasets` (GitHub, LFS): `large_dataset/` = 39 tarballs +
  `circuit_launch_20210716/` = 3 tarballs + myconfig.py + pretrained models/. Pick
  `circuit_launch_ed_1.tar.gz` (48,216,082 B, OID sha256 a23d1df233d41d4b98a4646c5e7b3bf7196546b0354304d901653bd5ce5fcf00)
  → LFS media URL (no git-lfs needed). Download STARTED on RTX `~/donkey_datasets/` (wget,
  ~4.4/48 MB when PAUSED by user to secure state first — resume/wait, then verify OID, extract,
  inspect manifest). Plan: `donkey train --tub <tub> --model models/pilot.h5` in the donkey env;
  then evaluate; optionally gym_donkeycar sim validation later.
- **JETSON MYSTERY SOLVED (power bank died)**: Jetson was off-network because its power bank ran
  out (NOT network). New power bank now; user will have the lab mate switch Jetson to WALL POWER
  tonight. Jetson booted + on `SRA_Upper` (2.4GHz) Wi-Fi wlan0 192.168.0.112; primary SSH path =
  USB gadget `sravjti@192.168.55.1` (l4tbr0, stable). **Jetson radio CANNOT see 5GHz
  `SRA_Upper_5G`** (hardware limit, verified nmcli) — wall-power plan needs 2.4GHz `SRA_Upper`.
- **Jetson clock fixed**: was ~14 h behind → `timedatectl` → System clock synchronized: yes.
  Camera: `/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0`.
- **Tunnel self-heal VERIFIED LIVE**: Jetson new URL `https://window-dts-pre-rivers.trycloudflare.com`
  auto-reported to RTX `/var/tmp/mcqueen-junior/url-reports.txt` (old `cincinnati-…` dead).
  `~/mcqueen-remote/jetson.url` UPDATED. `mcqueen-edge.service` STOPPED on Jetson (camera freed).
- **LATENCY TEST (LAN) — TOOLING BUILT, RUN NOT COMPLETED, PAUSED per user**: broker restarted on
  RTX as `0.0.0.0:8765` (was 127.0.0.1 — needed for LAN reach; left running, healthy). NEW
  `tools/realtime/mini_stun.py` (local STUN → LAN candidates, avoids NAT hairpin; receiver parser
  needs attr reserved byte = 1 — fixed) + NEW `tools/realtime/run_rtp_lan_test.sh` (script; sections
  5/6 break under pkill-self-match — use PID-file or separate calls). Sender-receiver rendezvous on
  LAN was NEVER fully established; NO full-loop latency numbers. **ALL test processes STOPPED**
  (receiver/sender/mini_stun killed; broker stays). Root cause of earlier confusion: `pkill -f`
  inside the tool's bash wrapper kills the wrapper itself (pattern appears in the start command) —
  use bracketed patterns that don't appear un-bracketed + separate kill/start calls.
- **OPENPILOT PIPELINE (paused mid-way, RTX)**: supercombo v0.9.4 fetched + SHA-256 VERIFIED
  (`d7f95f6bfa1c76567e186c806e75fc0ab900e3bd99f9514bdece99364ffaf8a8`, 47,501,059 B) but WRONG
  API (new unified inputs `input_imgs/big_input_imgs/desire [1,100,8]`, output `outputs [1,6120]`,
  408 nodes, NO action head) — `extract_action_subgraph.py` FAILED on it. Correct target =
  OLD-API supercombo (img/big_img/desire_pulse/action_t/features_buffer [1,24,512] → mul_48/
  linear_80/mul_41, 874 nodes). **v0.8.16 downloaded COMPLETE on RTX** (`~/mcqueen/models/supercombo.onnx`,
  95,165,081 B — API check + OID verify PENDING). Env `/home/junior/mcqueen-openpilot` = lerobot
  clone + onnx 1.22.0 + onnx2pytorch 0.6.0. `models/*.py` deployed to RTX `~/mcqueen/models/`
  (+ new `smoke_frozen_action.py`). GPU 92% busy (neighbor job, 3119 MiB) — fine for conversion.
- Start-of-session ritual (N): read AGENTS.md + state files + git status, recreate todo list.

## CURRENT STATE — SESSION CLOSED (2026-08-16 night); NEXT SESSION = OPENPILOT SETUP ON RTX
- **Discord post POSTED** (McQueen channel, SRA server): short tunnel update + screenshots — SSH
  proof one-liner (HOME WIFI: Kartik → LAB WIFI: SRA_Upper → RTX 4090 35C 18W 0%) verified live.
  Proof artifacts: `~/mcqueen-remote/mcqueen_rtx_proof.png`, one-liner in clipboard history.
- **Jetson**: OFF the lab network (verified: URL DNS-dead, /24 scan negative, no NVIDIA MAC in ARP).
  Deferred per user. To resume: lab person checks power → boot → auto-report (~2 min, self-healing)
  → update jetson.url. Optional morning task.
- **NEXT (morning, RTX-ONLY)**: openpilot setup on the RTX — 1) fetch supercombo.onnx (comma.ai
  public release; document URL + SHA-256) on RTX; 2) scp `models/` to RTX; 3) run
  `extract_action_subgraph.py`; 4) onnx2pytorch on RTX; 5) FrozenActionModel smoke. Laptop:
  spool→openpilot-session converter + tests (no torch on laptop, DECISION 023/024).
- Start-of-session ritual (N): read AGENTS.md + state files + git status, recreate todo list.

## CURRENT STATE — BOTH MACHINES REACHABLE FROM HOME (session 3f, 2026-08-16, VERIFIED)
- **RTX ✓ + Jetson ✓ both reachable from the home network**: RTX via :2222 (`omen`, URL stable);
  Jetson via :2223 (`ubuntu` aarch64, URL `cincinnati-longer-licensed-marcus.trycloudflare.com` in
  jetson.url). Root-caused the silent report failure (boot oneshot timing) + hardened: dedupe +
  2-min retry timers on both machines — URL auto-recovery is now self-healing.
- **Openpilot setup on RTX = next** (user back in the evening): fetch supercombo.onnx (comma.ai
  public release; URL + SHA-256 documented) → deploy `models/` to RTX → `extract_action_subgraph.py`
  → onnx2pytorch on RTX → FrozenActionModel smoke. Laptop: spool→openpilot-session converter
  (no torch on laptop, DECISION 023/024).

## CURRENT STATE — HOME SESSION ACTIVE (session 3e, 2026-08-16)
- **RTX REACHABLE FROM HOME — VERIFIED (milestone)**: key-only SSH via tunnel (:2222) → `omen`, unit
  active, URL stable == rtx.url. Remote access from the home network confirmed for the first time.
- **Jetson: OFF at the lab** — unreachable as designed; no new URL in RTX `url-reports.txt` (6 polls,
  never plugged in). PAUSED per user; resumes when the lab person plugs it in (new URL auto-reports).
- **User out until 22:00–23:00 → RTX-ONLY openpilot setup then**: fetch supercombo.onnx (comma.ai
  public release; URL + SHA-256 documented) → deploy `models/` to RTX (scp via tunnel) →
  `extract_action_subgraph.py` → onnx2pytorch on RTX → FrozenActionModel smoke. Laptop: spool→
  openpilot-session converter + tests (no torch on laptop, DECISION 023/024).

## CURRENT STATE — REMOTE ACCESS DONE + HOME WORKFLOW VALIDATED (sessions 3b/3c/3d, 2026-08-16, VERIFIED)
- **DECISION 026 EXECUTED + VERIFIED**: cloudflared TCP quick tunnels on RTX (`mcqueen-rtx-ssh-tunnel`)
  + Jetson (`mcqueen-jetson-ssh-tunnel`), systemd active+enabled (reboot-survivable; URLs change per
  restart). End-to-end SSH verified through both from the laptop client. URLs local-only:
  `~/mcqueen-remote/rtx.url` + `jetson.url`. Recipe: `docs/remote/REMOTE_ACCESS.md` (uncommitted).
- **Home workflow VERIFIED (reboot test)**: Jetson reboot → ~36 s → auto Wi-Fi → auto tunnel (new
  URL) → boot unit auto-reports URL to RTX file (`/var/tmp/mcqueen-junior/url-reports.txt`) via
  restricted key; mirror unit reports RTX URL to Jetson (`mcqueen-rtx-url-report`). SSH keys
  (laptop→both, no-password) installed + verified. Lockout only if RTX rebooted AND Jetson off.
- Jetson on `Delta_Virus_Lab` Wi-Fi (192.168.0.112, internet OK). Jetson powered OFF when user leaves;
  home sessions start with a lab phone call to plug it in.

## CURRENT STATE — OPENPILOT DIRECTION (session 3a, 2026-08-16)
- **DECISION 027 (user mandate)**: the COMPLETE openpilot (comma.ai supercombo) pipeline is THE driving
  model — vision encoder + temporal hydra FROZEN, ONLY the final action layer retrained on McQueen data.
  PPGeo ResNet-34 + Drive-JEPA ViT DROPPED (no further work; code removed at the next hardware-verified
  commit, §J simplicity). DECISION 015 partially superseded: weights-out-of-repo rule STAYS;
  `MCQUEEN_PPGEO_CKPT` → `MCQUEEN_SUPERCOMBO_ONNX` convention.
- Openpilot code ALREADY in repo `models/` (commit `536f2d5`, on origin): `action_adapter.py`
  (FrozenActionModel — supercombo ONNX subgraph via onnx2pytorch), `extract_action_subgraph.py`,
  `train_frozen_action.py`. **NEVER executed — UNVERIFIED** (no onnx anywhere on the laptop).
- supercombo.onnx: NOT on laptop — fetch the comma.ai public release AT THE LAB (document URL + SHA-256
  in the repo before use).
- Q13 = WAIT for the openpilot action head (tiny rehearsal ckpt NOT used live). v_ego=0; big_img = same
  narrow frame; 10 fps recording kept (Q14). Inference compute: GPU if neighbor job free, CPU fallback.
- PPGeo ckpt (`~/Downloads/mcqueen_ppgeo/`) + `rehearsal_temporal.pt` stay on disk — dead references.

## CURRENT STATE — DECK (CLOSED, 2026-08-16)
- 3rd-biweekly presentation DONE — user: "my presentation went great, the video too, now forget about all
  that". All deck threads CLOSED (Google Slides fixes, v1-vs-v2 pick, talk guide, daily log).

## NEXT ACTION (EXACTLY ONE — FIRST HOME SESSION: OPENPILOT SETUP ON RTX)
1. ~~DECISION 026 remote-access infra~~ **DONE + VERIFIED (sessions 3b/3c/3d)** — RTX + Jetson tunnels
   live; home workflow validated (phone call → plug Jetson → ~5 min → read new URL from
   `/var/tmp/mcqueen-junior/url-reports.txt` on RTX via RTX tunnel → update jetson.url → connect).
2. **Home session = openpilot setup on the RTX** (torch lab-only, DECISION 023/024 — laptop never runs
   torch): RTX tunnel → fetch supercombo.onnx (comma.ai public release; URL + SHA-256 documented) →
   deploy `models/` code to RTX (scp via tunnel) → `extract_action_subgraph.py` →
   onnx2pytorch conversion → FrozenActionModel smoke. Laptop: spool→openpilot-session converter + tests.
   Jetson (after phone call): camera/capture checks over SSH when needed.
3. **Training when data exists** (Tuesday lab recording ~20 laps): pull spools home → convert → push to
   RTX via tunnel → train action head → evaluate.
4. **Re-punch validation DEFERRED** (user: "fuck the repunch shit if its gonna take soo much time" —
   2026-08-16): not needed for home runs (tunnels are separate); needs a hotspot phone at the lab
   (CGNAT test). broker.py stays in the repo (DECISION 019: removal rides validation; deferred).
   Revisit at a future lab visit.
5. **Hardware-verified commit** (DECISION 013, next lab): pending verified work (AGENTS.md rule-R.8
   edit, trainer + transport scripts + tests, RESUME gate, inference_rtx.py `--checkpoint`, evidence
   filings, REMOTE_ACCESS.md doc) + PPGeo code removal (DECISION 027) + openpilot pieces iff verified.
## ACCEPTANCE CRITERIA (session 3n — all MET)
- DECISION 027 recorded; all 7 state files pristine (openpilot direction, Q13-wait, PPGeo removal queued,
  lab-day-1 order). ✓
- Deck threads closed per user. ✓

## TEST PLAN (superseded transport/latency scope from 2026-08-14 is DONE — sessions 2r/2s: full WAN loop
p50 ~276 ms, bitrate A/B, Jio 5G no-win). Current lab test plan = NEXT ACTION above.
