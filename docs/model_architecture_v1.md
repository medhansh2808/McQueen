# McQueen temporal driving policy v1

## Input / target contract

History: 6 observations.

Per step:
- front RGB visual representation
- wheel state: encoder-valid, left ticks/s, right ticks/s
- previous action: previous servo angle and previous motor PWM

Target:
- servo angle in degrees
- signed motor PWM

## Temporal core

Initial configuration:
- model dimension 512
- 4 Transformer encoder layers
- 8 attention heads
- feed-forward dimension 1024
- dropout 0.1

Final temporal token -> MLP -> 2D action.

## No target-action leakage

For target frame `t`, state may use action `t-1` but never action `t`.
Episode-start / padded previous action is neutral `[90 deg, 0 PWM]`.

This indexing rule is dependency-free tested at home.

## Visual backbone experiments

1. PPGeo ResNet-34
2. Drive-JEPA ViT

These are planned backbone integrations. Neither checkpoint adapter is called validated until it
loads and runs in the real RTX environment.

## Baselines

Older tiny CNN / GRU code is retained outside the committed production path as scratch/reference
until deliberately re-tested.
