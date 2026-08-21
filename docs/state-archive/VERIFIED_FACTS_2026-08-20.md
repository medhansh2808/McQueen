# VERIFIED_FACTS.md — ARCHIVED SECTIONS (superseded history)

> Moved here 2026-08-20 (session 3u) per DECISION 028 (state-file growth control).
> Live file: .mcqueen/VERIFIED_FACTS.md. This archive preserves superseded sections verbatim.

--- extracted verbatim from VERIFIED_FACTS.md ---

# >>> 2026-08-18 (session 3n) — ENCODER BENCH TEST: USB link, tools deployed, 0-pulse result, partner driver finding <<<

- FACT: **Jetson reachable over USB device-mode networking, SSH key-auth, no password**:
  laptop iface `enxb6c7aa1a45a2` = 192.168.55.100/24 ↔ Jetson 192.168.55.1 (ping OK ~3 ms);
  `ssh sravjti@192.168.55.1` works with the existing key (BatchMode OK, uname aarch64).
  SOURCE: direct session runs. CONFIDENCE: VERIFIED.
- FACT: **Encoder bench tools deployed to `~/encoder_bench/` on the Jetson and run**:
  bench_encoder_sweep.py help + import OK under Jetson system python3 (3.6) — after two
  py3.6 fixes (subparsers `required=` is 3.7+ → `--mode` flag; hardcoded laptop SYS_PATH →
  __file__-derived). Unit tests 8/8 PASS on the laptop. SOURCE: ssh runs + unittest. VERIFIED.
- FACT: **identify run (pins 29=A, 31=B, user hand-spinning the motor shaft): 0 pulses on
  both pins.** SOURCE: bench_encoder_sweep.py identify output. VERIFIED.
- FACT: **gpio_probe ×2 (6 s windows, user spinning output shaft then the motor's rear bare
  shaft): pins 29+31 CONSTANT HIGH, 0 transitions** (~70,495 + ~69,362 samples each, all
  high). Jetson.GPIO pull_up_down is IGNORED (warning seen) — no software pull-ups exist.
  Interpretation: inputs actively driven high, NOT floating; encoder unpowered would
  float/noise. SOURCE: gpio_probe.py output. VERIFIED.
- FACT: **TB6612/HW-166 driver SUSPECTED FAULTY (partner bench report, agent NOT present)**:
  motor on channel B drives FORWARD only; on channel A drives REVERSE only. Encoders
  tested FINE by the partner. SOURCE: user relay of partner's test. CONFIDENCE:
  PARTIALLY VERIFIED (independent confirmation pending).
- FACT: **The driver fault cannot explain the 0-pulse encoder read** — the encoder is wired
  directly to Jetson pins 29/31, never through the driver. SOURCE: wiring card v2.
  VERIFIED (wiring).

# >>> 2026-08-18 (session 3l, overnight) — CHESTNUT LoRA v1/v2 results, dataset expansion, v3 design <<<

- FACT: **Chestnut batch patch VERIFIED**: big_driving_supercombo.onnx (1.75 GB) has 6 batch-1-hardcoded
  Reshape initializers (val_789 [1,3072]→[-1,3072], val_808 [1,-1]→[-1,200] = desire_pulse flatten
  (1,25,8); plain [-1,-1] is illegal, val_822 [1,1,512], val_855 [1,9,3,8,64], val_911 [1,8,64,9],
  val_924 [1,9,512]→[-1,…]) + output-concat 'pad' (1,2) constant dropped (output 2580→2578; all used
  slices ≤2578). Batch-1 outputs identical to original (max abs diff 0.0); onnx.checker valid.
  Original untouched. SOURCE: patch_chestnut_batch.py run + compare logs. VERIFIED.
- FACT: **Reconverted model chestnut_onnx2torch_sd_batch.pt (6,124,020,429 B) works batch-16**:
  deterministic (1,2578)/(16,2578), 6/6 iterations identical. The "[16,-1] invalid for input of size
  2578" failure was a TEST-SCRIPT bug (`b(...)[0]` on (16,2578) → row 0 (2578,) then .view(16,-1)).
  VERIFIED.
- FACT: **onnx2pytorch list-index bug (torch 2.9+)**: operations/gather.py:13 + slice.py:86 used
  `data[selection]` with a list → list becomes tensor index → garbage shape tensors. Fixed in-venv:
  `data[tuple(selection)]`. convert/model.py has FAILOP instrumentation (lines 234/238/246/257).
  VERIFIED (batch-16 test passes after fix).
- FACT: **LoRA v1 results (ed_1 only, raw labels, 10 epochs, batch 16, lr 1e-4, r16/a32)**: best val
  0.23681 (epoch 2) → chestnut_lora_best.pt (6,169,093,517 B). Smoke train loss 0.82212. Sim: steers
  full range [-0.164,1.000] but oversteers → runs 35/8 steps (max_cte 9.493/7.054, max_speed 2.76/2.03);
  curv_floor 2.5 variant 10 steps (steer [-0.008,0.199]). GATE FAIL. ROOT CAUSE: label scale — openpilot
  action = curv·v²; v1 labels were raw curv with v_assumed=1, mismatched to runtime /v² at v≈2.7.
  VERIFIED.
- FACT: **Dataset source FOUND**: autorope/donkey_datasets GitHub (LFS). Fetch
  `https://media.githubusercontent.com/media/autorope/donkey_datasets/master/<path>`; sha256 must equal
  LFS OID from the pointer file. 39 tarballs in large_dataset/. VERIFIED.
- FACT: **Expansion datasets (5 tarballs ~335 MB, all SHA-verified, ~/donkey_datasets/expansion/)**:
  circuit_launch_ed_2 (16 catalogs), circuit_launch_adam_1 (5), circuit_launch_20210716_{1611,1715,1826}
  (35/18/29; nested murmurpi4_*/data/). Converted (tub_to_sessions.py per-tub out dirs + cp -r merge
  with offsets; prepack_sessions.py cv2-YUV npy) → sessions_expanded: **165 train (81,055 frames) +
  43 val (20,263), 20 GB** (ed_2 12368/3092, adam 3809/952, 1611 27537/6884, 1715 14165/3541,
  1826 23176/5794). VERIFIED.
