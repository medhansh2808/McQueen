# PROJECT_INDEX.md — McQueen compact repository map

Only files relevant to understanding/operating McQueen. For details, read the file itself.

## Root
- `AGENTS.md` — authoritative agent contract (sections A–Q). READ FIRST.
- `README.md` — project overview.
- `README_NEXT_LAB_BUNDLE.txt` — what to carry to the lab.
- `pyproject.toml` — Python project metadata.

## Docs (`docs/`)
- `ARCHITECTURE.md` — high-level architecture.
- `PROJECT_STATUS_2026-08-12.md` — current standing, proof separation, remaining gaps.
- `HARDWARE_MILESTONES_2026-08-11.md` — lab-verified hardware results + explicit NOT-counted list.
- `HOME_VALIDATED_2026-08-12.md` — laptop-validated software (not hardware proof).
- `NEXT_LAB_RUNBOOK.md` — the lab sequence (Phase A/B).
- `REALTIME_INFERENCE_V0.md` / `REALTIME_INFERENCE_V1.md` — realtime architecture + safety target.
- `full_loop_benchmark_v2.md` — benchmark stages, exact frame association, latency clock.
- `model_architecture_v1.md` — policy model architecture.
- `BACKBONE_INTEGRATION_PLAN.md` — PPGeo ResNet-34 → Drive-JEPA ViT plan.
- `dataset_schema_v2.md` — dataset-v2 schema.
- `evidence/2026-08-11-direct-wan-control.txt` — sanitized latency evidence.

## ML (`mcqueen_ml/`)
- `dataset/schema_v2.py` — spool schema v2 (dependency-free).
- `dataset/convert_spool.py` — v1/v2 → LeRobot converter.
- `dataset/validate_spool.py` — raw spool validation.
- `training/temporal_index_v2.py` — six-frame indexing (no leakage, neutral padding).
- `training/temporal_policy_v2.py` — backbone-agnostic temporal Transformer core.
- `training/dataset_v2.py` — temporal dataset wrapper.
- `training/model_config_v2.py` — model config.
- `training/smoke_train.py`, `smoke_temporal_policy_v2.py` — smoke tests.
- `deployment/protocol.py` — RTX↔Jetson prediction protocol.
- `deployment/safety.py` — safety gate (authority, freshness, ranges).

## Robot — Jetson (`robot/jetson_nano/mcqueen_edge/`)
- `app.py` — edge app entrypoint (UDP + HTTP).
- `server.py` — UDP teleop server (port 5007).
- `http_server.py` — HTTP status server (port 8080).
- `protocol.py` — phone↔Jetson packet protocol.
- `drive.py` — drive backend abstraction (Mock / Jetson GPIO).
- `jetson_gpio.py` — real GPIO backend (TB6612, MG995).
- `recorder.py` / `record_row.py` — raw dataset recording (spool v2).
- `encoder_source.py` — wheel encoder source (currently NullEncoderSource).

## Tools (`tools/`)
- `mcqueen_discovery.py` — laptop auto-discovery (UDP 5006).
- `mcqueen_recorder.py` — laptop-side recording helper.
- `realtime/direct_udp_peer.py` — NAT-punch direct UDP peer.
- `realtime/kachow_probe.py` — live phone→Jetson probe.
- `realtime/full_loop_contract_v2.py` — benchmark-v2 stage bookkeeping.
- `realtime/synthetic_full_loop_v2.py` — synthetic loop (software only).
- `preflight/laptop_lab_preflight.sh`, `jetson_no_drivetrain_preflight.sh`,
  `jetson_repo_inspect.sh`, `rtx4090_preflight_v2.sh`, `gpu4090_preflight.sh` — read-only checks.
- `tailscale/` — tailscale install/verify helpers.

## Tests (`tests/`)
- `test_jetson_protocol.py`, `test_jetson_drive.py`, `test_jetson_edge_app.py`,
  `test_jetson_udp_server.py`, `test_jetson_http_server.py` (⚠ known stale/failing),
  `test_jetson_backend_selection.py`, `test_jetson_gpio_backend.py`,
  `test_jetson_steering_mapping.py`, `test_realtime_contract.py`.
- ML tests live next to modules (`mcqueen_ml/**/test_*.py`).

## Deploy (`deploy/systemd/`)
- `mcqueen-edge.service` — edge runtime service.
- `mcqueen-recorder.service` + `.path` — recorder service.
- `mcqueen-discovery.service` — discovery responder.

## Hardware (`hardware/`)
- MCU sketches / wiring / CAD for drivetrain (encoder, servo, motor) — mostly Phase B.

## Android app (`apps/android/KachowV8/`)
- `app/src/main/java/com/kartik/mcqueencontroller/Protocol.kt` — phone↔Jetson packets.
- `.../UdpController.kt` — UDP send path.
- `.../TelemetryMirror.kt`, `DiscoveryClient.kt`, `DualRcSliderView.kt`, etc.

## Local-only (NOT in git)
- `context stuff for understanding the mcqueen project/` — user's context dumps (Supermind
  master context, working rules, lab sequences).
- `~/Downloads/mcqueen_wan_direct_p2p/` — realtime WAN pipeline (broker + gst sender/receiver).
- `~/Downloads/mcqueen_rtx_candidate_20260812/` — RTX temporal-candidate test package.
- `.mcqueen/` — agent state (this system), untracked until user authorizes commit.
