"""Dependency-free configuration for McQueen temporal driving policy v1."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_BACKBONES = (
    "tiny",            # TinyVisualBackbone — smoke/latency stand-in, not production
    "ppgeo_resnet34",
    "drive_jepa_vit",
)

ACTION_NAMES = (
    "servo_angle_deg",
    "motor_pwm",
)

WHEEL_NAMES = (
    "encoder_valid",
    "left_ticks_per_s",
    "right_ticks_per_s",
)


@dataclass(frozen=True)
class TemporalPolicyConfig:
    backbone: str = "ppgeo_resnet34"
    history: int = 6
    model_dim: int = 512
    transformer_layers: int = 4
    attention_heads: int = 8
    feedforward_dim: int = 1024
    dropout: float = 0.1
    action_dim: int = 2
    wheel_dim: int = 3

    def validate(self) -> None:
        if self.backbone not in SUPPORTED_BACKBONES:
            raise ValueError("unsupported backbone: {!r}".format(self.backbone))
        if self.history < 2:
            raise ValueError("history must be >= 2")
        if self.model_dim <= 0:
            raise ValueError("model_dim must be > 0")
        if self.attention_heads <= 0:
            raise ValueError("attention_heads must be > 0")
        if self.model_dim % self.attention_heads:
            raise ValueError("model_dim must be divisible by attention_heads")
        if self.transformer_layers <= 0:
            raise ValueError("transformer_layers must be > 0")
        if self.feedforward_dim < self.model_dim:
            raise ValueError("feedforward_dim must be >= model_dim")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.action_dim != len(ACTION_NAMES):
            raise ValueError("action_dim does not match canonical action")
        if self.wheel_dim != len(WHEEL_NAMES):
            raise ValueError("wheel_dim does not match canonical wheel state")


DEFAULT_POLICY_CONFIG = TemporalPolicyConfig()
DEFAULT_POLICY_CONFIG.validate()
