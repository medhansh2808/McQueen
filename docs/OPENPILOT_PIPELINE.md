# OPENPILOT_PIPELINE.md — McQueen driving model (comma.ai supercombo)

STATUS: **PIPELINE COMPLETE — SMOKE PASSED on RTX** (2026-08-17, session 3i part 3).
One open design decision (frozen plan-based control vs custom trainable head) — see
"Open decisions".

---

## 1. TL;DR

McQueen's driving model is comma.ai's **2026-master `driving_supercombo.onnx`** — a fully
frozen 30 M-param vision+temporal model converted to PyTorch via onnx2pytorch. Steering and
throttle are derived from the model's PLAN output using comma's own control math
(`get_curvature_from_plan` / `get_accel_from_plan`). The model runs on the RTX; the Jetson
hosts camera capture + the safety gate (per AGENTS.md architecture).

Original intent (DECISION 027) was a frozen supercombo trunk + a retrained 4-dim action head.
**Verification proved no comma export has ever had an action head** (see §6) — the action-head
contract in the repo's original `models/` code was fabricated by the previous agent and never
executed. The pipeline was therefore rebuilt on the real model, keeping the repo's input
contract 1:1.

## 2. Pipeline

```
JETSON CAMERA ──► WebRTC/transport ──► RTX ──► FrozenActionModel (supercombo, frozen)
                                                   │
                                                   ├─ plan (1,33,15 MDN means)
                                                   ├─ hidden (1,512) → temporal buffer
                                                   └─ action (1,4) = [curvature, accel, 0, 0]
                                                        │  plan-derived (comma math)
                                                        ▼
                                              action_to_command_torch → steer/throttle [-1,1]
                                                        ▼
                                              JETSON SAFETY GATE ──► servo + motor
```

## 3. Model identity (VERIFIED 2026-08-17)

| Field | Value |
|---|---|
| File | `driving_supercombo.onnx` |
| Source URL | `https://raw.githubusercontent.com/commaai/openpilot/master/openpilot/selfdrive/modeld/models/driving_supercombo.onnx` |
| Size | 60,881,999 bytes |
| SHA-256 | `659727c4d4839adc4992a254409a54259a8756a743f2d567bf5fdc6579f8009b` (== LFS OID, VERIFIED) |
| Graph | 351 nodes, 334 initializers, 29,996,510 params |
| RTX copy | `~/mcqueen/models/driving_supercombo_master.onnx` |
| dtype | float32 graph; img inputs uint8 |

Also on the RTX (rejected/archived, all SHA-verified): `supercombo_v0.9.4.onnx`
(`d7f95f6b…ffaf8a8`, 47.5 MB, 2023 API), `supercombo_v0811.onnx` (`43d36248…f40588`,
56.7 MB, 2021 API), `supercombo.onnx` (95.2 MB, `15d9eb01…f4eca`, provenance unknown,
new-API, no action head).

## 4. Model API (VERIFIED from the model itself)

Inputs (exactly the repo contract):

| Name | Shape | Notes |
|---|---|---|
| `img` | (1, 12, 128, 256) | 6-channel packed YUV (y0..y3,u,v), 2 stacked frames, uint8 |
| `big_img` | (1, 12, 128, 256) | wide-frame stack, uint8 |
| `features_buffer` | (1, 24, 512) | past 24 hidden features (temporal context) |
| `desire_pulse` | (1, 25, 8) | zeros for McQueen (no nav commands) |
| `traffic_convention` | (1, 2) | zeros (RHD flag) |
| `action_t` | (1, 2) | zeros (prev action) |

Output: single flattened `outputs` (1, 2576). Slice layout embedded in the model's own
metadata (`output_slices`, base64-pickled) — VERIFIED:

| Slice | Range | Size | Meaning |
|---|---|---|---|
| meta | 0:55 | 55 | engage/lead probs |
| desire_pred | 55:87 | 32 | desire prediction |
| pose | 87:99 | 12 | device pose |
| wide_from_device_euler | 99:105 | 6 | extrinsics |
| road_transform | 105:117 | 12 | road transform |
| lane_lines | 117:645 | 528 | lane lines MDN |
| lane_lines_prob | 645:653 | 8 | lane probs |
| road_edges | 653:917 | 264 | road edges |
| lead | 917:1061 | 144 | lead vehicle |
| lead_prob | 1061:1064 | 3 | lead probs |
| **hidden_state** | 1064:1576 | 512 | temporal feature (→ next features_buffer) |
| **plan** | 1576:2566 | 990 | plan MDN = 33 pts × 30 (15 means + 15 stds) |
| desire_state | 2566:2574 | 8 | desire state |

Plan per-point layout (15 values): POSITION (x,y,z) 0:3, VELOCITY (vx,vy,vz) 3:6,
ACCELERATION 6:9, T_FROM_CURRENT_EULER 9:12, ORIENTATION_RATE 12:15 (comma `Plan` enum).

## 5. Control math (VERIFIED — ported from openpilot master, 2026-08-17)

Sources: `openpilot/selfdrive/modeld/parse_model_outputs.py` (parse_mdn),
`openpilot/selfdrive/controls/lib/drive_helpers.py` (get_curvature_from_plan,
get_accel_from_plan), `openpilot/selfdrive/modeld/constants.py` (ModelConstants).

