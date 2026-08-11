# Home-validated software results — 2026-08-12

**Scope rule:** these are home software/runtime checks. They are not included in the
2026-08-11 lab hardware-milestone list.

## Dependency-free contracts

Validated:
- dataset-v2 schema and sequence rules
- synthetic encoder rows
- six-frame temporal indexing
- neutral `[90 deg, 0 PWM]` previous-action padding at episode start
- no target-action leakage
- exact-frame benchmark-v2 bookkeeping

## Home PyTorch runtime

Using the already-existing `mcqueen-laptop` environment, the temporal core is tested on the
home laptop GPU. The test covers:
- temporal dataset wrapper
- `[frames, wheels, previous_actions]` input contract
- Transformer forward pass
- `[servo, PWM]` output shape
- target-action leakage guard
- one optimizer/backpropagation step through the converted synthetic dataset

This proves the backbone-agnostic temporal core can execute/train in PyTorch. It does not prove
PPGeo/Drive-JEPA checkpoint integration and it is not an RTX 4090 performance claim.

## Home LeRobot runtime

The existing home LeRobot installation is used to validate the committed converter on synthetic
raw spools.

Required closeout checks:
- v2 raw spool validates
- legacy v1 raw spool validates
- v2 converts to a local LeRobot dataset and reloads
- v1 converts to a local LeRobot dataset and reloads
- v2 wheel fields survive conversion
- v1 correctly receives invalid/zero wheel placeholders
- converted v2 data can feed the temporal dataset wrapper and a PyTorch training step

## Still not a home proof

Home validation does not prove:
- Jetson camera runtime after reboot
- live WebRTC/WAN pipeline
- RTX 4090 temporal-model runtime
- PPGeo checkpoint loading
- Drive-JEPA checkpoint loading
- encoder electrical interface
- physical actuator behavior
- real driving dataset quality
- autonomous driving
