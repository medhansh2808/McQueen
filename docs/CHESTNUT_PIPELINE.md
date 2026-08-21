# CHESTNUT PIPELINE — big_driving_supercombo on donkey-sim

Status: ACTIVE (2026-08-18 overnight run). The McQueen goal (user Q4): a realtime
driving pipeline that is architecture-reproducible for real-car datasets later. The
large autonomous-driving model lives on the RTX 4090; the Jetson never runs it
(AGENTS.md F).

The model: comma `big_driving_supercombo.onnx` ("chestnut", 1,757,355,221 B, opset 20,
874 nodes, checkpoint id 6f5c8d09-b057-bd3c-f8e8-46daddea14f8/ecc73f48-623f-4207-ad2b-d42e8619f08b).
sha256 a501760a9d1d5fef0eab2b8c5d122d06124fc26dc8e0782e0aa94b82a208f0ff.

## Provenance / fetch

Source of the .onnx file is the commaai openpilot release artifacts (camera .onnx +
big .onnx pair). Recorded where the download happened (see .mcqueen/VERIFIED_FACTS.md).

## I/O contract (verified by dump_onnx_io.py + dump_chestnut_slices.py)

Inputs (all batch-1-harcoded in the export; patched — see below):

    img            1x12x128x256  UINT8   two packed YUV frames
    big_img        1x12x128x256  UINT8   (same for our pipeline)
    desire_pulse   1x25x8        fp16
    traffic_convention 1x2       fp16
    action_t       1x2           fp16
    features_buffer 1x24x512     fp16

Output: single flattened `outputs` (1x2580 fp16). Slice map (from ONNX metadata
`output_slices`, base64 pickle):

    lane_lines [0:528)  lane_lines_prob [528:536)  road_edges [536:800)
    meta [800:855)  desire_pred [855:887)  pose [887:899)
    wide_from_device_euler [899:905)  road_transform [905:917)
    plan [917:1907)  (33 x 15 mu + 15 std)  lead [1907:2051)  lead_prob [2051:2054)
    desire_state [2054:2062)  action [2062:2066)  hidden_state [2066:2578)
    pad [-2:]  (unused; removed in the batch patch)

The 'pad' (1,2) constant is concatenated onto the flattened output; every real
consumer uses slices <= 2578, so removing it is safe.

## Control mapping (openpilot modeld.py, verified)

    desired_curvature = action[0,0] / max(1.0, v_ego)^2
    desired_accel     = action[0,1]
    traffic_convention[is_rhd] = 1   (India -> [0,1])

Zero-shot diagnostics (chestnut_pilot --trace): pose[0] (model's internal speed
estimate) reads ~30-37 while the sim telemetry reads ~3.8 m/s — the model behaves as
if at highway speed, hence near-zero curvature commands. The sim caps speed at
~3.8 m/s even at full throttle. The model sees near-straight road in the raw sim
view (plan1 ~1.16 m forward, ~3 mm lateral).

## Convert (onnx2pytorch, mcqueen-openpilot env)

    /home/junior/mcqueen-openpilot/bin/python convert_chestnut.py big_driving_supercombo.onnx <outdir>
    -> chestnut_onnx2torch_sd.pt (6,124,020,173 B fp32 module, {"model": module}; ~25 s)

Load: torch.load(..., weights_only=False)["model"].

## Batch patch (REQUIRED before LoRA training)

The export is batch-1-hardcoded: 6 Reshape shape initializers start with 1 and the
final output concat appends a (1,2) 'pad' constant. tools/donkey/patch_chestnut_batch.py
rewrites leading 1 -> -1 ([-1,-1] is illegal; the desire_pulse flatten [1,-1] -> [-1,200])
and removes 'pad' from the output concat. Outputs: 2580 -> 2578 (used slices <= 2578
unchanged; batch-1 outputs identical, verified max abs diff 0.0).

    python patch_chestnut_batch.py --onnx big_driving_supercombo.onnx --out big_driving_supercombo_batch.onnx
    python convert_chestnut.py big_driving_supercombo_batch.onnx /tmp
    -> chestnut_onnx2torch_sd_batch.pt