- `plan_mu = plan.view(1,33,30)[:, :, :15]` (MDN means)
- `T_IDXS = [10.0*(i/32)**2 for i in range(33)]`
- `MIN_SPEED = 1.0`, `MIN_STABLE_DELAY = 0.3`, `action_t = 0.05` (DT_MDL, 20 Hz)
- **accel**: `a_target = 2*(v_target − v_now)/action_t − a_now`, where
  `v_now = speeds[0]`, `a_now = accels[0]`, `speeds = plan_mu[:,3]`, `accels = plan_mu[:,6]`,
  `v_target = interp(action_t, T_IDXS, speeds)` (with MIN_STABLE_DELAY ramp if action_t < 0.3)
- **curvature**: `psi_target = interp(action_t, T_IDXS, yaws)` (yaw = plan_mu[:,11]),
  `psi_rate = yaw_rates[0]` (yaw_rate = plan_mu[:,14]),
  `curv = 2*psi_target/(v_ego*action_t) − psi_rate/v_ego`, `v_ego = max(v_ego, 1.0)`
- **command**: `steering = atan(CAR_LENGTH_M * curv)/MAX_STEER_ANGLE_RAD` clamped to [-1,1]
  (CAR_LENGTH_M=0.35, MAX_STEER_ANGLE_RAD=0.78), `throttle = clamp(accel/MAX_SPEED_MPS, -1, 1)`
  (MAX_SPEED_MPS=3.0). Constants are McQueen-specific (toy car); calibration note in §8.

## 6. Why there is no action head (the falsification, VERIFIED 2026-08-17)

The repo's original `models/` contract (`extract_action_subgraph.py` output names
`mul_48/linear_80/mul_41`; `action_adapter.py` weights
`on_policy_model.temporal_hydra.final_layer.action.weight` [4,512] + bias + scale; "874
nodes") was written by the previous agent and NEVER executed (state files marked UNVERIFIED).

API dumps of every public-era comma export (2026-08-17):

| Export | Size | SHA-256 (verified) | Nodes | API style | Action head |
|---|---|---|---|---|---|
| v0.8.11 (2021) | 56,707,084 | `43d36248…f40588` | 356 | input_imgs/desire/initial_state | NO |
| "v0.8.16" mystery file | 95,165,081 | `15d9eb01…f4eca` | 389 | input_imgs/desire/initial_state | NO |
| v0.9.4 (2023) | 47,501,059 | `d7f95f6b…ffaf8a8` | 408 | input_imgs/desire[1,100,8]/features_buffer[1,99,128] | NO |
| 2026 master driving_supercombo | 60,881,999 | `659727c4…f8009b` | 351 | img/big_img/features_buffer/desire_pulse/traffic_convention/action_t | NO |

Comma has always controlled from the plan (openpilot master `modeld.py`
`get_action_from_model`: plan-derived curvature/accel; the `'action' in model_output`
branch exists only for future/alternate model versions). DECISION 029 records this finding.

## 7. Code (repo `models/`, deployed to RTX `~/mcqueen/models/`)

| File | Role | 2026-08-17 change |
|---|---|---|
| `action_adapter.py` | `FrozenActionModel` (onnx2pytorch, frozen trunk) + `action_to_command_torch` + `rgb_to_supercombo_yuv` | Rewritten: full-model conversion, frozen (0 trainable), plan-derived action via §5 math, slice layout from model metadata |
| `smoke_frozen_action.py` | smoke test (synthetic frames, temporal step-2) | Updated: 0 trainable expected; full model path |
| `extract_action_subgraph.py` | identity re-export of the 6-input→`outputs` graph | Updated: documents the falsified contract |
| `train_frozen_action.py` | (future) training script | UNTOUCHED — pending the open decision |

Runtime flow (per smoke): build 6-channel YUV stack (2 frames) → forward → slice
hidden/plan → action → convert to steer/throttle → roll hidden into features_buffer.

## 8. Verification evidence (2026-08-17, RTX, `~/mcqueen/models/`)

SMOKE PASSED:
- device: cuda (RTX)
- frozen trunk: 29,996,510 params, 0 trainable
- action (1,4) fp16, hidden (1,512) fp16, plan (1,33,3) fp16
- steer=-0.0301, throttle=+0.1924 on synthetic random frames — nonzero output proves real
  graph execution (not zeros)
- temporal step-2 with rolled features_buffer: OK

Not yet measured (do not claim): real-frame inference latency on RTX, end-to-end
capture→control latency, driving quality, calibration of CAR_LENGTH/MAX_STEER_ANGLE/MAX_SPEED.

## 9. Open decisions / next steps

1. **USER DECISION (blocking)**: (a) ship frozen plan-based control as-is (works now) vs
   (b) add a custom small trainable head on features[512] (restores DECISION 027 retrain
   intent; needs driving data). Recommendation: (a) now, (b) later if driving feel demands.
2. Real-frame run: `smoke_frozen_action.py --onnx <model> --real_frame <png>` with a Jetson
   frame (256×512 RGB).
3. RTX inference latency measurement (stage RTX_INFERENCE in benchmark-v2 terms).
4. Jetson integration: model output → safety gate → servo/motor (existing safety contract).
5. Calibration of CAR_LENGTH_M / MAX_STEER_ANGLE_RAD / MAX_SPEED_MPS for the actual chassis.
6. `train_frozen_action.py` rework ONLY if decision (b).

## 10. Sessions/references

- DECISION 027 (2026-08-16): openpilot pipeline = THE model (user mandate).
- DECISION 029 (2026-08-17): 2026-master driving_supercombo = THE model; plan-derived
  control; action-head contract falsified.
- Session 3i part 3 (2026-08-17): full verification + code rewrite + smoke (see
  `.mcqueen/SESSION_LOG.md`).
- `.mcqueen/VERIFIED_FACTS.md` (top entries): model identity, falsification, smoke facts.
- Model files on RTX `~/mcqueen/models/` (see §3).