- FACT: **LoRA v2 results (expanded data, curv·9 labels)**: epochs 000 T21.602/V18.510 (2155 s),
  001 T13.246/V15.575, 002 T11.547/**V14.578 best** → chestnut_lora_best_v2.pt (05:41), 003 T10.328/V14.690;
  cut at epoch 3 (~35.8 min/epoch). Sim (floor 3.0): runs 51/16 steps (max_cte 8.504/8.779,
  max_speed 2.40/2.63), **action[0,0]=60.031, accel −6.426** — OOD beyond the frozen head's natural
  scale (~[-1,1]) → full-lock crashes. GATE FAIL → v3. VERIFIED.
- FACT: **v3 design = raw-curvature training targets + runtime curv·v² mapping**: trainer
  label_to_action verified (steer 0.1 → 0.224); pilot `--action-scale 9.0` (=V_ASSUMED², V_ASSUMED=3.0),
  `curv = clamp(a0,±30)·9/max(3,v)²`, accel clamp ±4. Runbook docs/CHESTNUT_PIPELINE.md. VERIFIED (code).
  v3 RESULT UNKNOWN — killed mid-epoch-0 on user stop; no checkpoint.
- FACT: **RTX secure at stop**: 0 train_chestnut_lora processes; nvidia-smi process table empty;
  chestnut_lora_best.pt + chestnut_lora_best_v2.pt present. VERIFIED.

# >>> 2026-08-18 (session 3k, home evening) — JETSON ON WALL POWER, REACHABLE FROM HOME <<<

- FACT: **Jetson switched to WALL POWER by the user** (before leaving the lab) and is ON.
  Booted, joined lab Wi-Fi, tunnel self-healed: new URL `https://file-checkout-matching-
  volume.trycloudflare.com` auto-reported to RTX `/var/tmp/mcqueen-junior/url-reports.txt`
  (last line). Laptop's local cloudflared for port 2223 re-pointed (kill old PID + restart
  `./cloudflared access tcp --hostname <new url> --url 127.0.0.1:2223` from ~/mcqueen-remote;
  ~/mcqueen-remote/jetson.url updated). Verified from HOME: `ssh -p 2223 sravjti@127.0.0.1`
  → JETSON_OK (ubuntu, aarch64). RTX also reachable from home (port 2222, omen, GPU 0%).
  CONFIDENCE: VERIFIED.

# >>> 2026-08-18 (session 3k) — donkey train + sim validation COMPLETE <<<

- FACT: **v2 head trained 100 epochs** (frozen supercombo trunk + MLP 512-128-2, batch 32,
  fp16 AMP): best val_mse **0.46001** (epoch 97) -> `~/mcqueen/models/donkey_head_best_v2.pt`;
  train 0.9655->0.42559. v1 (25 ep): 0.49777 (epoch 23). SOURCE: train_v2.log + ckpt metadata
  (epochs=98, history tail). CONFIDENCE: VERIFIED.
- FACT: **Offline eval (2,861 val windows)**: v2 combined MSE 0.03176 (steer 0.05353,
  throttle 0.00999); v1 0.03546; zero-shot 1.29977 (steer 0.10108, throttle 2.49846).
  v2 = 41x better than zero-shot. SOURCE: eval_donkey_predictions.py output. VERIFIED.
- FACT: **Batch-patched ONNX verified**: batch-1 outputs identical to original (max diff
  0.0); batch-32 shapes (32,4)/(32,512)/(32,33,3); output width 2574 (p_pad dropped).
  Original driving_supercombo_master.onnx untouched (SHA 659727c4…f8009b). VERIFIED.
- FACT: **Sim no-assist ceiling** (v2 head, circuit_launch, throttle caps, no telemetry
  assists): 751 (run A) / 239 (run B) / 255-250 / 673-670 (trim -0.08) steps — always the
  same sharp right corner; run-to-run spawn + iGPU frame jitter causes variance. Zero-shot:
  479 steps, steer range [-0.053, 0.021] (never turns). cte-assist (removed per user):
  1028/1018 steps @0.04/assist-0.5, mean_cte ~1.1. SOURCE: docs/evidence/2026-08-18/
  donkey-sim-training/sim_*.log. VERIFIED.
- FACT: **gym_donkeycar 1.3.1 installed into mcqueen-openpilot env** from the local clone
  `~/gym-donkeycar` (commit 9fd36b0; PyPI only has 1.0.x) — imports OK with numpy 2.2.6;
  env API = class-based (CircuitLaunchEnv/GeneratedTrackEnv) + Gymnasium tuples
  (reset->(obs,info), step->5-tuple). SOURCE: install log + import test. VERIFIED.
- FACT: **Sim env quirks**: binary listens on 9091 only with DISPLAY set (~30 s boot; renders
  on Mesa Intel iGPU, not the RTX GPU); env reset() starts the car hand-braked (brake=1.0).
  SOURCE: port probe + donkey_env.py source. VERIFIED.
- FACT: **Neighbor GPU jobs**: robovista `evaluation.py --mode robovista` (from
  /home/junior/ViReL/Tasks/vlmgrpo) then Ameya's `splaterra/tinysplat train.py`
  (github.com/javAmeya, run from interactive pts/17 @ 192.168.0.135, checkpoints
  /usr/local/models/splaterra-tinysplat-checkpoints) — NOT McQueen's; user talked to Ameya;
  nothing killed by agent without user OK. VERIFIED (ps/proc inspection).
- FACT: **Dataset/converter pipeline verified end-to-end**: 14,337 records -> 11,470 train
  (23 sessions) / 2,867 val (6 sessions), prepacked (6,128,256) uint8 .npy, 2.8 GB;
  torch-free converter unit-tested on laptop (ALL PASS). VERIFIED.

# >>> 2026-08-18 (session 3j) — donkeycar files restored on RTX <<<

- FACT: **Donkeycar files restored to original RTX paths (session 3j, user mandate)**:
  ~/mcqueen/donkeycar → ~/mysim (manage.py/myconfig.py/config.py/calibrate.py/train.py/data/models/
  logs/git-lfs/unitylog.txt); ~/mcqueen/datasets → ~/donkey_datasets (circuit_launch_ed_1/ = 14,337
  images, tarball 48,216,082 B byte-exact); ~/mcqueen/donkey_sim → ~/donkey_sim
  (DonkeySimLinux/donkey_sim.x86_64 executable, 1.1G); ~/mcqueen/gym-donkeycar → ~/gym-donkeycar
  (source clone; env's gym_donkeycar 1.3.1 = NON-editable pip install — move safe). Path refs fixed
  back: myconfig.py DONKEY_SIM_PATH = /home/junior/donkey_sim/DonkeySimLinux/donkey_sim.x86_64 (was
  mangled to .../DonkeySimLinux/mcqueen/donkey_sim.x86_64); git-lfs/build-git-lfs.sh `sudo cp
  ~/go/bin/git-lfs /usr/local/bin` (was .../go/bin/mcqueen/donkeycar/git-lfs). Recursive grep for old
  consolidated paths = CLEAN. ~/mcqueen keeps ONLY non-donkey dirs (envs, mcq, models, openpilot, run,
  training, visualization). SOURCE: live SSH mv + post-restore verification. CONFIDENCE: VERIFIED.
- FACT: **Jetson off-network mystery SOLVED = dead power bank** (2026-08-17, session 3i): the
  3g disappearance was the power bank running out, NOT a network fault. Jetson verified via USB
  gadget `192.168.55.1` (l4tbr0) + Wi-Fi `SRA_Upper` wlan0 192.168.0.112. **Jetson radio CANNOT
  see 5GHz `SRA_Upper_5G`** (nmcli scan: only 2.4GHz SSIDs listed — hardware limit; laptop and
  RTX are on 5G). Wall-power switch planned by lab mate (needs the 2.4GHz SSID). SOURCE: live
  SSH + nmcli scans. CONFIDENCE: VERIFIED.
- FACT: **Jetson clock was ~14 h behind; fixed via timedatectl** (2026-08-17, session 3i):
  `System clock synchronized: yes` after sync. Camera present:
  `/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0`.
  SOURCE: live ssh. CONFIDENCE: VERIFIED.
- FACT: **Tunnel self-heal VERIFIED LIVE** (2026-08-17, session 3i): Jetson booted → new URL
  `https://window-dts-pre-rivers.trycloudflare.com` auto-appended to RTX
  `/var/tmp/mcqueen-junior/url-reports.txt` (the 3f dedupe+retry hardening works end-to-end);
  old `cincinnati-…` URL dead. SOURCE: RTX file + Jetson log. CONFIDENCE: VERIFIED.
- FACT: **supercombo v0.9.4 has the NEW unified API — INCOMPATIBLE with repo models/ code**
  (2026-08-17, session 3i): inputs `input_imgs [1,12,128,256]`, `big_input_imgs`, `desire
  [1,100,8]`, `traffic_convention`, `nav_features [1,256]`, `features_buffer [1,99,128]`;
  single output `outputs [1,6120]`; 408 nodes; NO action head (only hydra.final_layer.meta /
  desire_pred / road_transform / pose / wide_from_device_euler). SHA-256 VERIFIED
  (`d7f95f6bfa1c76567e186c806e75fc0ab900e3bd99f9514bdece99364ffaf8a8`, 47,501,059 B).
  `extract_action_subgraph.py` FAILED on it: `ValueError: names not found in value_infos:
  img, big_img, desire_pulse, action_t`. Repo code targets OLD API (img/big_img/desire_pulse/
  action_t/features_buffer [1,24,512] → mul_48/linear_80/mul_41; 874 nodes;
  on_policy_model.temporal_hydra.final_layer.action.weight [4,512]). SOURCE: onnxruntime
  session dumps on RTX + failed extract run. CONFIDENCE: VERIFIED.
- FACT: **supercombo v0.8.16 (old API) fully downloaded on RTX** (2026-08-17, session 3i):
  `~/mcqueen/models/supercombo.onnx` = 95,165,081 B (matches GitHub LFS pointer size; OID
  check + API dump PENDING). SOURCE: RTX ls + GitHub API. CONFIDENCE: PARTIALLY VERIFIED.
- FACT: **RTX has a READY donkeycar env** (2026-08-17, session 3i):
  `/home/junior/miniconda3/envs/donkey` — Python 3.11.15, donkeycar 5.3.0, tensorflow 2.21.0,
  keras 3.15.1, gym_donkeycar 1.3.1, numpy 2.4.6, pandas 3.0.5. NO tensorflow/donkeycar in
  lerobot/mcqueen-openpilot//opt/mcqueen envs (checked). SOURCE: conda env + pip list on RTX.
  CONFIDENCE: VERIFIED.
- FACT: **donkey_datasets repo = git-lfs; direct media URL works without git-lfs**
  (2026-08-17): `large_dataset/` = 39 tarballs (132–134 B pointer files); `circuit_launch_ed_1.tar.gz`
  size 48,216,082 B, LFS OID sha256 a23d1df233d41d4b98a4646c5e7b3bf7196546b0354304d901653bd5ce5fcf00;
  `circuit_launch_20210716/` = 3 tarballs + myconfig.py + pretrained models/. Fetch =
  `https://media.githubusercontent.com/media/autorope/donkey_datasets/master/<path>`.
  SOURCE: GitHub API + pointer files. CONFIDENCE: VERIFIED.
- FACT: **Official donkeycar autopilot workflow** (docs.donkeycar.com, fetched 2026-08-17):
  collect tub data → transfer → `donkey train --tub <path> --model models/pilot.h5 [--type
  linear|categorical|...]` (4.3+ auto-creates tflite; `--transfer` for continued training;
  augmentations MULTIPLY/BLUR, transformations CROP/TRAPEZE; TRAIN_FILTER) → deploy → `python
  manage.py drive --model models/pilot.h5` (tflite fastest: `--type tflite_linear`). 10–20 laps
  / 5–20k images recommended; tubclean to remove mistakes. SOURCE: docs.donkeycar.com guide
  deep_learning/train_autopilot + utility/donkey. CONFIDENCE: VERIFIED (docs).
- FACT: **LAN latency-test tooling built; run NOT completed** (2026-08-17, session 3i):
  broker.py on RTX now bound `0.0.0.0:8765` (was 127.0.0.1; healthy — left running). NEW
  `tools/realtime/mini_stun.py` (RFC-5389-style local STUN returning LAN candidates; receiver
  parser requires XOR-MAPPED-ADDRESS reserved byte == 1 — implemented) + NEW
  `tools/realtime/run_rtp_lan_test.sh` (LAN variant, local broker + local STUN, no
  cloudflared). Full-loop rendezvous NOT achieved (no latency numbers). Sender→receiver media
  flew only while the production `mcqueen-edge` loop was running earlier (frames_rx=4253 was
  THAT loop, not the test). All test processes STOPPED. SOURCE: live runs + logs.
  CONFIDENCE: VERIFIED (tooling), FAILED/NOT-COMPLETED (test).
- FACT: **pkill -f inside the tool's bash wrapper kills the wrapper itself** (2026-08-17,
  session 3i): when the same ssh command contains both `pkill -f <pattern>` and a start
  command whose text contains the pattern, the wrapper's own cmdline matches → ssh dies
  silently, the start never happens, logs look stale. Fix: bracketed patterns
  (`[g]st_rtx_rtp_receiver`), pattern text present ONLY in the pkill call, kill and start in
  SEPARATE ssh calls, or PID-file kill. SOURCE: observed failures (sender/receiver/mini_stun
  starts) + ps forensics. CONFIDENCE: VERIFIED.

- FACT: **DECISION 026 remote access INSTALLED + VERIFIED on BOTH machines** (2026-08-16 lab, session
  3b): RTX systemd unit `mcqueen-rtx-ssh-tunnel` (active+enabled) + Jetson unit `mcqueen-jetson-ssh-tunnel`
  (active+enabled), both `cloudflared tunnel --url tcp://localhost:22 --no-autoupdate --logfile …`,
  Restart=always. End-to-end from laptop through `cloudflared access tcp` proxies (RTX :2222, Jetson
  :2223) → SSH landed on `omen` (x86_64) and `ubuntu` (aarch64). URLs (random per restart): RTX
  `specification-plays-fridge-person.trycloudflare.com`, Jetson `customized-lauren-councils-total.trycloudflare.com`
  — saved local-only `~/mcqueen-remote/rtx.url` + `jetson.url`. Laptop client `~/mcqueen-remote/cloudflared`
  v2026.8.2 (linux-amd64); Jetson binary `/var/tmp/mcqueen-sravjti/cloudflared` v2026.8.2 (arm64).
  SOURCE: live SSH evidence + unit files + log greps. CONFIDENCE: VERIFIED.
- FACT: **Jetson SSH password = [REDACTED — user-known; state files never store credentials]** (2026-08-16; user-corrected — `sra@vjti` and `ubuntu` user
  both rejected). Jetson joined `Delta_Virus_Lab` Wi-Fi → wlan0 192.168.0.112/24 (same LAN as RTX
  192.168.0.132), internet VERIFIED (google 200). SOURCE: live session. CONFIDENCE: VERIFIED.
- FACT: **RTX network identity (2026-08-16 session 3g)**: the RTX's active Wi-Fi SSID is
  `SRA_Upper` (NOT Delta_Virus_Lab — that is the JETSON's SSID). RTX also has ethernet enp3s0
  connected; the lab one-liner proof uses `iwgetid -r` on both sides. Laptop home SSID: `Kartik`.
  SOURCE: live `iwgetid`/`nmcli` output over the tunnel. CONFIDENCE: VERIFIED.
- FACT: **Jetson dropped off the lab network (incident, 2026-08-16 session 3g)**: after being
  VERIFIED reachable from home (~22:45), the Jetson left the network — tunnel URL stopped resolving
  (access_jetson.log: "no such host"), port 22 closed at 192.168.0.112, full RTX-side LAN port-22
  rescan found no Jetson, 8×30s report-file polls showed no new URL. RTX remained reachable
  throughout (omen, unit active). SOURCE: live DNS/LAN/poll evidence. CONFIDENCE: VERIFIED.
- FACT: **Jetson recovered from home; report-unit silent failure root-caused + hardened** (2026-08-16
  session 3f): Jetson powered on with tunnel UP (new URL `cincinnati-longer-licensed-marcus.trycloudflare.com`,
  wlan0 connected) but boot report oneshot failed silently (URL >150s → exit 1, never retried). Found
  via RTX LAN port-22 scan (`192.168.0.112` open) + SSH hop through the RTX tunnel. Now: report
  scripts dedupe via `.last_report` + 2-min retry timers on BOTH machines (`mcqueen-jetson-url-report.timer`,
  `mcqueen-rtx-url-report.timer` — enabled, active). SSH from home to Jetson VERIFIED (ubuntu aarch64).
  SOURCE: live recovery + timer states. CONFIDENCE: VERIFIED.
- FACT: **RTX reachable from the HOME network — VERIFIED (milestone, 2026-08-16 session 3e)**: from
  home Wi-Fi (laptop + phone only), key-only SSH via cloudflared tunnel (:2222) → `omen`; unit
  `mcqueen-rtx-ssh-tunnel` active; URL stable (`specification-plays-fridge-person.trycloudflare.com`).
  Jetson meanwhile UNREACHABLE as designed (powered off; no new URL in RTX `url-reports.txt` across 6
  polls). SOURCE: live home-network SSH. CONFIDENCE: VERIFIED.
- FACT: **Final remote-access verification ×2, all GREEN** (2026-08-16 session 3d): RTX tunnel
  (:2222, key-only BatchMode SSH) → `omen`, unit active, log URL == `~/mcqueen-remote/rtx.url`; Jetson
  tunnel (:2223) → `ubuntu` aarch64, unit active; RTX `url-reports.txt` holds the CURRENT Jetson URL
  (matches jetson.url). SOURCE: two live rounds of tunnel SSH. CONFIDENCE: VERIFIED.
- FACT: **Re-punch (NEWCAND in-band) NOT implemented in code** (2026-08-16 session 3d): sender
  (`gst_jetson_rtp_wan.py`) + receiver (`gst_rtx_rtp_receiver.py`) exchange candidates ONLY via broker
  (`control_udp_candidate_v2` wss); no NEWCAND/hole-watchdog anywhere in the repo (grep). Validation
  would require implementation first. DECISION 019's broker.py removal stays PENDING (deferred —
  user dropped re-punch for now). SOURCE: repo grep. CONFIDENCE: VERIFIED.
- FACT: **Jetson reboot test PASSED** (2026-08-16 session 3c): `systemctl reboot` → up in ~36 s →
  auto Wi-Fi `Delta_Virus_Lab` → tunnel unit auto-started with a fresh random URL
  (`nil-squad-tournaments-physiology.trycloudflare.com`); old URL died as expected. The
  phone-call home workflow is therefore viable: plug in → boot → auto-tunnel → new URL readable
  on the RTX via the auto-report. SOURCE: live reboot + observations. CONFIDENCE: VERIFIED.
- FACT: **SSH keys installed** (2026-08-16): laptop `~/.ssh/id_ed25519` in RTX + Jetson
  authorized_keys (passwordless login, verified both). Restricted append-only keys
  Jetson→RTX (`mcqueen-jetson-to-rtx`) and RTX→Jetson (`mcqueen-rtx-to-jetson`) power the
  URL-report units (`mcqueen-jetson-url-report`, `mcqueen-rtx-url-report`; report files
  `url-reports.txt` on each machine — both verified). SOURCE: live tests. CONFIDENCE: VERIFIED.

- FACT: **Slide 31 (transport) rewritten per user's transport story** (2026-08-16):
  problem (college Wi-Fi + carrier NAT block inbound) → Tailscale (blocked by the college
  Wi-Fi; checked via status + pings — tunnel never comes up; user-stated) → WebRTC
  (handshake dies at CGNAT, broker relay = latency) → STUN punch direct peer-to-peer UDP
  (ladder 677→478→277 ms) → tune (400 kbps → p50 ~160 ms; control floor 43 ms) → "Where we
  landed: ~275 ms full loop (best ~160 ms)". SOURCE: edit_deck2.py + qa20 pdftotext.
  CONFIDENCE: VERIFIED (Tailscale-blocked detail user-stated).
- FACT: **3rd-biweekly deck v5 = 38 slides, FINAL** (2026-08-16, user re-ordered model
  slides between latency and next-2-weeks, then removed goals-set + goals slides): order =
  1–26 original, 27 title, 28 status, 29 why, 30 loop diagram, 31 transport, 32 metrics,
  33 latency, 34–36 model S1/S2/S3 (chain merged into 36), 37 next-2-weeks, 38 THANK YOU.
  SOURCE: presentation.xml sldIdLst + pdftotext qa18/qa19. CONFIDENCE: VERIFIED.
- FACT: **V2 TENTATIVE DECK exists** (2026-08-16, user request): `~/Desktop/McQueen_v2_tentative.pptx`, 38 slides, same order/geometry/numbers as v1 but toned-down
  copy ("we tried, we learnt" style). v1 `McQueen_ThirdBiweekly.pptx` unchanged. Build:
  /tmp/opencode/edit_deck2_v2.py. Rendered qa21. CONFIDENCE: VERIFIED.
- FACT: **V2 simplified further** (2026-08-16): pipeline slide = loop diagram ONLY (caption
  + 4 bullets removed, recentered); outro rows punchy one-liners; status bottom bar single
  line. qa22. CONFIDENCE: VERIFIED.
- FACT: **V2 WAN slides simplified more** (2026-08-16): transport/latency/metrics lines
  plain + short (jargon-free); loop diagram slide untouched. qa23. CONFIDENCE: VERIFIED.
- FACT: **V2 slides 31+32 heavy-simplified** (2026-08-16): transport = 4 rows (problem /
  tried-Tailscale+WebRTC merged / STUN punch fix / tune) + landing; metrics = 4 cards 2×2
  (~275 ms, 43 ms, <10 ms, 99.5%). qa24. Full-deck audit: no numeric discrepancies. 
  CONFIDENCE: VERIFIED.
- FACT: **V2 audit items 1–5 done** (2026-08-16, user approved): metrics bottom bar
  removed; latency slide = Diagnosed+Planned only ("real-data training"); "rehearsal
  policy" → "offline test policy" on slides 28/36; script_third_biweekly.md aligned to v2.
  qa25. CONFIDENCE: VERIFIED.
- FACT: **V2 slide 33 = 4-row middle ground** (2026-08-16, user: "too much" after the 2-row
  version): Worked/Didn't/Diagnosed/Planned, short lines, all single-line (qa26).
  Supersedes the Diagnosed+Planned-only variant. CONFIDENCE: VERIFIED.
- FACT: **GitHub purged of audit/error/evidence/agent-state** (2026-08-16, user-authorized,
  commit bd79d4c on jetson-nano): repo = 133 tracked files, all reproducible-project
  content (follow-up purge e64e98a removed docs/NEXT_LAB_RUNBOOK.md and fixed README
  transport direction to the finalized STUN-punch/UDP design). Purged files live on disk only (gitignored) and in history (tag
  pre-purge-2026-08-16 pushed). .mcqueen/ is now LOCAL-ONLY — state files no longer
  versioned anywhere. CONFIDENCE: VERIFIED (ls-tree grep = 0 matches).
- FACT: **Purged local copies verified byte-identical to tag** (2026-08-16): 11 purged docs
  + all 113 docs/evidence/ files match pre-purge-2026-08-16 content exactly; extra raw
  5g/ab run logs on disk are newer local evidence (not in tag — fine).
  CONFIDENCE: VERIFIED.

# >>> 2026-08-16 (session 3a, HOME) — openpilot direction facts <<<

- FACT: **Openpilot supercombo is THE model (DECISION 027, user mandate 2026-08-16)** — complete pipeline
  (vision encoder + temporal hydra) FROZEN, ONLY the final action layer retrained on McQueen data; PPGeo
  ResNet-34 + Drive-JEPA ViT DROPPED. SOURCE: user mandate + DECISIONS.md 027. DATE: 2026-08-16.
  CONFIDENCE: VERIFIED (decision).
- FACT: Repo `models/` contains the openpilot code (commit `536f2d5`, on origin, added by medhansh2808):
  `action_adapter.py` (FrozenActionModel: supercombo ONNX subgraph → onnx2pytorch; frozen trunk;
  re-initialized trainable 4-dim action head matched BY VALUE from onnx initializers; inputs
  img/big_img 6×128×256 packed YUV → stacked (1,12,128,256) uint8, desire_pulse (1,25,8),
  traffic_convention (1,2), action_t (1,2), features_buffer (1,24,512); outputs action (1,4),
  hidden_state (1,512), plan_positions (1,33,3)), `extract_action_subgraph.py` (874 → subgraph via
  `onnx.utils.extract_model`), `train_frozen_action.py` (MSE on steer/throttle via
  `action_to_command_torch`, v_ego=0.0, dead-reckon diagnostic only). SOURCE: repo read. DATE: 2026-08-16.
  CONFIDENCE: VERIFIED (file presence + code read); **RUNTIME UNVERIFIED — never executed anywhere (no
  onnx file, no conversion, no training, no inference evidence)**.
- FACT: supercombo.onnx is NOT on the laptop (Downloads/Desktop/Documents/repo/context searched — 0 hits);
  `*.onnx` is gitignored (.gitignore:55). Fetch plan: comma.ai public release at the lab; URL + SHA-256
  documented in the repo before use. SOURCE: find/grep 2026-08-16. CONFIDENCE: VERIFIED.
- FACT: PPGeo checkpoint (`~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth`, 87.3 MB) + rehearsal tiny
  ckpt (`/home/junior/mcqueen_run/rehearsal_temporal.pt` on RTX) stay on disk but are DEAD references
  (DECISION 027); `MCQUEEN_PPGEO_CKPT` convention superseded by `MCQUEEN_SUPERCOMBO_ONNX`.
  SOURCE: DECISION 027. DATE: 2026-08-16. CONFIDENCE: VERIFIED (decision).
# VERIFIED_FACTS.md — McQueen verified facts

Only facts supported by repository evidence or explicitly recorded verified project docs.
Format: FACT | SOURCE | DATE/COMMIT | CONFIDENCE

---

## Hardware-verified (2026-08-15 lab — session 2r)
- FACT: Jio 5G full-loop test (session 2s): sender ran continuously through an outside walk on a
  power bank (resilient autostart wrapper, 0 restarts, 0 stall-kills); RTX received 49,369 frames,
  fps 20.6, assoc 95.3%, ctrl_sent 46,094. **Loop p50 did NOT improve**: best ~223-224 ms at the
  desk on stable 4G; 5G++ spot window ~231-237 ms (≈ stable 4G); cumulative end 257.7 ms; p95
  worsened to ~1239 ms from 5G↔5G++↔4G mode-shifting. **5G++ ≈ 4G median, worse tail — <100 ms
  not achieved via 5G on this phone.** RTT ~50 ms either way → queueing across the path is the wall.
  SOURCE: docs/evidence/2026-08-15/5g/ (sender.log, receiver.log, REPORT.md). DATE: 2026-08-15.
  CONFIDENCE: VERIFIED (hardware, live).
- FACT: Jetson `/tmp` is tmpfs — wiped on reboot (the first autostart wrapper in `/tmp` vanished
  after the power-swap reboot; cron fired into a missing file). Fix: autostart moved to
  `/home/sravjti/mcqueen_5g/` (persists). ALSO: `mcqueen-edge.service` (GPIO app) holds
  `/dev/video0` at boot → any sender must start after edge is stopped (or edge must not grab the
  camera). ALSO: unanchored `pkill -f` inside a cleanup ssh kills the cleanup shell itself
  (F7-class) — use precise PID kills.
  SOURCE: 2026-08-15 lab debugging. CONFIDENCE: VERIFIED.
- FACT: Rehearsal temporal policy TRAINED on RTX CPU (neighbor GPU job untouched): 20 epochs,
  tiny backbone, batch 16, best_val 3.02 → `/home/junior/mcqueen_run/rehearsal_temporal.pt`
  (36 MB; ckpt keys: model_state_dict/backbone=tiny/config/action_names [servo_angle_deg,
  motor_pwm]/stats/history=6/image_size=224/epochs/seed/train_loss/val_loss).
  SOURCE: smoke_train_batch.py PASS (630 samples/6 eps, forward (8,2)); train run + ckpt key
  verification on RTX. DATE: 2026-08-15. CONFIDENCE: VERIFIED (hardware).
- FACT: Real-ckpt inference chain verified on RTX: test_checkpoint_inference.py 10/10,
  test_inference_rtx.py 18/18; `inference_rtx.py --checkpoint --device cpu` infer avg
  6.59 ms/frame → servo=89.0, pwm=4 (near-center). CUDA single-frame measured 444.75 ms
  while GPU busy (path proven, not fast).
  SOURCE: test + inference output on RTX. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: KACHOW APK built from source: gradle 9.4.1 + JDK 17 `assembleDebug` SUCCESS (27 s) →
  `apps/android/KachowV8/app/build/outputs/apk/debug/app-debug.apk`. Install HELD per user.
  SOURCE: gradle build output. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: Full WAN loop (Jetson hotspot → punched UDP → RTX → control return) VERIFIED LIVE:
  sender `CTRL_RX n=960`, LAT_p50=276.5 ms / LAT_p95=486.7 ms @300 kbps; receiver
  RTP_RX pkts=4530, frames_rx=1072, fps 18.3, assoc 941/1019 (~94%), infer_avg 0.12 ms.
  SOURCE: docs/evidence/2026-08-15/ (REPORT.md + ab/); sender/receiver logs. DATE:
  2026-08-15. CONFIDENCE: VERIFIED (hardware, live).
- FACT: The WAN path needs NO port-forward: receiver binds ephemeral port + STUN punch;
  campus NAT endpoint-independent. Observed public endpoints: receiver
  14.139.108.62:49995 → :41820 → :53591 (fresh per run), Jetson 152.59.109.96:59856;
  media/control = direct peer-to-peer UDP (achieved=422 kbps @400 setting, peer in logs).
  Port-forward theory in the 2026-08-15 docs was RETRACTED after evidence.
  SOURCE: ERROR_LOG_2026-08-15.md entry A + run logs. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: 2026-08-15 full-loop blocker was a DEAD cloudflared tunnel (log `Tunnel server
  stopped`) + STALE URL file (`unfortunately-wrestling-kim-traveller.trycloudflare.com`)
  — F8-class. Fixed: fresh tunnel `https://carlo-booth-austin-pics.trycloudflare.com`
  (PID 759025, URL file refreshed) → signaling verified from Jetson (`{"ok": true...}`).
  cloudflared = startup broker ONLY; never on the media path.
  SOURCE: ERROR_LOG_2026-08-15.md entry A. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: Bitrate A/B 150/300/400 kbps ×2 + manual 400 rerun (6th scripted run: transient
  websocket 530 on signaling): ctrl_rx in EVERY data run; loop p50 stable 270–280 ms across
  bitrates; fps 18–22; assoc ~94–96%; 150_1 loss 2.9% / assoc 4.3% (other runs: snapshot
  skew artifact — receiver counts continuously vs sender meta lag; recorded, not hidden).
  SOURCE: docs/evidence/2026-08-15/ab/{summary.txt,run_*/logs}. DATE: 2026-08-15.
  CONFIDENCE: VERIFIED (with artifact noted).
