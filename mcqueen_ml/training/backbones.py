"""Visual backbone adapters for the McQueen temporal driving policy.

Each adapter fulfills the ``VisualBackbone`` protocol (see
``temporal_policy_v2.py``): an ``nn.Module`` exposing ``output_dim`` and
mapping ``[N, 3, H, W]`` RGB frames to ``[N, output_dim]`` features.

``torchvision`` is imported lazily (inside construction) so modules that
import this file stay importable on machines without torchvision.
"""

from __future__ import annotations

import os

import torch
import torch.nn as nn


class PPGeoResNet34Backbone(nn.Module):
    """ResNet-34 visual encoder weights released by PPGeo (OpenDriveLab).

    The PPGeo stage-2 checkpoint at
    ``MCQUEEN_PPGEO_CKPT`` (default:
    ``~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth``) is a plain
    torchvision ResNet-34 state dict (keys ``conv1.*``/``bn1.*``/
    ``layer1..4.*``/``fc.*``, 218 keys, verified against the official
    release). The adapter reproduces the PPGeo ``ResnetEncoder(34,
    num_input_images=1)`` forward contract used by the released model:
    ImageNet mean/std normalization, conv1..layer4, global average pool,
    512-dim feature vector.

    The checkpoint file is NOT part of the repository (weights are never
    committed); this adapter deliberately refuses to substitute ImageNet
    weights when the checkpoint is missing.
    """

    output_dim = 512

    def __init__(self, weights_path: str | None = None) -> None:
        super().__init__()
        if weights_path is None:
            weights_path = os.path.join(
                os.path.expanduser("~"),
                "Downloads",
                "mcqueen_ppgeo",
                "ppgeo_visual_encoder.pth",
            )
        if not os.path.isfile(weights_path):
            raise RuntimeError(
                "PPGeo ResNet-34 checkpoint not found at {!r}. "
                "Download it from the OpenDriveLab/PPGeo release "
                "(google drive id 1GAeLgT3Bd_koN9bRPDU1ksMpMlWfGXbE) or set "
                "MCQUEEN_PPGEO_CKPT. No silent ImageNet fallback.".format(
                    weights_path
                )
            )
        try:
            import torchvision.models as tvm
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "torchvision required for PPGeoResNet34Backbone"
            ) from exc

        self.register_buffer(
            "_mean",
            torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1),
            persistent=False,
        )
        self.register_buffer(
            "_std",
            torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1),
            persistent=False,
        )

        self.net = tvm.resnet34(weights=None)
        state_dict = torch.load(weights_path, map_location="cpu")["state_dict"]
        self.net.load_state_dict(state_dict, strict=True)
        self.net.fc = nn.Identity()  # backbone only; fc was ImageNet head

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        x = (images - self._mean.to(images.device)) / self._std.to(images.device)
        x = self.net.conv1(x)
        x = self.net.bn1(x)
        x = self.net.relu(x)
        x = self.net.maxpool(x)
        x = self.net.layer1(x)
        x = self.net.layer2(x)
        x = self.net.layer3(x)
        x = self.net.layer4(x)
        x = self.net.avgpool(x)
        return x.flatten(1)
