"""RTX smoke test for the McQueen temporal policy core."""

import torch

from mcqueen_ml.training.model_config_v2 import TemporalPolicyConfig
from mcqueen_ml.training.temporal_policy_v2 import (
    TemporalDrivingPolicy,
    TinyVisualBackbone,
)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = TemporalPolicyConfig(
        history=6,
        model_dim=512,
        transformer_layers=4,
        attention_heads=8,
        feedforward_dim=1024,
    )
    backbone = TinyVisualBackbone()
    model = TemporalDrivingPolicy(
        backbone,
        visual_dim=backbone.output_dim,
        config=config,
    ).to(device)

    frames = torch.rand(2, 6, 3, 224, 384, device=device)
    wheels = torch.rand(2, 6, 3, device=device)
    previous = torch.rand(2, 6, 2, device=device)

    with torch.no_grad():
        output = model(frames, wheels, previous)

    params = sum(p.numel() for p in model.parameters())
    print("DEVICE", device)
    print("OUTPUT_SHAPE", tuple(output.shape))
    print("PARAMETERS", params)
    print("✅ TEMPORAL POLICY CORE SMOKE PASS")


if __name__ == "__main__":
    main()
