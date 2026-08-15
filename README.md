# McQueen

McQueen is an autonomous RC-car / small-UGV project centered on human demonstrations,
temporal vision and RTX-first inference.

## Current roles

- **Phone / KACHOW:** human teleoperation, manual takeover, E-stop/AUTO authority.
- **Jetson Nano 2GB:** camera capture, hardware video encode, phone runtime, raw recording,
  safety/failsafe and actuator I/O.
- **RTX 4090:** first target for training and autonomous inference.
- **Laptop:** development, SSH/debugging, Git, dataset inspection and software validation.
- **Camera:** Lenovo FHD webcam; known target MJPEG 1280x720 @ 30 fps.

## Autonomy target

    6 recent RGB observations
      + previous actions
      + wheel encoder state
      -> driving-pretrained visual encoder
      -> temporal Transformer
      -> [servo_angle_deg, signed_motor_pwm]

The first planned visual-backbone experiment is PPGeo ResNet-34; Drive-JEPA is a second
experiment. Neither checkpoint integration is presented as proven until it runs in the intended
RTX environment.

## Realtime transport direction

- video: Jetson hardware H.264 -> RTP -> direct UDP (peer-to-peer, STUN-punched)
- signaling: broker only for the NAT punch / discovery stage
- autonomous action return: direct UDP on the same punched path
- full-loop association: exact `frame_id` + Jetson monotonic capture timestamp

## Steering contract

- phone `-1000` -> `115 deg` left
- phone `0` -> `90 deg` center
- phone `+1000` -> `45 deg` right

## Dataset

Canonical raw format: `mcqueen-driving-spool-v2`.

See `docs/dataset_schema_v2.md`.

## Project status

Proof levels are intentionally separated; see the docs index (`docs/README.md`) for
architecture, setup, model and benchmark documentation. Hardware-verified milestones and
per-session evidence are maintained locally (not part of the public repo).

## Contributors

- Kartik Tagore (`@kt-fr`)
- Medhansh Abhilash (`@medhansh2808`)
