"""Primary McQueen temporal driving policy.

The policy is intentionally backbone-agnostic. A visual backbone converts each
RGB frame into one feature vector. The temporal policy then combines visual
features, wheel state, and previous actions before predicting the next action.
"""

from __future__ import annotations

from typing import Protocol

import torch
import torch.nn as nn

from .model_config_v2 import TemporalPolicyConfig


class VisualBackbone(Protocol):
    output_dim: int

    def __call__(self, images: torch.Tensor) -> torch.Tensor:
        ...


class TinyVisualBackbone(nn.Module):
    """Small smoke-test backbone. Not the final production visual encoder."""

    output_dim = 128

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=5, stride=2, padding=2),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 96, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(96, 128, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.net(images).flatten(1)


class TemporalDrivingPolicy(nn.Module):
    """RGB history + wheel history + previous actions -> normalized action."""

    def __init__(
        self,
        visual_backbone: nn.Module,
        visual_dim: int,
        config: TemporalPolicyConfig,
    ) -> None:
        super().__init__()
        config.validate()
        self.config = config
        self.visual_backbone = visual_backbone

        self.visual_projection = nn.Sequential(
            nn.Linear(int(visual_dim), config.model_dim),
            nn.LayerNorm(config.model_dim),
        )

        self.state_projection = nn.Sequential(
            nn.Linear(config.wheel_dim + config.action_dim, config.model_dim),
            nn.GELU(),
            nn.Linear(config.model_dim, config.model_dim),
            nn.LayerNorm(config.model_dim),
        )

        self.position = nn.Parameter(
            torch.zeros(1, config.history, config.model_dim)
        )

        layer = nn.TransformerEncoderLayer(
            d_model=config.model_dim,
            nhead=config.attention_heads,
            dim_feedforward=config.feedforward_dim,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.temporal_encoder = nn.TransformerEncoder(
            layer,
            num_layers=config.transformer_layers,
            norm=nn.LayerNorm(config.model_dim),
        )

        self.action_head = nn.Sequential(
            nn.Linear(config.model_dim, config.model_dim // 2),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.model_dim // 2, config.action_dim),
        )

        nn.init.trunc_normal_(self.position, std=0.02)

    def forward(
        self,
        frames: torch.Tensor,
        wheels: torch.Tensor,
        previous_actions: torch.Tensor,
    ) -> torch.Tensor:
        if frames.ndim != 5:
            raise ValueError("frames must be [B, T, C, H, W]")

        batch, steps, channels, height, width = frames.shape
        if steps != self.config.history:
            raise ValueError(
                "expected history {}, got {}".format(
                    self.config.history, steps
                )
            )
        if wheels.shape != (batch, steps, self.config.wheel_dim):
            raise ValueError("wheels must be [B, T, {}]".format(self.config.wheel_dim))
        if previous_actions.shape != (
            batch,
            steps,
            self.config.action_dim,
        ):
            raise ValueError(
                "previous_actions must be [B, T, {}]".format(
                    self.config.action_dim
                )
            )

        flat_frames = frames.reshape(
            batch * steps, channels, height, width
        )
        visual = self.visual_backbone(flat_frames)
        if visual.ndim > 2:
            visual = visual.flatten(2).mean(dim=-1)
        if visual.ndim != 2:
            raise ValueError("visual backbone must return [N, F] features")

        visual = self.visual_projection(visual)
        visual = visual.reshape(batch, steps, self.config.model_dim)

        state = torch.cat([wheels, previous_actions], dim=-1)
        state = self.state_projection(state)

        tokens = visual + state + self.position[:, :steps]
        temporal = self.temporal_encoder(tokens)
        return self.action_head(temporal[:, -1])
