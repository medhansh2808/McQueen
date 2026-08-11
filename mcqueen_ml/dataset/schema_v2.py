"""McQueen canonical raw driving dataset v2.

Dependency-free so this contract can be validated on a laptop without PyTorch.
"""

SCHEMA_VERSION = "mcqueen-driving-spool-v2"

REQUIRED_FIELDS = (
    "schema_version",
    "frame_index",
    "capture_monotonic_ns",
    "timestamp_unix_s",
    "observation.images.front_rgb",
    "action.servo_angle_deg",
    "action.motor_pwm",
    "observation.wheels.encoder_valid",
    "observation.wheels.left_ticks_total",
    "observation.wheels.right_ticks_total",
    "observation.wheels.left_ticks_delta",
    "observation.wheels.right_ticks_delta",
    "observation.wheels.left_ticks_per_s",
    "observation.wheels.right_ticks_per_s",
    "observation.wheels.sample_dt_s",
    "mcqueen.raw.steering_command",
    "mcqueen.raw.throttle_command",
    "mcqueen.raw.motor_enabled",
)


def validate_frame(row):
    """Return a list of schema errors. Empty list means valid."""
    errors = []

    missing = [key for key in REQUIRED_FIELDS if key not in row]
    if missing:
        errors.append("missing fields: {}".format(", ".join(missing)))
        return errors

    if row["schema_version"] != SCHEMA_VERSION:
        errors.append(
            "schema_version must be {!r}".format(SCHEMA_VERSION)
        )

    try:
        frame_index = int(row["frame_index"])
        if frame_index < 0:
            errors.append("frame_index must be >= 0")
    except Exception:
        errors.append("frame_index must be an integer")

    try:
        mono = int(row["capture_monotonic_ns"])
        if mono <= 0:
            errors.append("capture_monotonic_ns must be > 0")
    except Exception:
        errors.append("capture_monotonic_ns must be an integer")

    try:
        servo = float(row["action.servo_angle_deg"])
        if not 45.0 <= servo <= 115.0:
            errors.append("servo angle outside McQueen physical range")
    except Exception:
        errors.append("servo angle must be numeric")

    try:
        pwm = int(row["action.motor_pwm"])
        if not -255 <= pwm <= 255:
            errors.append("motor PWM outside dataset range")
    except Exception:
        errors.append("motor PWM must be numeric")

    if not isinstance(
        row["observation.wheels.encoder_valid"], bool
    ):
        errors.append("encoder_valid must be boolean")

    return errors


def validate_sequence(rows):
    """Validate frames plus strictly increasing order/timestamps."""
    errors = []

    previous_index = None
    previous_mono = None

    for position, row in enumerate(rows):
        for error in validate_frame(row):
            errors.append("row {}: {}".format(position, error))

        try:
            index = int(row["frame_index"])
            mono = int(row["capture_monotonic_ns"])
        except Exception:
            continue

        if previous_index is not None and index != previous_index + 1:
            errors.append(
                "row {}: non-contiguous frame_index".format(position)
            )

        if previous_mono is not None and mono <= previous_mono:
            errors.append(
                "row {}: monotonic timestamp did not increase".format(position)
            )

        previous_index = index
        previous_mono = mono

    return errors