- FACT: A/B script process management: `pkill -f <scriptname>` SELF-MATCHES even with the
  bracket trick when the command line also starts the script (the literal name is in the
  nohup line) — the shell kills itself. F7-safe solution = PID files
  (`kill $(cat *.pid)` + `kill -0` checks). 3 launch failures diagnosed, all fixed,
  relaunch verified (RECEIVER_ALIVE + PUBLIC printed).
  SOURCE: ERROR_LOG_2026-08-15.md entry D. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: WAN ping Jetson(hotspot)→14.139.108.62: min 45.4 / avg 53.8 / max 62.3 ms (0% loss);
  LAN RTT probe laptop→RTX 192.168.0.132:5955 10/10, avg 3.36 ms. Probe tool is Python
  3.6-safe (Jetson) via `_mono_ns()` = int(time.monotonic()*1e9).
  SOURCE: 2026-08-15 lab runs + AUDIT sections 7-8. CONFIDENCE: VERIFIED.
- FACT: `run_rtp_wan_test.sh` (sacred) UNTOUCHED 2026-08-15 (git diff empty for it); only
  new scripts were edited (run_bitrate_ab.sh, measure_true_path_rtt.py) per care protocol.
  SOURCE: git diff --stat. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: Jetson `mcqueen-edge.service` restored ACTIVE at session end (was stopped for
  pipeline testing; `sudo -S` with transient helper). A/B/manual procs all stopped.
  SOURCE: systemctl is-active. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: Neighbor GPU job at session end: `train.py` PID 744309 (`~/grpo-gsm8k-output`,
  20.3 GB VRAM, 82% util) — NOT McQueen's, untouched (DECISION 014). ViReL PID 575347 gone.
  SOURCE: nvidia-smi/ps on RTX. DATE: 2026-08-15. CONFIDENCE: VERIFIED.

