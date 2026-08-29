"""Hardware-independent drive safety/controller layer for McQueen.

This file intentionally contains no Jetson.GPIO imports so it can be tested on
a laptop. A real Jetson GPIO/PWM backend will be plugged in later.
"""

import time


class MockDriveBackend:
    """In-memory backend used by laptop tests."""

    def __init__(self):
        self.calls = []

    def apply(self, steering, throttle, motor_enabled):
        self.calls.append(
            ("apply", int(steering), int(throttle), bool(motor_enabled))
        )

    def emergency_stop(self):
        self.calls.append(("estop",))


class DriveController:
    """Applies phone commands with session, sequence and timeout safety."""

    def __init__(self, backend, failsafe_seconds=0.300):
        self.backend = backend
        self.failsafe_seconds = float(failsafe_seconds)

        self.session = ""
        self.session_armed = False
        self.resume_required = False
        self.last_sequence = -1
        self.last_command_monotonic = None

        self.steering = 0
        self.throttle = 0
        self.motor_enabled = False
        self.failsafe = True
        self.failsafe_reason = "startup"

    def _safe_stop(self, reason):
        self.steering = 0
        self.throttle = 0
        self.motor_enabled = False
        self.failsafe = True
        self.failsafe_reason = str(reason)
        self.backend.emergency_stop()

    def _begin_session(self, session):
        self.session = str(session)
        self.session_armed = False
        self.resume_required = False
        self.last_sequence = -1
        self.last_command_monotonic = None
        self._safe_stop("new session")

    def handle_packet(self, packet, now=None):
        """Handle a parsed packet from protocol.parse_phone_packet().

        Returns a short result string useful for logging/testing.
        """
        if packet is None:
            return "invalid"

        if now is None:
            now = time.monotonic()

        session = packet["session"]
        sequence = int(packet["sequence"])
        packet_type = packet["type"]

        if session != self.session:
            self._begin_session(session)

        if sequence <= self.last_sequence:
            return "stale"

        self.last_sequence = sequence

        if packet_type == "H":
            return "hello"

        if packet_type == "E":
            self.session_armed = False
            self._safe_stop("phone estop")
            return "estop"

        if packet_type == "R":
            if self.resume_required:
                self.resume_required = False
                return "resume"
            return "resume-idle"

        if packet_type != "C":
            return "invalid"

        steering = int(packet["steering"])
        throttle = int(packet["throttle"])
        motor_enabled = bool(packet["motor_enabled"])

        if self.resume_required:
            # A neutral command implicitly resumes: the app auto-sends
            # (0,0) while FAILSAFE, so the gate clears by itself after a
            # link gap instead of requiring a manual RESUME. Falling
            # through lets this same neutral re-arm the session. Non-neutral
            # commands are still refused until the gate clears.
            if steering == 0 and throttle == 0:
                self.resume_required = False
            else:
                return "resume-required"

        # Match the proven UNO-Q behavior: every new phone session must first
        # send a neutral command before motion is accepted.
        if not self.session_armed:
            if steering == 0 and throttle == 0:
                self.session_armed = True
            else:
                return "awaiting-neutral"

        effective_motor_enabled = bool(motor_enabled or throttle != 0)

        self.backend.apply(
            steering=steering,
            throttle=throttle,
            motor_enabled=effective_motor_enabled,
        )

        self.steering = steering
        self.throttle = throttle
        self.motor_enabled = effective_motor_enabled
        self.last_command_monotonic = float(now)
        self.failsafe = False
        self.failsafe_reason = ""

        return "applied"

    def enforce_failsafe(self, now=None):
        """Stop the car if no valid command arrived within the timeout."""
        if now is None:
            now = time.monotonic()

        if self.last_command_monotonic is None:
            return False

        if self.failsafe:
            return False

        if float(now) - self.last_command_monotonic > self.failsafe_seconds:
            self.resume_required = True
            self.session_armed = False
            self._safe_stop("command timeout")
            return True

        return False

    def emergency_stop(self, reason="manual estop"):
        self.session_armed = False
        self._safe_stop(reason)

    def snapshot(self):
        return {
            "session": self.session,
            "session_armed": self.session_armed,
            "resume_required": self.resume_required,
            "last_sequence": self.last_sequence,
            "steering": self.steering,
            "throttle": self.throttle,
            "motor_enabled": self.motor_enabled,
            "failsafe": self.failsafe,
            "failsafe_reason": self.failsafe_reason,
        }
