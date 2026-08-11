"""Jetson-side safety gate for remote McQueen predictions.

The remote model NEVER grants authority. Phone/UI state must explicitly place
McQueen in AUTO before predictions are allowed to reach actuators.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import Prediction


@dataclass(frozen=True)
class SafetyConfig:
    servo_min_deg: float = 45.0
    servo_center_deg: float = 90.0
    servo_max_deg: float = 115.0
    forward_max_pwm: int = 100
    reverse_max_pwm: int = 70
    prediction_timeout_ms: float = 250.0


@dataclass(frozen=True)
class SafeCommand:
    servo_angle_deg: float
    motor_pwm: int
    auto_active: bool
    reason: str


class AutoSafetyGate:
    """Apply authority, freshness, range and speed-cap rules on the Jetson."""

    def __init__(self, config: SafetyConfig | None = None) -> None:
        self.config = config or SafetyConfig()
        self._auto_authorized = False

    @property
    def auto_authorized(self) -> bool:
        return self._auto_authorized

    def set_auto_authorized(self, authorized: bool) -> None:
        self._auto_authorized = bool(authorized)

    def safe_stop(self, reason: str) -> SafeCommand:
        return SafeCommand(
            servo_angle_deg=self.config.servo_center_deg,
            motor_pwm=0,
            auto_active=False,
            reason=reason,
        )

    def apply(
        self,
        prediction: Prediction,
        receive_mono_ns: int,
    ) -> SafeCommand:
        if not self._auto_authorized:
            return self.safe_stop("auto_not_authorized")

        age_ms = (receive_mono_ns - prediction.capture_mono_ns) / 1_000_000.0
        if age_ms < 0:
            return self.safe_stop("invalid_timestamp")
        if age_ms > self.config.prediction_timeout_ms:
            self._auto_authorized = False
            return self.safe_stop("stale_prediction")

        servo = min(
            self.config.servo_max_deg,
            max(self.config.servo_min_deg, float(prediction.servo_angle_deg)),
        )

        pwm = int(round(prediction.motor_pwm))
        if pwm >= 0:
            pwm = min(pwm, self.config.forward_max_pwm)
        else:
            pwm = max(pwm, -self.config.reverse_max_pwm)

        return SafeCommand(
            servo_angle_deg=servo,
            motor_pwm=pwm,
            auto_active=True,
            reason="ok",
        )