## Git / repository
- FACT: Repo root is `/home/kartik/McQueenWork/McQueen`; remote is `https://github.com/medhansh2808/McQueen.git`.
  SOURCE: `git remote -v` (run 2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Branch `jetson-nano`, HEAD `5cc716cfc1e9598f0403b82a859201946cd861d4`; local == origin/jetson-nano.
  SOURCE: `git rev-parse HEAD` + `git status` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Worktree clean; only untracked item is local folder `context stuff for understanding the mcqueen project/` (not in git).
  SOURCE: `git status --short` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: `.gitignore` excludes `data/`, `*.pt/*.pth/*.onnx`, `wandb/`, `checkpoints/`, `outputs/` etc.; it does NOT exclude `.mcqueen/` or `AGENTS.md`.
  SOURCE: `.gitignore` (read 2026-08-13). CONFIDENCE: VERIFIED.

## Hardware-verified (2026-08-11 lab)
- FACT: Real Jetson ↔ real RTX 4090 direct-WAN UDP control return: 60/60 ACKs; control RTT min 29.4 ms, p50 43.1 ms, p95 70.4 ms, max 75.7 ms. Jetson side dry-run (zero GPIO writes).
  SOURCE: docs/HARDWARE_MILESTONES_2026-08-11.md; docs/evidence/2026-08-11-direct-wan-control.txt. DATE: 2026-08-11. CONFIDENCE: VERIFIED (documented).
- FACT: Real Lenovo camera → Jetson hardware H.264 → WebRTC → RTX decode/appsink → CUDA/PyTorch dummy action proven, but ONLY on the temporary local lab route (not separate-WAN).
  SOURCE: docs/HARDWARE_MILESTONES_2026-08-11.md. DATE: 2026-08-11. CONFIDENCE: VERIFIED (documented, with boundary).
- FACT: Real KACHOW phone → real Jetson command parsing proven (forward/reverse + steering extremes) using MockDriveBackend / no-GPIO path.
  SOURCE: docs/HARDWARE_MILESTONES_2026-08-11.md. DATE: 2026-08-11. CONFIDENCE: VERIFIED (documented, with boundary).

## Home-validated software (2026-08-12)
- FACT: Dataset-v2 schema + sequence rules, legacy v1 compat, six-frame temporal indexing with neutral `[90 deg, 0 PWM]` padding, no target-action leakage, benchmark-v2 bookkeeping validated on laptop.
  SOURCE: docs/HOME_VALIDATED_2026-08-12.md. DATE: 2026-08-12. CONFIDENCE: VERIFIED (documented).
- FACT: Backbone-agnostic PyTorch temporal core (Transformer forward + one training step) validated on home laptop GPU (`mcqueen-laptop` env); input `[frames, wheels, previous_actions]`, output `[servo, PWM]`.
  SOURCE: docs/HOME_VALIDATED_2026-08-12.md. DATE: 2026-08-12. CONFIDENCE: VERIFIED (documented).
- FACT: Home LeRobot installation used to validate committed converter on synthetic raw spools (v2 + v1 convert, reload, wheel fields).
  SOURCE: docs/HOME_VALIDATED_2026-08-12.md. DATE: 2026-08-12. CONFIDENCE: VERIFIED (documented).

## Realtime contract / safety
- FACT: Benchmark-v2 stages: SIGNALING_P2P, VIDEO_CONNECTED, VIDEO_FRAMES, FRAME_TIMESTAMP, EXACT_FRAME_MATCH, RTX_INFERENCE, DIRECT_UDP, CONTROL_RETURN, SAFETY_GATE, FULL_LOOP_LATENCY. Exact frame association via Jetson `frame_id` + `capture_mono_ns` echoed by prediction; latency = `receive_mono_ns − capture_mono_ns` on Jetson monotonic clock; newest-frame-wins.
  SOURCE: docs/full_loop_benchmark_v2.md, docs/REALTIME_INFERENCE_V1.md. DATE: 2026-08-12. CONFIDENCE: VERIFIED.
- FACT: Safety contract: steering 45–115 deg center 90; forward cap +100 PWM; reverse cap −70; prediction timeout 250 ms; stale → zero PWM, center steering, cancel AUTO; remote model never grants authority (phone authorizes AUTO).
  SOURCE: mcqueen_ml/deployment/safety.py + docs/REALTIME_INFERENCE_V1.md (read 2026-08-13). CONFIDENCE: VERIFIED.
- FACT: NO authoritative separate-WAN camera-capture → RTX inference → returned-command full-loop latency result exists yet.
  SOURCE: docs/REALTIME_INFERENCE_V1.md "Not yet measured". CONFIDENCE: VERIFIED.

## Architecture / roles
- FACT: Phone (KACHOW) = teleop + takeover/E-stop + AUTO authorization; Jetson = capture/encode/teleop/record/safety/actuators; RTX 4090 = decode/inference/training; laptop = dev only, NOT part of runtime.
  SOURCE: docs/PROJECT_STATUS_2026-08-12.md section D. CONFIDENCE: VERIFIED.
- FACT: Intended policy: 6 RGB obs + previous actions + wheel state → visual encoder → temporal Transformer → MLP → [servo_angle_deg, signed_motor_pwm]. Planned backbones: PPGeo ResNet-34, then Drive-JEPA ViT. Neither adapter runtime-proven.
  SOURCE: docs/PROJECT_STATUS_2026-08-12.md section C; docs/BACKBONE_INTEGRATION_PLAN.md. CONFIDENCE: VERIFIED.
- FACT: Remote WAN pipeline code (broker.py on RTX at 127.0.0.1:8765, cloudflared Quick Tunnel, gst sender/receiver) exists only in `~/Downloads/` bundles and on the RTX — NOT committed to the repo.
  SOURCE: inspection of ~/Downloads/mcqueen_wan_direct_p2p/ + run_direct_wan_test.sh (2026-08-13). CONFIDENCE: VERIFIED.

## Open risk flags (verified locally)
- FACT: `tests/test_jetson_http_server.py` previously observed FAILING (asserts old "OAK-D/WebRTC" HTML + `session-` prefix no longer produced by current http_server.py). Re-checked in Phase 11.
  SOURCE: test run (2026-08-13). CONFIDENCE: PARTIALLY VERIFIED (re-run this session).
- FACT: `tools/preflight/laptop_lab_preflight.sh` previously observed checking the OLD steering mapping (`-1000→45°`, `1000→115°`) vs current code (`-1000→115°`, `1000→45°`). Re-check in lab.
  SOURCE: file inspection + tests/test_jetson_steering_mapping.py (2026-08-13). CONFIDENCE: PARTIALLY VERIFIED.
- FACT: Earlier `motor_pwm=0` claim: analysis of `data/jetson_recordings/session_20260810_191351` showed 130/138 frames had zero throttle/steering input; non-zero frames' PWM math is correct (throttle×255/1000). Blocker status UNVERIFIED until live phone→Jetson probe.
  SOURCE: raw recording analysis (2026-08-13). CONFIDENCE: PARTIALLY VERIFIED.

## 2026-08-13 lab-exit pull (VERIFIED from live machines)
- FACT: Jetson reachable at `sravjti@192.168.55.1` (USB), hostname `ubuntu`, kernel 4.9.253-tegra; RTX reachable at `junior@192.168.0.132` (wired) and `192.168.0.179` (wifi), hostname `omen`.
  SOURCE: ssh + ping (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: At pull time: Jetson `mcqueen-edge.service` inactive + enabled; Lenovo camera present at `/dev/v4l/by-id/usb-Sonix_...Lenovo_FHD_Webcam...video-index0`; Jetson clone `~/McQueen` at commit `61a3c91` (untracked tools/realtime/kachow_probe.py).
  SOURCE: ssh inspection (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: At pull time: RTX broker.py RUNNING (`http://127.0.0.1:8765/health` = ok) and cloudflared RUNNING with URL `https://disposition-cabinets-mariah-glad.trycloudflare.com`; RTX clone `/var/tmp/mcqueen-junior/McQueen` at `8259460`.
  SOURCE: ssh inspection (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Laptop copies of `tools/realtime/gst_jetson_rtp_wan.py` + `gst_rtx_rtp_receiver.py` are the NEWEST sender/receiver; deployed Jetson sender (17:25, v4l2src/NVENC-era) is older; deployed RTX receiver md5 = laptop md5 `b4cf4ee...`.
  SOURCE: md5 + diff of pulled snapshots (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: The 584-line cv2+x264 sender had bug `if self.sent_pkts % 30 < n:` (NameError, `n` undefined); probe-error log = 22,209 identical NameErrors; exception preceded rtp_ts increment so rtp_ts stayed 0. Fixed to `% 30 == 0` on laptop copy; py_compile + association unit test pass. Not yet redeployed.
  SOURCE: `docs/evidence/2026-08-13-lab-pull/` + `docs/evidence/2026-08-13-wan-pipeline-errors.txt` #20 (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: RTX receiver lab16 run failed `ModuleNotFoundError: websocket` — must be started with `/var/tmp/mcqueen-junior/gst-webrtc-venv/bin/python`, not system python.
  SOURCE: pulled log `gst_rtx_rtp_receiver_lab16.log` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: RTX lab15 run (4.6MB, 4m27s): receiver PLAYING OK, RTP_RX flowing, but rtph264depay stuck "waiting for start" (FU-A S=1/E=0 + AUD NAL 9) — old-NVENC-sender artifact; new sender drops AUD + manual packetization.
  SOURCE: pulled log `gst_rtx_rtp_receiver_lab15.log` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Full machine snapshots + all 2026-08-13 lab receiver logs + recordings stored locally: `docs/evidence/2026-08-13-lab-pull/` (manifest README.md) and `data/lab_pull_20260813/` (gitignored).
  SOURCE: pull session (2026-08-13). CONFIDENCE: VERIFIED.

## 2026-08-13 home debug of the WAN video path
- FACT: lab13/14/15 receiver `frames_rx` counters counted UDP marker bits, NOT decoded
  frames; decoded frames were ZERO (no `[RTX-GST] VIDEO` line in any lab receiver log).
  Old deployed sender set the RTP marker bit on EVERY packet ((96<<1) PT-byte bug).
  SOURCE: pulled logs gst_rtx_rtp_receiver_lab13/14/15.log (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: lab15 "waiting for start" = FU-A fragments never completing + AUD NALs (type 9)
  flushing rtph264depay mid-fragment. New sender drops type-9 NALs + completes FU-A.
  SOURCE: lab15 log depay DEBUG lines (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: #19 stall was the NVENC-era chain (deployed 411-line sender log ends at
  `NVMEDIA: NVENC` init); new sender uses cv2 capture + x264 SW — chain removed by design.
  SOURCE: gst_jetson_rtp_wan_lab.log + sender code comments + isolated appsrc test (2026-08-13).
  CONFIDENCE: VERIFIED (code-level; hardware proof pending).
- FACT: The new (584-line) sender's cv2→appsrc→x264→probe chain ALREADY ran continuously
  on the Jetson for ~12 min at 19:20 (22,209 probe firings = 22,209 encoded AUs); its only
  failure was F1 NameError freezing rtp_ts. So cv2+x264 does NOT stall on the Jetson.
  SOURCE: mcq_sender_probe_errors.log (22,209 lines, 2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Offline unit test tools/realtime/test_rtp_packetization.py — 6/6 PASS (AUD drop,
  marker-only-on-last, FU-A S/E, per-frame ts 0/3000/6000, one-META-per-frame, non-VCL
  hold, 100-frame F1 no-crash guard); test_rtp_association.py PASS; sender+receiver
  py_compile OK; run_rtp_wan_test.sh bash -n OK; AST undefined-name scan clean.
  SOURCE: runs (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Sender refactored (probe → _on_rtp_probe → handle_au → send_au) with NEW non-VCL
  (SPS/PPS/SEI) hold-and-prepend hardening; run script resets probe-error log + reports
  probe-error count / last rtp_ts / last frames_rx in RESULT.
  SOURCE: tools/realtime/ (2026-08-13, uncommitted). CONFIDENCE: VERIFIED.

## Environment
- FACT: Laptop Python 3.10.12 verified (`python3 --version`). Home env `mcqueen-laptop` used for temporal-core tests.
  SOURCE: command run (2026-08-13). CONFIDENCE: VERIFIED.

## 2026-08-14 home prep (H1–H5)
- FACT: `mcqueen-laptop` env = Python 3.12.13, torch 2.11.0+cu128, CUDA available; gdown
  installed there. `test_inference_rtx.py` 18/18 PASS (CPU+CUDA); unittest 8 OK (temporal 3 +
  backbones 5); system-python pytest 18 passed with the two torch collectors ignored
  (test_temporal_policy_v2.py, test_backbones_ppgeo_resnet34.py — established convention).
  SOURCE: test runs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: `tools/realtime/broker.py` is now repo-managed (copied from
  `docs/evidence/2026-08-13-lab-pull/rtx/broker.py`); run_rtp_wan_test.sh step 1b scp's it
  every run and exits 10/11 with download hints if venv python / cloudflared missing.
  SOURCE: file + `bash -n` + live smoke (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: `tools/realtime/inference_rtx.py` implements newest-frame-wins 6-frame buffer, exact
  frame_id + capture_mono_ns echo, safety clamps (servo 45–115, pwm −70..100), numpy-only
  I420 decode; `_load_policy_classes` raises RuntimeError instead of silently substituting
  architectures. Receiver `gst_rtx_rtp_receiver.py` gained `--inference dummy|real`.
  SOURCE: code + 18/18 tests (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: PPGeo "Visual Encoder (ResNet-34)" released checkpoint (Google Drive
  `1GAeLgT3Bd_koN9bRPDU1ksMpMlWfGXbE`, BaiduYun code `itqi`) is a PLAIN torchvision resnet34
  state dict: `{"state_dict": OrderedDict}` with 218 standard keys (conv1/bn1/layer1..4/fc,
  no prefix). PPGeo model.py wraps it as `ResnetEncoder(34, num_input_images=1)` with
  normalize=True (ImageNet mean/std) → layer4 → 512-dim pooled features.
  SOURCE: torch.load inspection + repo read (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Checkpoint stored OUTSIDE repo at `~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth`
  (87.3 MB); `mcqueen_ml/training/backbones.py` PPGeoResNet34Backbone (output_dim 512) raises
  RuntimeError when missing — no silent fallback (DECISION 015). Tests 5/5 PASS incl. strict
  torchvision-equivalence; full TemporalDrivingPolicy end-to-end OK.
  SOURCE: tests + policy run (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: `kachow_probe.py` reports per-packet `pwm` via the recorder's exact `throttle_to_pwm`
  (clamp ×255/1000, motor_enabled gating) + LABEL_PATH stats; exit 0 = control + PWM path
  proven, exit 3 = control OK but PWM unproven. PWM math re-verified: 1000→255, −1000→−255,
  500→128, disabled→0.
  SOURCE: code + assertion checks (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Evidence automation exists: `tools/realtime/capture_evidence.sh` (files milestone logs,
  `LOGS FILED → docs/evidence/<date>/<milestone>/` banner, exit 2 on missing/empty),
  `docs/evidence/MILESTONE_TEMPLATE.md` (n/p50/p95 per benchmark-v2 stage),
  `tools/realtime/process_recording.sh` (validate_spool → convert_spool → file evidence;
  failed validation BLOCKS conversion). Smoke-tested live.
  SOURCE: runs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Standalone inference CLI on the LAPTOP GPU: warmup 172 ms, steady ~3–4 ms/forward at
  640×480 — a laptop number, NOT the 4090; no RTX performance claim made.
  SOURCE: CLI smoke (2026-08-14). CONFIDENCE: VERIFIED (with boundary).
- FACT: ~~Git state 2026-08-14 end: branch `jetson-nano`, HEAD == origin == `6632913`; prep
  work uncommitted by DECISION 013~~ **(SUPERSEDED 2026-08-14 evening by FACT 86: first
  hardware-verified commit `8f35564` pushed; the uncommitted list below is now committed):**
  modified: AGENTS.md, DECISIONS.md, model_config_v2.py,
  gst_jetson_rtp_wan.py, gst_rtx_rtp_receiver.py, kachow_probe.py, run_rtp_wan_test.sh,
  AUDIT doc; untracked: broker.py, inference_rtx.py, test_inference_rtx.py, backbones.py,
  test_backbones_ppgeo_resnet34.py, capture_evidence.sh, process_recording.sh,
  MILESTONE_TEMPLATE.md, HOME_DEBUG doc, test_rtp_packetization.py, context folder.
  SOURCE: `git status` (2026-08-14). CONFIDENCE: VERIFIED (historical snapshot, superseded).
- FACT: ~~On 2026-08-14 the user pushed `57561db` "actaul audit" DIRECTLY to GitHub (web UI,
  commit by kt-fr) — origin/jetson-nano is 1 commit AHEAD of local `6632913`; it only edits
  `docs/AUDIT_2026-08-13.md` (removes the timeline table, 1 insertion / 14 deletions); the
  local working copy's own AUDIT edit (timeline paragraph + "Jetson sender" typo fix)
  differed — reconcile at the first hardware-verified commit~~ **(SUPERSEDED 2026-08-14
  evening: absorbed via `git reset --soft origin/jetson-nano`, local AUDIT version KEPT,
  everything pushed in `8f35564`; repo sync 0/0).

## 2026-08-14 LAB session (VERIFIED from live machines)
- FACT: Jetson USB SSH ok; camera at
  `/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0`;
  hotspot ON (wlan0 10.147.40.55, Android range) with internet; `mcqueen-edge.service` was
  active and was stopped (sudo password required, `sudo -n` fails, tty_tickets).
  SOURCE: ssh checks (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: RTX `omen` reachable at wired 192.168.0.132 (wifi .179 unreachable); i9-13900K 24C/32T,
  62 GB RAM (~50 avail); venv gst-webrtc-venv = torch 2.6.0+cu124; BOTH avdec_h264 (libav,
  rank primary 256) and nvcodec (nvh264dec etc.) present. Broker healthy at 127.0.0.1:8765.
  SOURCE: ssh + gst-inspect + free + lscpu (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: RTX GPU 100% busy (443 W, 18.6 GB VRAM) with `python train.py` run as user `junior`,
  cwd `/home/junior/ViReL/Tasks/vlmgrpo`, started 15:57:43, parent interactive `-bash`. Dir
  contents (train.py, reward.py, evaluation.py, config.py, local_robo2vlm.py, unsloth_compiled_cache,
  wandb/, outputs_sft_coldstart/, spatialladder_data/) = VLM-GRPO vision-language RL training.
  NOT McQueen's (outside /var/tmp/mcqueen-junior, no mcqueen refs) → UNTOUCHABLE per DECISION 014.
  SOURCE: read-only /proc + ps + ls (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: L0 run (run_rtp_wan_test.sh, 4th attempt): SIGNALING_P2P READY Jetson pub
  152.58.42.132:57379 ↔ RTX pub 14.139.108.62:48699; sender SENT pkts + rtp_ts advancing
  (F1 fix live); RTX frames_rx=16 assoc_ok=1 assoc_miss=0 ctrl_sent=1 infer_avg=169.75ms;
  0 probe errors; 0 GST errors. Receiver then stalled at pkts=210 (of 12,060+ sent): GPU
  starved NVDEC ~1 fps → appsrc backpressure → UDP thread blocked → socket Recv-Q 216,192 B
  → kernel drops. NOT a transport bug.
  SOURCE: full Jetson + RTX logs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Receiver `gst_rtx_rtp_receiver.py` udp_loop gates RTP→appsrc on
  `elif self.cur_meta is not None:` — META loss drops delivered RTP (BUG F10, approved fix:
  decouple; always push RTP). Pipeline has NO rtpjitterbuffer (F11, approved: bounded ≤50 ms
  drop-on-late no-rtx). Sender hardcodes `x264enc tune=zerolatency bitrate=2500
  speed-preset=ultrafast` (F12, approved: bitrate from measurement).
  SOURCE: code read (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Jetson logs CTRL_RX only every 10th control (`ctrl_count % 10 == 0`); with 1 control
  received nothing prints — control return path INCONCLUSIVE (needs sustained run, >10 controls).
  SOURCE: sender code + run evidence (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: run_rtp_wan_test.sh hardened on 2026-08-14 (uncommitted): F7 anchored pkill/pgrep
  patterns (plain `pkill -f <script>` self-matched the remote shell via the nohup line text);
  F8 stale cloudflared.url refresh (2026-08-13 URL dead; live tunnel re-registered a new URL);
  F9 sudo bounded/conditional (never hang).
  SOURCE: bash -n + SURVIVED tests + run outputs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: ~~Origin/jetson-nano is 1 commit AHEAD of local (`57561db` "actaul audit", kt-fr web
  push 2026-08-14 00:17, only docs/AUDIT_2026-08-13.md: removed timeline table). Local
  working copy has its own uncommitted AUDIT edit — reconcile at first hardware-verified
  commit~~ **(SUPERSEDED 2026-08-14 evening: reconciled + pushed in `8f35564`; sync 0/0).

## 2026-08-14 LAB session 2 — fixes implemented on reset baseline, FULL LOOP measured (VERIFIED)
- FACT: Per user order the sender/receiver/run-script were reset to GitHub HEAD (`6632913`);
  ONLY these changes then applied: Fix 1 (receiver ALWAYS pushes RTP to appsrc, never gates on
  `cur_meta`; lost META → assoc_miss, never a delivery block), Fix 2 (rtpjitterbuffer
  latency=50 drop-on-latency=true between appsrc and rtph264depay), Fix 3 (sender
  `--bitrate-kbps` + achieved-kbps print), CPU decode (avdec_h264) + CPU dummy inference
  (device=cpu), rolling FULL_LOOP_LATENCY print every 10 controls. run_rtp_wan_test.sh
  byte-identical to HEAD (git diff empty).
  SOURCE: git diff + code read + py_compile (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: RTX gst-webrtc-venv GStreamer is 1.20.3; rtpjitterbuffer has `drop-on-latency` (False
  default) and NO `drop-on-late` (removed in 1.20 — parse error: "no property drop-on-late in
  element rtpjitterbuffer0" crashed the receiver until switched). `do-retransmission` defaults
  False. `latency` default 200 ms.
  SOURCE: venv python Gst version + list_properties (2026-08-14, live). CONFIDENCE: VERIFIED.
- FACT: Committed run_rtp_wan_test.sh reproduced F7 (plain `pkill -f <script>` self-kills the
  remote shell in steps 6+7 → peers never start; the step-8 "evidence" was STALE morning
  logs) and F9 (Jetson `sudo systemctl stop` fails without a tty / hangs with a tty). F8
  (stale cloudflared.url) did NOT hit because the URL file was refreshed this morning. Bugs
  noted, NOT fixed (user order: fix only the listed bugs; manual start pre-approved).
  SOURCE: full script run + logs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: FULL LOOP on the real WAN (hotspot link, CPU path, GPU free): SIGNALING_P2P ✓, frames
  sustained, EXACT_FRAME_MATCH assoc_ok≈5.7k / assoc_miss≈950 (~14% honest WAN-loss misses;
  Fix 1 delivers RTP through lost META), CPU dummy inference 0.13–0.2 ms, control return
  ctrl_sent↔CTRL_RX n≈1.8k, safety values servo 90 / pwm 0. Bitrate sweep (Fix 3 live,
  achieved 2495/719/380 kbps): 2500 → p50 709 ms/p95 2.5 s; 800 → 408 ms/1.76 s;
  400 → **p50 391 ms / p95 1.67 s / ~14 fps (FINAL)**.
  SOURCE: Jetson + RTX live logs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: ViReL train.py (PID 490867) is GONE from the RTX GPU — nvidia-smi shows 0% util,
  27 MiB VRAM. The full-loop run was fully uncontended; CPU path still used per user approval.
  SOURCE: nvidia-smi (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Broker log documents the Jetson tunnel ws dying (`[BROKER] ws error jetson No PONG
  received after 7.5 seconds` → disconnected): the sender has NO websocket reconnect, so it
  stopped learning candidate updates (stayed on a dead peer mapping after a receiver restart).
  Receiver re-punch on PEER_CANDIDATE change WORKS (verified: receiver logged the new Jetson
  public 152.58.46.184:55369 and re-punched; flow resumed). Robustness gap = sender ws
  reconnect — NOT one of the 3 fixes; noted only.
  SOURCE: broker_lab.log + receiver logs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: test_rtp_packetization.py was adapted to the committed sender API (calls
  `_on_rtp_probe` with a real Gst.Buffer; non-VCL hold test dropped — that prep behavior was
  reset away per user order): 5/5 PASS. test_rtp_association PASS; pytest tests/ + mcqueen_ml/
  (torch collectors ignored) 18 passed; sender/receiver py_compile OK.
  SOURCE: runs (2026-08-14). CONFIDENCE: VERIFIED.

## 2026-08-14 LAB session 2b — user switched phone to a better network; measurement runs (VERIFIED)
- FACT: User connected the phone (Jetson's hotspot) to a better network; the Jetson's public
  IP changed 152.58.29.86 → 152.58.29.56 (new CGNAT mapping confirmed). Same pipeline, same
  config: 30 fps @ 400 kbps FULL_LOOP_LATENCY dropped p50 391 ms → ~160 ms, p95 1.67 s →
  ~380 ms. Bottleneck = the internet link, NOT the pipeline (confirmed).
  SOURCE: live Jetson/RTX logs (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Sender gained `--max-fps` (default 30 = frame_step 1, rtp_ts_step 3000, frame_ns
  33.3 ms = byte-identical original path; max_fps 10 = every 3rd captured frame, rtp_ts_step
  9000, frame_ns 100 ms; skipped frames get NO capture_q/frame_id → META stays 1:1).
  py_compile + packetization 5/5 + pytest 18 passed; 10 fps pacing confirmed live (rtp_ts
  14,724,000 = 1636×9000).
  SOURCE: code + tests + live log (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Measurement run 1 (10 fps @ 150 kbps, 2.5 min): p50 462 ms / p95 679 ms; frames
  sent ≈1,645 vs received ≈1,590 (~96–97%, window overlapped prior stream — approximate);
  META loss ~1%; controls 1,665 sent vs 1,640 received (98.5%); EXACT_FRAME_MATCH 98.9%
  (1,665/1,684).
  SOURCE: live logs (2026-08-14). CONFIDENCE: VERIFIED (arrival approx; clean run = run 2).
- FACT: Measurement run 2 (30 fps @ 150 kbps, 2.5 min, drained baselines): p50 224 ms /
  p95 368 ms; frames sent 5,020 vs received 4,995 (**99.5% arrival**); packets 21,260 sent vs
  21,000 received (1.2% loss); META 5,019 vs 4,987 (**0.6% loss**); controls 4,593 sent vs
  4,600 received (~0% loss); EXACT_FRAME_MATCH 95.0% (4,593/4,835); CPU infer 0.04–0.14 ms;
  achieved 169 kbps incl. ~12% RTP header overhead (x264 bitrate is a ceiling, not a fill;
  static scene entropy low).
  SOURCE: live logs (2026-08-14). CONFIDENCE: VERIFIED (clean windows).
- FACT: FPS ANOMALY: at the same bitrate (150), 10 fps (462 ms) measured WORSE latency than
  30 fps (224 ms). With loss ~0, bandwidth is no longer the constraint; latency is dominated
  by link RTT/jitter + jitter-buffer clock recovery, which behaves differently with sparse
  10 fps traffic. UNCONFIRMED as systematic — needs a repeated pair (link variance possible).
  SOURCE: run 1 vs run 2 logs (2026-08-14). CONFIDENCE: PARTIALLY VERIFIED.
- FACT: On the OLD hotspot, loss was 50–70% (frames), ~13% META, ~70% controls; on the NEW
  network loss is ~0–1.5% across all classes. The jitter buffer (latency=50 drop-on-latency)
  converts link jitter into frame drops when jitter exceeds the 50 ms budget — on the old
  link that was the dominant loss mechanism.
  SOURCE: all session logs (2026-08-14). CONFIDENCE: VERIFIED.

## 2026-08-14 LAB session 2c — approved 4-part plan (cleanup, save test, fps ladder, 25 ms jitter) (VERIFIED)
- FACT: Cleanup DONE on RTX + Jetson (user-approved scope): removed old WAN setup files/tools
  + stale pids + dead webrtc-venv + __pycache__; old LOGS kept per user. KEEPLIST_INTACT
  verified after removal: receiver/broker/cloudflared/sender all alive; ~/McQueen clone +
  mcqueen-edge service files + data + HF cache + inference_rtx.py + mcqueen_ml/ + current
  tools present; nothing non-McQueen touched.
  SOURCE: removal + post-check pgrep/ls (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Receiver gained opt-in `--save-frames <dir>` (default OFF = current behavior
  unchanged): decoded frames JPEG'd + meta.csv (frame_id, capture_mono_ns, recv_mono_ns,
  save_mono_ns) via an async writer thread (bounded queue — disk I/O never blocks the
  control path). Save test (30fps@150, ~3 min): RTX recv→decode→save p50 1.14 ms /
  p95 1.54 ms; 5,277 saved vs 5,270 assoc_ok ≈ 100% with 0 dropped; completeness vs
  received 90.8% (assoc_miss/lost-META frames not saved by design); 161 MB in
  recordings/save_test_201750/.
  SOURCE: receiver code + live stats (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: FPS LADDER + RTT PROBE (same network, 150 kbps cap, Jetson pings 1.1.1.1 every
  second during each run): 10 fps → loop p50 677 ms (link RTT p50 46/p95 73 ms — healthy),
  15 fps → 478 ms, 30 fps → 277 ms. True 20 fps unattainable from a 30 fps camera (30/N
  rates only: 30/15/10). Verdict: sparse-traffic penalty (jitter-buffer clock recovery +
  path/NAT scheduling with one burst per 100 ms) — NOT link variance; 30 fps is the winner.
  Also: the two 15-fps-equivalent runs agreed (478 vs 467 ms) → measurement reproducible.
  Sender `--max-fps` reworked to a time-gate that ONLY applies when throttling (default 30
  = push every camera frame, byte-identical original behavior — regression caught + fixed
  when the gate skipped jittery camera frames at default 30).
  SOURCE: sender/receiver live logs + RTT probe files (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: 25 ms JITTER BUFFER test (`--jitter-ms` flag, default 50 = unchanged; receiver
  restarted on new public port): loop p50 281.9 ms / p95 425.4 ms @ 30fps@150 — statistically
  identical to the 50 ms run (276.8/393) → the jitter buffer is NOT the latency driver;
  ~280 ms is wire/RTT. SAVED n=21,400, 0 dropped, recv2save p50 0.93 ms. Also: sender
  re-pointing to a NEW receiver port WITHOUT a fresh restart does NOT re-establish the NAT
  path (CGHNAT/campus mapping keyed per session) — the fresh-sender restart is required;
  in-place re-pointing left the receiver with 0 RTP until the sender was restarted.
  SOURCE: live logs + recordings/jitter25_204850 (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Absolute capture→save latency was NOT measured (dropped per user): it needs a
  Jetson↔RTX clock offset; `tools/realtime/sync_calib.py` (NTP-style 4-timestamp offset
  over the direct-UDP path, no broker) was written and deployed but not run to completion.
  RTX-side recv→decode→save IS measured (~1 ms). Keep sync_calib.py as untracked tooling.
  SOURCE: session (2026-08-14). CONFIDENCE: PARTIALLY VERIFIED (tool written, unused).
- FACT: CLEANUP ROUND 2 (full sweep, user-approved 2026-08-14): Jetson home reduced to
  Desktop/examples.desktop/McQueen/safety_contract_250ms.py; removed 6 git bundles+tar
  (~50 MB), McQueen_files/, 12 old logs, 4 stale pids, old kachow_probe copy, tailscale+
  websocket install artifacts; RTX removed 15 lab2–16 logs + Aug 11–12 WAN logs +
  gst_rtx_receiver_wan.pid + ~/mcqueen scratch + ~/logs policy_server logs + sync_calib.py
  copies. KEPT manual-punch tools on Jetson /tmp (natprobe.py, punch_peer.py — the
  SSH-orchestrator hole-punch tool for broker removal, rtp_loopback_test.py) + mcq_rtt_*
  evidence. Post-sweep: sender/receiver/broker/cloudflared alive, keep-list intact.
  SOURCE: removal + post-checks (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: `docs/ERROR_LOG_2026-08-14.md` created (all 2026-08-14 lab errors + findings:
  F1/F2/F7/F8/F9/F10/F11/F12, drop-on-late crash, cd mistake, Q11 ws death, NAT re-point
  failure, NVDEC starvation, 10-fps + jitter findings, cleanup-gap note). User-approved to
  include in the next GitHub push (DECISION 013).
  SOURCE: file + user approval (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: Final full-loop run (30 fps @ 150 kbps, 25 ms jitter, new phone network, Jetson
  monotonic clock): FULL_LOOP_LATENCY n≈48.6k p50 287.1 ms / p95 504.0 ms; CONTROL_RETURN
  PROVEN at scale (CTRL_RX n=48,650 — previously inconclusive); EXACT_FRAME_MATCH 52,095 ok
  / 3,287 miss (~94 %); RTX_INFERENCE infer_avg 0.06–0.10 ms (CPU path); VIDEO_FRAMES 57.6k
  sustained @ 25.4 fps; save path recv→save p50 0.96 / p95 1.32 ms, 52,100 saved, 0 dropped.
  SOURCE: `docs/evidence/2026-08-14/wan-loop-measured/` logs + REPORT.md (2026-08-14 21:50).
  CONFIDENCE: VERIFIED (hardware, from logs).
- FACT: Evidence for 2026-08-14 filed on the laptop: `docs/evidence/2026-08-14/wan-loop-measured/`
  (14 files + REPORT.md) via `tools/realtime/capture_evidence.sh`. Deployed
  sender/receiver/inference_rtx/broker on the machines are md5-IDENTICAL to laptop repo
  copies; Jetson clone `tools/realtime/kachow_probe.py` is STALE (Aug 13 copy) — repo
  version must be deployed before the live Q1 probe.
  SOURCE: md5 comparisons + capture_evidence.sh run (2026-08-14 21:47–21:50).
  CONFIDENCE: VERIFIED.
- FACT: ViReL train.py RETURNED on RTX: PID 575347, started 20:17, 90 % GPU util / 20.4 GiB
  VRAM (nvidia-smi + ps, 21:41 check). NOT McQueen's, UNTOUCHABLE (DECISION 014 + user hard
  rule). Plan A (CPU decode/infer) proven GPU-independent — jitter25 run sustained 25.4 fps
  while it ran.
  SOURCE: nvidia-smi/ps over SSH (2026-08-14 21:41). CONFIDENCE: VERIFIED.

## Git / repository (post-sync, 2026-08-13 evening)
- FACT: ALL 2026-08-13 work is COMMITTED and PUSHED: branch `jetson-nano`, local HEAD ==
  origin/jetson-nano == `6698d41` ("Fix stale edge tests, steering preflight, and runbook").
  Includes WAN RTP transport code, full lab-exit evidence pull, agent system, and the
  edge-test/preflight/runbook fixes.
  SOURCE: `git log origin/jetson-nano`, `git status` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Push was user-authorized/intentional (audit answer). DECISION 012: nightly home
  sync of committed work is sanctioned.
  SOURCE: user audit answers (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Only untracked item is `context stuff for understanding the mcqueen project/`
  (reference material per DECISION 008, intentionally not committed).
  SOURCE: `git status --short` (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: F1 fix (`% 30 == 0`) present in committed sender at `tools/realtime/gst_jetson_rtp_wan.py`
  line 414; startup check 35/35 PASS; pytest = 18 passed + 1 env-blocked collector
  (test_temporal_policy_v2.py needs torch in mcqueen-laptop env).
  SOURCE: code_search + startup check + pytest (2026-08-13). CONFIDENCE: VERIFIED.
- FACT: Jetson is Ubuntu 18.04-era with old Python/GStreamer/NVIDIA stacks — conservative dependency policy required.
  SOURCE: AGENTS.md section I (policy) + docs. CONFIDENCE: VERIFIED (policy).

## Inference / model readiness (2026-08-14 evening)
- FACT: NO trained temporal driving policy EXISTS anywhere (laptop scan: only
  `~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth` found via `find -name "*.pt|*.pth"`).
  The PPGeo checkpoint is a visual ENCODER (feature extractor) — it outputs features, NOT
  actuator commands. A policy must be trained (backbone + temporal head) on driving demos.
  SOURCE: `find` over /home/kartik + repo (2026-08-14). CONFIDENCE: VERIFIED.
- FACT: The only driving demos on the laptop are 8 sessions (Aug 9–10) in
  `data/jetson_recordings/` — user verdict: NOT real driving data; no training until a real
  dataset is recorded on real roads. L1 `--inference real` is gated: real dataset → train
  policy → L0 green → user approval.
  SOURCE: user decision (2026-08-14 evening). CONFIDENCE: VERIFIED (user decision).

## Latency plan findings (2026-08-14 evening, finalized next-lab scope)
- FACT: Today's 46 ms RTT was measured to Cloudflare (1.1.1.1), NOT the RTX's public IP —
  the true Jetson→RTX path RTT is UNMEASURED and is the decisive next diagnostic (floor for
  the whole <100 ms question). If ≈46 ms → floor ≈60 ms; if 100+ ms → link is the wall.
  SOURCE: mcq_rtt probe logs (2026-08-14 lab). CONFIDENCE: PARTIALLY VERIFIED (gap identified).
- FACT: Finalized next-lab scope = transport/latency ONLY: TRUE PATH RTT first, then
  320×240 @ 150 kbps + packet pacing if worth it. Constants: 30 fps, 50 ms jitter (25 ms
  measured identical — keep margin), CPU decode/infer, no retransmission, 250 ms timeout.
  SOURCE: user decisions (2026-08-14 evening). CONFIDENCE: VERIFIED (user decision).
- FACT: Real spec per user: on real roads, camera→actuator commands as fast as possible.
  <100 ms was aspirational, NOT a hard spec. Ideal road link: Jio 5G (RTT ~10–30 ms →
  <100 ms comfortably achievable); 4G borderline (~60 ms floor + queueing).
  SOURCE: user (2026-08-14 evening). CONFIDENCE: VERIFIED (user decision).
- FACT: First hardware-verified commit exists on GitHub: `8f35564` pushed to
  origin/jetson-nano (`57561db..8f35564`, repo sync 0/0). Contains all H1–H5 prep, lab
  fixes, 14-file milestone evidence, AUDIT/ERROR_LOG 08-14, and the branch-only purge of
  52 legacy/old-hardware files. No restructure tag created yet (deferred to explicit
  "do github restructure rn" trigger).
  SOURCE: git log/status (pushed this session). CONFIDENCE: VERIFIED.
- FACT: Second purge pushed `30728e1`: `robot/uno_q/` (9 files — STM32 + OAK-D + YOLOv6
  phone-control, the pre-Jetson Uno Q generation; zero current references; robot/jetson_nano
  KEPT as current). Cumulative old-hardware purge = 61 files across `8f35564` + `30728e1`.
  SOURCE: git log/status. CONFIDENCE: VERIFIED.
- FACT: Broker policy (DECISION 019, user mandate 2026-08-14 evening): brokerless for lab AND
  road sessions; fallback = the re-punch trick (NAT mappings are destination-independent —
  the RTX's hole stays alive via its keepalives even while the Jetson rebinds; Jetson
  re-STUNs and sends NEWCAND to the RTX's known endpoint through the still-open mapping).
  No broker rewrite, no aiohttp, no cloudflared in the new design; broker.py removal from
  the repo rides the next hardware-verified commit ONLY if the lab validation passes.
  SOURCE: user decision (2026-08-14 evening). CONFIDENCE: VERIFIED (decision; trick unvalidated).
- FACT: The 400 kbps new-network run (session 2b, p50 ~160 ms / p95 ~380 ms) had its loss /
  frames_rx NEVER LOGGED — the run's log was not preserved in evidence. The 400 kbps run on
  the OLD network lost ~55% of frames (14.1 fps, p95 1.67 s). Gap recorded; the lab bitrate
  A/B (DECISION 019) must log loss per run.
  SOURCE: evidence review (2026-08-14 evening). CONFIDENCE: VERIFIED (gap confirmed).

## Training rehearsal + transport prep (home, 2026-08-15 — session 2m)
- FACT: 5 usable old demo sessions (630 frames / 6 episodes) converted to LeRobot datasets
  `data/lerobot/rehearsal/<session>/` (repo-id `mq-rehearsal-<session>`); read-back verified:
  len 238 first dataset, `front_rgb` [3,720,1280] float32, `wheels` [0,0,0], `action` [90,0].
  SOURCE: `mcqueen_ml/dataset/convert_spool.py` + `validate_spool.py` + read-back runs.
  DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: `session_20260810_133136` FAILS validation (110 frames @ 5.00 Hz < 9–11 Hz
  contract); `session_20260809_180739` + `session_20260809_180748` empty. SOURCE:
  validate_spool.py output. CONFIDENCE: VERIFIED.
- FACT: NO training loop for TemporalDrivingPolicy existed; NEW trainer
  `mcqueen_ml/training/train_temporal_v2.py` (episode-level split, MSE on normalized
  actions, PPGeo/tiny backbones, resized 224×224 image cache ~380 MB) verified at home
  ONLY by import/argparse/py_compile — never executed (DECISION 023: laptop freezes under
  torch training; first real run = lab 4090). SOURCE: py_compile + argparse smoke.
  CONFIDENCE: VERIFIED (import-level) / training outcome UNVERIFIED.
- FACT: `tools/realtime/inference_rtx.py` now loads a trained checkpoint (`--checkpoint`:
  backbone/history/image_size/denorm from checkpoint; default random-tiny path unchanged):
  existing `test_inference_rtx.py` 18/18 PASS + NEW `test_checkpoint_inference.py` 11/11
  PASS (synthetic checkpoint, CPU). SOURCE: test runs. DATE: 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: Full suite green after inference_rtx.py edit: tests/test_jetson_protocol.py OK,
  test_jetson_drive.py PASS, test_realtime_contract.py OK (5),
  mcqueen_ml/training/test_temporal_policy_v2.py OK (3),
  test_backbones_ppgeo_resnet34.py OK (5, real PPGeo checkpoint). CONFIDENCE: VERIFIED.
- FACT: Laptop hardware limit: 7.6 GB RAM total, GTX 1650 Max-Q 4 GB; froze TWICE under
  torch training load 2026-08-15 (first with a ~7 GB full-res cache — agent bug fixed to
  ~380 MB; second on the fixed run) → DECISION 023 (no laptop training, ever). SOURCE:
  observed freezes + user mandate. CONFIDENCE: VERIFIED.
- FACT: Laptop has Android SDK (`/home/kartik/Android/Sdk`: platform android-36, build-tools
  36.0.0, JDK 17, adb, sdkmanager) but NO gradle distribution, NO gradle-wrapper.jar,
  NO local.properties → app build deferred to lab (fetch gradle-9.4.1-bin.zip + write
  local.properties first). SOURCE: filesystem + wrapper-dir inspection. CONFIDENCE: VERIFIED.
- FACT: `tools/realtime/measure_true_path_rtt.py` mechanics verified via loopback smoke:
  30/30 received, loss 0.0% (loopback RTT values are meaningless for WAN — only the
  mechanism is verified). `tools/realtime/run_bitrate_ab.sh` passes `bash -n`; NOT run
  (lab-only, needs authorization). SOURCE: loopback run + bash -n. CONFIDENCE: VERIFIED
  (mechanics only).
- FACT: Git state after session 2m: local HEAD == origin == `30728e1` (repo sync 0/0);
  uncommitted = 7 .mcqueen files + AGENTS.md + app Kotlin ×3 + drive.py/protocol.py +
  tests ×2 + inference_rtx.py + untracked {train_temporal_v2.py, measure_true_path_rtt.py,
  run_bitrate_ab.sh, test_checkpoint_inference.py, sync_calib.py, "context stuff" folder}.
  Nothing committed (DECISION 013). SOURCE: `git status` + `git rev-parse`. CONFIDENCE: VERIFIED.

## Session 2n (home, 2026-08-15) — freeze lesson, A/B fix, gradle prep
- FACT: The laptop froze a THIRD time during a single-batch, forward-only, GPU smoke
  (tiny backbone, batch 8, no backward, RAM guard passed with 5.2 GB available, 180 s
  alarm) → torch/CUDA execution itself triggers the freeze; DECISION 024: zero torch of
  any kind on the laptop. SOURCE: observed freeze 2026-08-15 + user mandate.
  CONFIDENCE: VERIFIED.
- FACT: `smoke_train_batch.py` (single-batch pipeline smoke: discovery → index → stats →
  dataset → collate → forward → checkpoint save/reload contract; RAM guard + 180 s alarm,
  NO backward) is written + py_compile-verified but has NEVER run; first run = 4090
  pre-flight at lab. SOURCE: py_compile; no execution (DECISION 024). CONFIDENCE:
  VERIFIED (static only) / run outcome UNVERIFIED.
- FACT: `run_bitrate_ab.sh` loss computation FIXED: was 100×(1 − frames_rx/SENT pkts)
  (packets ≠ frames — would print garbage); now 100×(1 − frames_rx/meta=) with an
  additional assoc_ok/assoc_miss loss column; `bash -n` OK. Receiver logs
  `VIDEO frames_rx=… assoc_ok=… assoc_miss=…`; sender logs `SENT pkts=… meta=…`. SOURCE:
  source grep + bash -n. CONFIDENCE: VERIFIED (static).
- FACT: gradle-9.4.1-bin.zip downloaded to ~/Downloads/ with SHA-256
  `2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb` (from
  services.gradle.org); gradle-wrapper.jar (48,966 B) fetched into
  apps/android/KachowV8/gradle/wrapper/; local.properties (sdk.dir=/home/kartik/Android/Sdk)
  created (gitignored). SOURCE: downloads + sha256 + ls. CONFIDENCE: VERIFIED.
- FACT: User decisions (session 2n): dataset recorded at 10 fps (recorder is the offline
  teleop path — zero impact on the live 30 fps loop; Q14 logs the temporal-rate mismatch);
  encoders: no work now (wheels stay zeros via NullEncoderSource at record AND inference —
  consistent train/infer). SOURCE: user answers. CONFIDENCE: VERIFIED (user decision).

## Session 2o (home exit, 2026-08-15) — final re-verification pass
- FACT: Post-2n verification pass re-confirmed everything: git tree 24 entries (16 M + 8
  ??), HEAD == origin == `30728e1`; 2n content present in all 6 state files; DECISION
  023/024 blocks complete; Q13/Q14 present; py_compile all 5 python files OK; `bash -n`
  OK; gradle-9.4.1-bin.zip SHA-256 `2ab2958f…6cb` == official; wrapper jar 48,966 B;
  local.properties gitignored; no stray processes; pure-python tests green. SOURCE:
  command outputs 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: No USB transfer needed for the lab: gradle zip + datasets + ckpt live on the
  laptop (app builds locally with the laptop's SDK); laptop→RTX transfers = scp over lab
  LAN; laptop↔Jetson = USB scp on 192.168.55.1. SOURCE: user clarification + env checks.
  CONFIDENCE: VERIFIED.

## Session 2p (lab departure, 2026-08-15) — report deliverables + final sanity
- FACT: `~/Downloads/mcqueen_project_report.txt` (2,865 words) and
  `~/Downloads/mcqueen_project_report_bullets.txt` (450 words) exist on disk; every
  number in them grep-verified against evidence sources (Aug 11 RTT 29.4/43.1/70.4/75.7
  @60/60 ACK; Aug 14 loop p50 287.1/p95 504.0, 57,641 frames, 25.4 fps, assoc
  52,095/3,287, 242,910 pkts; ladder 677/478/277; jitter 281.9 vs 276.8; save path
  0.96/1.32, 52,100 saved, 90.8%; 160 ms @400 kbps; 709 ms old-hotspot; link RTT 46).
  Leak-scan clean (no DECISION IDs, no ViReL, no PID, no HH:MM, no credentials).
  SOURCE: grep of report + evidence files 2026-08-15. CONFIDENCE: VERIFIED.
- FACT: At final departure check: git tree still 24 entries (16 M + 8 ??), HEAD ==
  origin == `30728e1`, zero commits, zero stray processes (only pgrep self-match).
## Session 3o (home, 2026-08-18) — NVIDIA NIM provider verification (model setup)
- FACT: NVIDIA NIM free-tier API key verified LIVE: HTTP 200 on `/v1/models` and real chat
  completions on `integrate.api.nvidia.com` (phone-verified account, no credit card). SOURCE:
  curl probes 2026-08-18. CONFIDENCE: VERIFIED.
- FACT: NIM live catalog = 102 models; `deepseek-ai/deepseek-v4-flash` and
  `deepseek-ai/deepseek-v4-pro` are END OF LIFE on NIM since 2026-08-07;
  `qwen/qwen3-coder-480b-a35b-instruct` EOL since 2026-06-11; `moonshotai/kimi-k2.6` returns
  404 for this account. models.dev catalog opencode uses is STALE (still lists EOL models).
  SOURCE: live `/v1/models` fetch + 410/404 probe responses. CONFIDENCE: VERIFIED.
- FACT: Live probes 2026-08-18: `deepseek-ai/deepseek-v4-flash-0731` (Jul-31 agent-tuned
  rebuild; 1M ctx documented) responds and produced a correct WebRTC SDP ICE-candidate parser;
  `z-ai/glm-5.2` responds in ~1.9 s; `nvidia/nemotron-3-ultra-550b-a55b` and
  `nvidia/nemotron-3.5-lightning-30b-a3b` respond; `stepfun-ai/step-3.7-flash` and
  `thinkingmachines/inkling` respond. SOURCE: chat-completion probes. CONFIDENCE: VERIFIED.
- FACT: The previous default `opencode/deepseek-v4-flash-free` (OpenCode Zen free tier)
  returned `FreeUsageLimitError` on a live probe — rate-limited/exhausted at probe time.
  SOURCE: zen API probe 2026-08-18. CONFIDENCE: VERIFIED.
- FACT: NIM free tier (community-observed, no official SLA): ~40 RPM account-wide (shared
  across all models on one key), NO daily request cap; 429s honor Retry-After; DeepSeek
  endpoint congested today (66 s small-answer latency, 529 Overloaded, 10-min agentic stall);
  GLM-5.2 unaffected. SOURCE: forum reports + live measurements. CONFIDENCE: VERIFIED.
- FACT: Config: `~/.config/opencode/opencode.jsonc` now defaults to
  `nvidia/deepseek-ai/deepseek-v4-flash-0731` with a 6-model NVIDIA map; NVIDIA key stored in
  opencode `auth.json` (never in repo); `opencode models` lists all 6 registered models.
  SOURCE: config + `opencode models` output 2026-08-18. CONFIDENCE: VERIFIED.
- FACT: The "account-wide 429" conclusion was CORRECTED same evening — NIM rate limits are
  PER-MODEL, not account-wide. Live probe battery (all 6 models): nemotron-3-ultra 200 in
  0.67s (curl) but FAILS through opencode (UnknownError ×2 — endpoint rejects opencode's
  request format); step-3.7-flash 200 in 2.65s AND verified through opencode (read tool +
  correct answer); inkling 200 in 0.71s (curl only); nemotron-3.5-lightning 200 in 7.9s
  (curl only); GLM-5.2 429 (its own pool burned); 0731 HTTP 000 / 45s timeout (endpoint
  congested). SOURCE: curl + `opencode run` 2026-08-18. CONFIDENCE: VERIFIED.
- FACT: Config default CHANGED 2026-08-18 evening → `nvidia/stepfun-ai/step-3.7-flash`
  (only NIM model verified working through opencode tonight). All 6 models remain
  registered. SOURCE: config edit + parse check. CONFIDENCE: VERIFIED.
- FACT: step-3.7-flash specs (third-party): 198B MoE (11B active), 256K ctx, vision-native,
  3 reasoning levels, SWE-bench Pro 56.3, TB2.1 59.5 (StepFun launch claims), open weights
  Apache 2.0 on HF. vs 0731: 1M ctx/131K out, TB2.1 82.7 (DeepSeek claim). Same benchmark,
  0731 claims +39%. Both free on NIM. SOURCE: cloudprice/benchlm/llmreference/tpsreport
  2026-08-19. CONFIDENCE: PARTIALLY VERIFIED (vendor claims, not independently measured).
- FACT: Same-evening follow-up (2nd attempt): NIM account-wide 429 persisted 30+ min after
  last success, NO Retry-After / x-ratelimit headers (opaque burst limit); 0731 agentic
  task stalled a 2nd time (2/2 stalls). SOURCE: live curls + `opencode run` 2026-08-18.
  CONFIDENCE: VERIFIED (infrastructure saturation, not model quality — single-turn probes
  all answered when budget allowed).
- FACT: google/gemini-2.5-flash is deprecated for new users (error directs to
  gemini-3.6-flash); google/gemini-3.6-flash is live on the connected AI Studio key.
  SOURCE: `opencode run` error + models list 2026-08-18. CONFIDENCE: VERIFIED.
- FACT: google/gemini-3.6-flash completed smoke TASK A end-to-end: found genuine bug in
  tools/mcqueen_recorder.py (next_save_time incremented before frame-availability and
  staleness checks, burning save slots), applied minimal fix, py_compile passed (re-checked
  by me). Agentic tool loop (read/grep/edit/bash) fully works. SOURCE: `opencode run`
  transcript + `git diff` + py_compile 2026-08-18. CONFIDENCE: VERIFIED.

## Session 3p facts (2026-08-19)
- FACT: GitHub push ef68be0 (19 files, chestnut stack + TRAINING_REPRO_GUIDE + README +
  AGENTS.md) landed on medhansh2808/McQueen branch jetson-nano; remote ref
  ef68be0efe95e9dc2b486406bb5a4a30996028ba == local HEAD. SOURCE: git push output +
  git ls-remote + git rev-parse, 2026-08-19. CONFIDENCE: VERIFIED.
- FACT: tools/donkey/test_tub_to_sessions.py passes (pure stdlib, no torch). SOURCE:
  local run 2026-08-19. CONFIDENCE: VERIFIED.
- FACT: DonkeySim CANNOT run on Xvfb :99 — HTTP API never responds; the sim needs a real
  X display (Intel iGPU enough; model runs on CUDA). SOURCE: 321% CPU + curl timeout
  (Aug 17) + confirmed again 2026-08-19. CONFIDENCE: VERIFIED.
- FACT: RTX desktop :1 auto-locked after ~idle since Aug 12 → the captured v2 "run"
  footage is the lock screen, not the sim. SOURCE: xwd frames + user viewing clips.
  CONFIDENCE: VERIFIED.
- FACT: GNOME Videos (Totem) on user's laptop lacks an H.264 decoder; WebM/VP9 plays.
  Local ffplay is broken headless (fails on testsrc too). SOURCE: user report + my ffplay
  test. CONFIDENCE: VERIFIED.
- FACT: RTX GPU busy 2026-08-19 with ViReL evaluation.py robovista greedy
  unsloth/Qwen3-VL-8B-Thinking (junior, tmux 209920, /home/junior/ViReL/Tasks/vlmgrpo);
  GPU 97%, ~18-20 GiB, rotating PIDs (2807960→2809166→2814601). SOURCE: nvidia-smi +
  ps. CONFIDENCE: VERIFIED (point-in-time).
- FACT: Firefox on RTX display opened 2026-08-19 ~16:02 with a "Discord | #meow" window;
  the Donkey Monitor tab is a session-restored leftover from Aug 16 research (no 8887
  visits in history). No repo code auto-opens browsers. SOURCE: ps start times, history.
  CONFIDENCE: VERIFIED — none of it is McQueen software.
- FACT: chestnut_pilot.py --exe default is now os.path.expanduser("~/donkey_sim/
  DonkeySimLinux/donkey_sim.x86_64") — byte-identical resolution on the RTX, portable
  elsewhere. SOURCE: edit + py_compile + string check 2026-08-19. CONFIDENCE: VERIFIED.
- FACT: run_rtp_lan_test.sh machine values (RTX/JETSON/RTX_DIR/RTX_PY/BROKER_PY/CAM) are
  env-overridable with identical defaults; bash -n passes. SOURCE: edit + bash -n
  2026-08-19. CONFIDENCE: VERIFIED.
- FACT: docs/TRAINING_REPRO_GUIDE.md ships only verified links: commaai/openpilot
  releases, tawnkramer/gym-donkeycar releases (Race Edition, circuit_launch ≥ v21.07.24),
  media.githubusercontent.com/media/autorope/donkey_datasets/master (SHA-verified ~335 MB).
  Sessions/checkpoints NOT hosted — documented as recreate steps. SOURCE: guide text
  + earlier verification. CONFIDENCE: VERIFIED.

## Session 3q facts (2026-08-19)
- FACT: RTX display :1 was GNOME-idle-LOCKED (loginctl session 2 LockedHint=yes) during
  ALL prior capture attempts → all x11grab footage showed the lock screen, not the sim.
  SOURCE: loginctl + frame YAVG identical across timestamps. CONFIDENCE: VERIFIED.
- FACT: `sudo loginctl unlock-session 2` unlocks :1 (password via stdin, transient);
  gsettings org.gnome.desktop.screensaver lock-enabled true/false toggles auto-lock
  (idle-delay key absent on this GNOME). Both used transiently, restored to true.
  CONFIDENCE: VERIFIED.
- FACT: ffmpeg x11grab on :1: mp4 muxer writes in bursts (file 48 B for ~8 s is normal);
  SIGKILL truncates mp4 (moov missing) — use avi container for kill-proof captures;
  x11grab produces no frames while the screen is static (damage-based) but captures
  continuously during sim animation. SOURCE: 5+ capture experiments 3q. CONFIDENCE:
  VERIFIED.
- FACT: chestnut v2 re-shoot runs (3q): 212/155 and 149/134 steps (vs 51/16 on Aug 18)
  — same full-lock oscillation crash pattern. SOURCE: pilot logs 3q. CONFIDENCE:
  VERIFIED.
- FACT: sim_pilot.py (donkey head pilot) needs the ONNX trunk driving_supercombo_master.onnx
  (29,996,510 params); passing chestnut_onnx2torch_sd_batch.pt (a torch file) → protobuf
  DecodeError crash. SOURCE: dk3 run 3q. CONFIDENCE: VERIFIED.
- FACT: donkey head v2 run dk3 (trim -0.08, warmup 25, max-steps 1200): 73/48 steps —
  does NOT reproduce the Aug 18 673-751 result; exact Aug-18 invocation must be
  recovered from docs/evidence/2026-08-18/donkey-sim-training/ logs before the next
  attempt. SOURCE: dk3_pilot.log 3q. CONFIDENCE: VERIFIED (numbers), UNVERIFIED (cause).

## Session 3r facts (2026-08-19, lab)
- FACT: chestnut_lora_best_v3.pt DOES NOT EXIST on RTX (~/mcqueen/models listing Aug 19).
  v3 training never completed (paused mid-epoch-0 Aug 18; ~36 min/epoch). All three
  re-shoot pilots (v2_reshoot, v2b, v3_pilot.log) loaded the v2 checkpoint — identical
  header (curv_floor=3.0, action_scale=1.0) + OOD action signature (-91/-97) → the
  216/190 "v3" numbers are v2 behavior. SOURCE: RTX logs + models dir. CONFIDENCE:
  VERIFIED.
- FACT: RTX GPU was FREE at lab check (0% util, 25 MiB used of 24.5 GiB, no compute
  apps); display :1 unlocked (LockedHint=no) but actively used by a human (recent
  Firefox Claude tab, Disk Usage Analyzer, terminal). SOURCE: nvidia-smi + xwininfo,
  session 3r. CONFIDENCE: VERIFIED (at check time).
- FACT: Jetson unreachable at lab via: USB gadget (no route), LAN SSH (old .112 gone;
  20+ live hosts swept direct + via RTX hop, zero known-user hits; LAN SSH firewalled
  per earlier facts), and the cloudflared tunnel (port 2223 resets; laptop-side config
  matches ~/mcqueen-remote/jetson.url; Jetson-side dialer not running even on
  Wi-Fi+internet). SOURCE: live session 3r. CONFIDENCE: VERIFIED.
- FACT: home access to the Jetson works ONLY via the cloudflared reverse tunnel
  `ssh -p 2223 sravjti@127.0.0.1`; the Jetson-side broker must be running for it to
  work. SOURCE: ~/mcqueen-remote/ + live tests. CONFIDENCE: VERIFIED.
