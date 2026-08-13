# VERIFIED_FACTS.md — McQueen verified facts

Only facts supported by repository evidence or explicitly recorded verified project docs.
Format: FACT | SOURCE | DATE/COMMIT | CONFIDENCE

---

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
