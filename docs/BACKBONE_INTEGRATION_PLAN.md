# Driving-backbone integration plan

Source check performed 2026-08-11 against the official project repositories.

## PPGeo — first experiment

Official repository:
`https://github.com/OpenDriveLab/PPGeo`

The official PPGeo repository describes PPGeo as a self-supervised driving-policy pretraining
framework learned from unlabeled driving videos and publishes a **Visual Encoder (ResNet-34)**
checkpoint. The repository code is Apache-2.0 licensed.

Why first for McQueen:
- the released visual component is a conventional ResNet-34;
- it is directly aligned with driving-video representation learning;
- it should be simpler to isolate as a feature encoder than a full modern driving stack.

RTX integration rule:
1. clone/read the official repo;
2. inspect the actual checkpoint object and state-dict keys;
3. identify the feature tensor/output dimension from code, not guesses;
4. load into an isolated adapter;
5. run one fake 6-frame McQueen batch;
6. measure forward latency/memory;
7. only then commit the adapter.

Do **not** assume torchvision ResNet key names match the released checkpoint before inspection.

## Drive-JEPA — second experiment

Official repository:
`https://github.com/linhanwang/Drive-JEPA`

The official repository describes a ViT encoder pretrained on large-scale driving video using a
V-JEPA objective and provides released checkpoints/cache assets. Its documented environment uses
Python 3.9 and PyTorch 2.1 / CUDA 12.1 for the full project stack.

McQueen integration rule:
- do not mutate the existing working RTX LeRobot/CUDA environment to match Drive-JEPA blindly;
- inspect whether the visual encoder/checkpoint can be loaded independently;
- use an isolated environment if its dependencies conflict;
- keep McQueen's temporal/state/action interface identical when comparing PPGeo vs Drive-JEPA.

## Fair comparison

Same:
- McQueen train/validation/test episode split
- six-frame history
- wheel/action state
- temporal head
- action normalization/loss
- evaluation metrics

Compare:
- held-out action error
- temporal stability
- inference latency
- GPU memory
- later closed-loop driving performance