## Known onnx2pytorch issues (torch 2.11 semantics; both fixed in the venv)

1. operations/gather.py:13 and operations/slice.py:86 use `data[selection]` with a
   list — deprecated; under torch 2.9+ a list is converted to a TENSOR index, which
   produces garbage shape tensors (observed: dynamic reshape target '[16, -1]' from a
   corrupted slice of a Shape tensor). Fix: `data[tuple(selection)]` (the warning's
   own prescription). Both files patched in mcqueen-openpilot.
2. convert/model.py has a try/except FAILOP instrumentation (prints the failing op id
   and input shapes) added 2026-08-18 — harmless, useful for future debugging.

## Bench (single-frame, fp16 cuda)

bench_chestnut.py: load 13.6 s, warmup 218 ms, median 27.1 ms / p90 27.3 ms per
frame, peak 3,541 MiB VRAM (fp16). (The model is the RTX-side component; the
capture->control-return latency budget is measured separately — see AGENTS.md E.)

## Sim pilot (chestnut_pilot.py)

Runs the model against gym_donkeycar 1.3.1 (circuit_launch). Key knobs:

    --mode metrics --track circuit_launch --runs 2 --port 9091 --max-steps 1200 --warmup 25
    --module chestnut_onnx2torch_sd_batch.pt | chestnut_lora_best.pt
    --curv-floor 1.0   (assumed-v=1 for the curvature mapping)
    --action-t 0 0 --throttle-ff 0.7 --throttle-kp 0.8   (LoRA evaluation)
    --trace / --crop-bottom 0.6 / --pose-slice / --plan-slice   (diagnostics)

Sim launch recipe (PROVEN; never pkill+launch in one command — pkill self-matches):

    sh -c "cd ~/mcqueen/models && DISPLAY=:1 setsid nohup /home/junior/mcqueen-openpilot/bin/python \
        chestnut_pilot.py <flags> > ~/mcqueen/run/<log> 2>&1 < /dev/null &"

DISPLAY requirements (verified): real Xorg on :1 (Mesa iGPU). Xvfb is NOT enough
(Unity stalls after car load). Unity ignores SIGTERM — kill -9 by PID.

