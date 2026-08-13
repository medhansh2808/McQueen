# McQueen project status — 2026-08-12 home closeout

Proof levels are deliberately separated.

## A. Hardware/network-interface verified in the 2026-08-11 lab session

See `HARDWARE_MILESTONES_2026-08-11.md`.

Only the following are counted there:
1. real Jetson <-> real RTX 4090 direct-WAN UDP control return: 60/60 ACKs,
   p50 43.1 ms / p95 70.4 ms RTT, Jetson dry-run only;
2. real Lenovo camera -> Jetson hardware H.264 -> WebRTC -> RTX decode/appsink ->
   CUDA/PyTorch dummy action on the successful local lab route;
3. real KACHOW phone -> real Jetson command parsing with forward/reverse and steering extremes,
   mock/no-GPIO backend.

No home/synthetic test is a hardware milestone.

## B. Home-validated software/runtime

See `HOME_VALIDATED_2026-08-12.md`.

The closeout validates dataset-v2, legacy-v1 compatibility, temporal indexing, benchmark-v2
bookkeeping, the backbone-agnostic PyTorch temporal core, local LeRobot conversion/reload, and a
synthetic converted-data training step using the already-installed home environment.

These are software/runtime validations, not car-hardware milestones.

## C. Intended policy

    6 RGB observations
      + previous actions
      + wheel state
      -> driving-pretrained visual encoder
      -> temporal Transformer
      -> MLP
      -> [servo_angle_deg, signed_motor_pwm]

Planned visual-backbone experiments:
1. PPGeo ResNet-34
2. Drive-JEPA ViT

Neither checkpoint adapter is claimed as runtime-proven yet.

## D. Runtime responsibilities

Phone/KACHOW:
- manual teleop
- manual takeover / E-stop authority
- AUTO authorization

Jetson:
- camera capture and hardware encode
- phone teleop runtime
- raw dataset recording
- frame IDs / monotonic capture timestamps
- safety/failsafe
- actuator I/O
- future encoder GPIO input

RTX 4090:
- receive/decode video
- temporal-policy inference
- direct-UDP action return
- training/evaluation

Laptop:
- development/debug/Git/orchestration
- home software validation

## E. Remaining proof gaps

Still requires lab/RTX/drivetrain hardware:
- verify/restart live `mcqueen-edge.service`
- real camera/WebRTC/RTX benchmark-v2 run
- authoritative separate-WAN capture -> prediction-return latency
- RTX 4090 temporal-core smoke/training test
- PPGeo checkpoint adapter and forward pass
- Drive-JEPA adapter and forward pass
- encoder voltage/channel/pin/direction/counts-per-revolution verification
- physical servo/motor verification after current software state
- serious human-demonstration dataset
- trained closed-loop policy
- autonomous unknown-environment navigation
