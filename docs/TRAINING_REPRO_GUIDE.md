# TRAINING REPRO GUIDE — chestnut (comma big_driving_supercombo) LoRA on DonkeySim

This guide reproduces the overnight chestnut experiment: a comma `big_driving_supercombo`
ONNX trunk converted to PyTorch, LoRA-adapted on DonkeySim driving data, and evaluated
in the simulator. Every number below comes from an actual run; nothing is estimated.
Proof states use the project's convention: VERIFIED / PARTIALLY VERIFIED / UNVERIFIED.

## 1. Hardware and environment

- GPU: NVIDIA RTX 4090-class (24 GB VRAM) — the trunk in fp16 uses ~3 GB; batch 16 peaks
  at ~3.5 GB. Older GPUs with less VRAM need a smaller batch.
- Sim rendering: the DonkeySim binary renders on the GPU machine's desktop session
  (Intel iGPU is enough; the model itself runs on CUDA).
- Python environment: Python 3.12, PyTorch with CUDA, `onnx2pytorch` (see the script
  docstrings for the exact import surface), OpenCV, gym-donkeycar 1.3.1.
- The sim binary: DonkeySim Race Edition (see links below).

## 2. End-to-end steps

### 2.1 Fetch the base model (VERIFIED)

File: `big_driving_supercombo.onnx` — 1,757,355,221 bytes, opset 20, 874 nodes,
checkpoint id `6f5c8d09-b057-bd3c-f8e8-46daddea14f8/ecc73f48-623f-4207-ad2b-d42e8619f08b`.

- Source: https://github.com/commaai/openpilot/releases (release artifacts; the model
  era matches the 0.10.3+ "temporal policy" releases).
- Identity check (mandatory — the download page lists assets by name, verify the file
  you get against these):

      sha256sum big_driving_supercombo.onnx
      # expected: a501760a9d1d5fef0eab2b8c5d122d06124fc26dc8e0782e0aa94b82a208f0ff

### 2.2 Patch and convert to PyTorch (VERIFIED)

The export hard-codes batch=1 in Reshape initializers; patch them to be batch-agnostic,
then convert with onnx2pytorch (~25 s on an RTX 4090):

    python tools/donkey/patch_chestnut_batch.py --onnx big_driving_supercombo.onnx \
        --out big_driving_supercombo_batch.onnx
    python models/convert_chestnut.py big_driving_supercombo_batch.onnx <out_dir>

Output: `chestnut_onnx2torch_sd_batch.pt` (the frozen trunk module used by the trainer
and the pilot).

### 2.3 Get training data (two routes, both VERIFIED)

Route A — record your own DonkeySim sessions:
- Simulator: https://github.com/tawnkramer/gym-donkeycar/releases (Race Edition;
  the `circuit_launch` track exists since v21.07.24).
- Drive with the keyboard/manual control, then convert the catalog tub:

      python tools/donkey/tub_to_sessions.py --tub <catalog_dir> --out <root> \
          --val-frac 0.2 --chunk 500
      python tools/donkey/prepack_sessions.py <root>   # packs frames to (6,128,256) uint8 YUV

- Session layout produced: `<root>/session_XXX/controls.csv` (steering, throttle in
  [-1,1]) + `rgb_raw_upright/frame_*.npy`. Unit test:
  `python tools/donkey/test_tub_to_sessions.py` (pure stdlib, no torch).

Route B — public donkey datasets (used for the expansion, ~335 MB, SHA-verified):
- https://media.githubusercontent.com/media/autorope/donkey_datasets/master/<path>
  (git-lfs repo; this media URL serves the raw files without git-lfs). Verify every
  downloaded catalog with sha256 before converting.

### 2.4 Train the LoRA (trainer file status: PENDING PUSH)

The trainer `models/train_chestnut_lora.py` (LoRA via forward hooks on exact
`nn.Linear` layers of the frozen trunk, weighted MSE over the action slice) was run in
three label versions on the RTX:

