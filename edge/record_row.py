"""Pure helper for constructing canonical McQueen dataset-v2 rows.

No OpenCV, GPIO, PyTorch or Jetson dependencies.
Python 3.6 compatible.
"""

SCHEMA_VERSION = "mcqueen-driving-spool-v2"
TASK = "Imitate expert driving"


def build_frame_row(
    frame_index,
    relative_rgb_path,
    capture_monotonic_ns,
    timestamp_unix_s,
    servo_angle_deg,
    motor_pwm,
    drive_state,
    encoder,
):
    return {
        "schema_version": SCHEMA_VERSION,
        "frame_index": int(frame_index),
        "capture_monotonic_ns": int(capture_monotonic_ns),
        "timestamp_unix_s": float(timestamp_unix_s),

        # Temporary compatibility aliases for older tools.
        "timestamp": int(float(timestamp_unix_s) * 1000.0),
        "timestamp_s": float(timestamp_unix_s),

        "observation.images.front_rgb": str(relative_rgb_path),

        "action.servo_angle_deg": int(servo_angle_deg),
        "action.motor_pwm": int(motor_pwm),

        "observation.wheels.encoder_valid":
            bool(encoder["encoder_valid"]),
        "observation.wheels.left_ticks_total":
            int(encoder["left_ticks_total"]),
        "observation.wheels.right_ticks_total":
            int(encoder["right_ticks_total"]),
        "observation.wheels.left_ticks_delta":
            int(encoder["left_ticks_delta"]),
        "observation.wheels.right_ticks_delta":
            int(encoder["right_ticks_delta"]),
        "observation.wheels.left_ticks_per_s":
            float(encoder["left_ticks_per_s"]),
        "observation.wheels.right_ticks_per_s":
            float(encoder["right_ticks_per_s"]),
        "observation.wheels.sample_dt_s":
            float(encoder["sample_dt_s"]),

        "task": TASK,

        "mcqueen.raw.steering_command":
            int(drive_state["steering"]),
        "mcqueen.raw.throttle_command":
            int(drive_state["throttle"]),
        "mcqueen.raw.motor_enabled":
            bool(drive_state["motor_enabled"]),
    }
