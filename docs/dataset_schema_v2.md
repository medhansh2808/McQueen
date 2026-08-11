# McQueen raw driving dataset v2

Schema ID:

    mcqueen-driving-spool-v2

## Purpose

Each saved camera frame is paired with:

- the human driving command active at capture time
- left/right wheel encoder state
- a monotonic Jetson capture timestamp
- raw KACHOW command values for debugging

The raw dataset remains in physical/control units.
Normalization belongs in training, not recording.

## Canonical per-frame fields

Required:

    schema_version
    frame_index
    capture_monotonic_ns
    timestamp_unix_s

    observation.images.front_rgb

    action.servo_angle_deg
    action.motor_pwm

    observation.wheels.encoder_valid
    observation.wheels.left_ticks_total
    observation.wheels.right_ticks_total
    observation.wheels.left_ticks_delta
    observation.wheels.right_ticks_delta
    observation.wheels.left_ticks_per_s
    observation.wheels.right_ticks_per_s
    observation.wheels.sample_dt_s

    mcqueen.raw.steering_command
    mcqueen.raw.throttle_command
    mcqueen.raw.motor_enabled

## Action meaning

    action.servo_angle_deg

Physical steering command.

Known McQueen calibration:

    45 deg   = right limit
    90 deg   = center
    115 deg  = left limit

    action.motor_pwm

Signed motor command.

Positive = forward.
Negative = reverse.
Zero = stopped.

The dataset stores the human command actually issued.
Autonomous deployment safety caps are NOT baked into dataset labels.

## Wheel encoders

Raw tick values are canonical.

Do not permanently convert ticks to metres until we have measured:

- encoder counts per motor/output revolution
- gearbox relationship if applicable
- wheel circumference
- left/right encoder direction signs

This prevents incorrect geometry from contaminating the dataset.

If encoder data is unavailable for a frame:

    observation.wheels.encoder_valid = false

and numeric encoder values may be zero.

## Timing

capture_monotonic_ns is generated from the Jetson monotonic clock.

On Jetson Python 3.6:

    int(time.monotonic() * 1_000_000_000)

This field is used for:

- temporal frame spacing
- synchronization
- latency measurements
- stale-data detection

timestamp_unix_s is retained only for human-readable chronology.

## Previous action

Previous action is NOT duplicated in the raw frame.

For frame t the training loader derives:

    previous_action = action at frame t-1

At the first frame of an episode it may use the first action or a neutral action,
depending on the training experiment.

## Temporal training

Windows must never cross episode boundaries.

Example history=6:

    frame t-5
    frame t-4
    frame t-3
    frame t-2
    frame t-1
    frame t

plus recent action history and wheel observations.

## Important rule

Camera image, drive command and wheel observation should be sampled as close to
the same capture instant as practical.