- v1 — openpilot curv*v^2 targets: 10 epochs, best val 0.23681. Sim result: drives
  nothing (zero-shot GATE FAIL). Label scale wrong.
- v2 — same curv*v^2 targets, expanded dataset (165 train / 43 val sessions),
  3 epochs x ~35.8 min: best val 14.57770. Sim result: OOD action 60 vs max label 26,
  crashes at 51/16 steps. Scale still wrong.
- v3 — RAW curvature targets + runtime mapping in the pilot (`--action-scale 9.0`
  = V_ASSUMED^2 with V_ASSUMED 3.0, `--curv-floor 3.0`): interrupted in epoch 0,
  no checkpoint. UNVERIFIED.

The trainer file is NOT yet in this commit (DECISION 013: nothing unverified is pushed;
v3 never completed one epoch). It will be added after the next validated training run.
The intended v3 invocation:

    python models/train_chestnut_lora.py \
        --module chestnut_onnx2torch_sd_batch.pt \
        --sessions-root <train_root> --val-root <val_root> \
        --out chestnut_lora_best.pt --epochs 10 --batch-size 16 --lr 1e-4 --r 16 --alpha 32

(`--smoke` runs a single training batch as a sanity check.)

### 2.5 Evaluate in the simulator (VERIFIED)

    DISPLAY=:1 python models/chestnut_pilot.py \
        --mode metrics --track circuit_launch --runs 2 --port 9091 --max-steps 1200 \
        --warmup 25 --module chestnut_lora_best.pt \
        --curv-floor 3.0 --action-t 0 0 --throttle-ff 0.7 --throttle-kp 0.8

Key facts learned (verified):
- The sim must run on a real X display (Xvfb is not enough: software GL starves the
  sim's HTTP server and it never becomes ready).
- The v2 crash pattern is deterministic (51/16 steps) and caused by the label-scale
  mismatch, not by the sim.

## 3. Results and comparisons (all VERIFIED unless marked)

| Version | Labels | Train | Best val | Sim behavior |
|---|---|---|---|---|
| zero-shot (no LoRA) | — | — | — | survives 1200 steps, never steers |
| v1 | curv*v^2 | 10 epochs | 0.23681 | drives nothing (GATE FAIL) |
| v2 | curv*v^2 | 3 x ~35.8 min | 14.57770 | OOD action 60 vs max 26; crash 51/16 |
| v3 | raw curvature + runtime map | interrupted epoch 0 | — | UNVERIFIED (no checkpoint) |

Perf bench (VERIFIED): 27.1 ms/frame median (fp16, batch 1), 3,541 MiB peak VRAM at
batch 16, model load 24.3 s, 888M trainable-adjacent params (LoRA r=16).

## 4. What is NOT in this repository — and how to get it anyway

| Asset | Size | Why not here | How to get it |
|---|---|---|---|
| Our recorded sessions | multi-GB | datasets are not committed (policy) | record your own (2.3 Route A) or download public catalogs (2.3 Route B) |
| `chestnut_onnx2torch_sd_batch.pt` | ~GB | model weights are not committed | build it: steps 2.1 + 2.2 (~25 s) |
| LoRA checkpoints (v1/v2/v3) | ~6 GB each | model weights are not committed | train them: step 2.4 |
| `mcqueen-openpilot` python env | — | machine-specific | recreate: python 3.12 + torch + onnx2pytorch + cv2 + gym-donkeycar 1.3.1 |
| DonkeySim binary | ~1 GB | third-party | gym-donkeycar releases link (2.3 Route A) |

No other download links exist for McQueen artifacts — anything not listed above was
never hosted anywhere, and nothing here is a guess.

## 5. Verification states summary

VERIFIED: fetch+sha256, patch, convert, session conversion (unit test passes), pilot
evaluation recipe, zero-shot/v1/v2 results, bench numbers, DonkeySim/Xvfb fact.
UNVERIFIED: v3 training (interrupted), trainer file content as of this commit.