Results so far (2026-08-18):
- Zero-shot (chestnut_onnx2torch_sd.pt, curv_floor 1.0, crude throttle): 2x1200 steps
  no crash (survival beats v2's 673) but no real driving: mean CTE ~3.6, steer range
  +/-0.05, max speed 1.55 m/s -> GATE FAIL -> LoRA path.
- LoRA v1 (ed_1 only, labels curv): 10 epochs, best val 0.237 (ep 2). Drives with
  full-range steering but oversteers at low v -> crashes (35/8 steps). Label scale
  mismatched the runtime /v^2 mapping (v_assumed=1 vs floor 1).
- LoRA v2 (expanded 6.8x data, labels curv*9): best val 14.58 (ep 2). Wild OOD
  actions (60 vs max label 26) -> crashes (51/16 steps). Label scale beyond the
  frozen head's natural range.
- LoRA v3 (expanded data, RAW curvature labels + pilot --action-scale 9): IN
  PROGRESS (epoch 0 eval planned immediately after epoch 0, time-bounded).

Gate (unchanged contract): beat 673 steps AND complete a full lap.

## LoRA training (train_chestnut_lora.py)

Why hand-rolled: peft's all-linear target breaks on onnx2pytorch custom ops that
subclass nn.Linear with different signatures. Hand-rolled LoRAModule: frozen base +
picklable _LoraHook forward hooks on EXACT `type(m) is nn.Linear` modules, params in
a nn.ParameterDict bank; __setstate__ re-registers hooks (pickle round-trip verified,
diff 0.0). 11.23M trainable params (1.26% of 877M).

Labels (assumed-v mapping, DECISION 2026-08-18, CORRECTED v3): training targets
are RAW curvature (the model's natural action-head scale ~[-1,1]):
action[0] = tan(steer*0.78)/0.35; action[1] = throttle*2.0. The openpilot
curv*v^2 scale is applied at RUNTIME: chestnut_pilot --action-scale 9
(= V_ASSUMED^2, V_ASSUMED = 3.0) and --curv-floor 3.0:
curv = action[0]*9/max(3, v_ego)^2 — round-trips dataset steering at v=3.
WHY v3: v2 trained curv*v^2 targets (0..26) on the frozen head (natural range
~[-1,1]) -> OOD overshoot in sim (action[0,0]=60 vs max label 26, accel -6.4)
-> crashes (51/16 steps). Pilot also clips action[0,0] to +-30 and accel to
+-4 as an OOD guard.

Loss: weighted MSE (0.7 steer / 0.3 accel).

    python train_chestnut_lora.py --module chestnut_onnx2torch_sd_batch.pt \
        --sessions-root ~/mcqueen/run/donkey_sessions/train \
        --val-root ~/mcqueen/run/donkey_sessions/val \
        --out ~/mcqueen/models/chestnut_lora_best.pt \
        --epochs 10 --batch-size 16 --lr 1e-4 --r 16 --alpha 32
    # --smoke for a single training batch (train loss sanity)

Data: ed_1 = 23 train sessions (11,470 frames) + 6 val (2,867). Source:
autorope/donkey_datasets (LFS; fetch via
https://media.githubusercontent.com/media/autorope/donkey_datasets/master/<path>;
verify sha256 = LFS OID).

## Dataset expansion (downloaded + SHA-verified 2026-08-18, ~335 MB)

    circuit_launch_ed_2.tar.gz      (16 catalogs)   +OID verified
    circuit_launch_adam_1.tar.gz    (5 catalogs)    +OID verified
    circuit_launch_20210716_1611/1715/1826.tar.gz   (35/18/29 catalogs, nested data/) +OID verified

Conversion to sessions: tools/donkey/tub_to_sessions.py --tub <dir> --out
<expanded_root> --val-frac 0.2 --chunk 500 (standard-library, no torch). Do NOT touch
the running trainer's sessions dir. Use the expansion only for the NEXT training run.

## Repo files

    tools/donkey/patch_chestnut_batch.py   batch-agnostic ONNX patch
    tools/donkey/tub_to_sessions.py        catalog tub -> session dirs
    models/train_chestnut_lora.py          LoRA trainer (source of truth; scp to RTX)
    models/chestnut_pilot.py               sim pilot (source of truth; scp to RTX)
    docs/CHESTNUT_PIPELINE.md              this runbook

## RTX artifacts (~/mcqueen/models/)

    big_driving_supercombo.onnx            original artifact (untouched)
    big_driving_supercombo_batch.onnx      patched copy
    chestnut_onnx2torch_sd.pt              converted fp32 (batch-1)
    chestnut_onnx2torch_sd_batch.pt        converted fp32 (batch-agnostic)
    chestnut_lora_best.pt                  LoRA checkpoint (trainer output)
    train_chestnut_lora.py / chestnut_pilot.py / bench_chestnut.py / dump_*.py

Logs: ~/mcqueen/run/chestnut_*.log

## Safety / discipline

- No git commits from home; mirror only via ~/mcqueen-remote/sync_state.sh --check.
- Machine hygiene (DECISION 014): RTX is a common machine; only touch McQueen's own
  files. The two onnx2pytorch source edits above are inside McQueen's own
  mcqueen-openpilot venv (keep-list).
- No timestamps in audits/evidence reports (user mandate 2026-08-14).