# McQueen — Next Lab Runbook

This runbook intentionally avoids destructive or speculative steps.

## 1. Laptop cold-start preflight

Boot the laptop with no manual McQueen commands. Connect the Lenovo webcam, then run:

```bash
bash ~/McQueenWork/McQueen/tools/preflight/laptop_lab_preflight.sh
```

Expected:
- `mcqueen-recorder.path`: enabled + active
- `mcqueen-discovery.service`: enabled + active
- webcam stable path exists
- `mcqueen-recorder.service`: active
- UDP 5006 discovery listener
- UDP 5007 recorder/control proxy when camera is present
- TCP 8080 phone LOG endpoint when camera is present

## 2. Jetson inspection BEFORE syncing

Connect Jetson micro-USB to laptop, power Jetson, SSH in, then run:

```bash
bash ~/McQueen/tools/preflight/jetson_repo_inspect.sh
```

Do **not** blindly `git pull` yet. The Jetson previously had local branch history that may differ from origin. Use the inspection output to choose a safe sync.

After safe sync, the Jetson must contain the current steering contract:
- phone left `-1000` -> `45°`
- center `0` -> `90°`
- phone right `+1000` -> `115°`

Then restart `mcqueen-edge.service` and physically verify left/center/right with wheels off the ground.

## 3. End-to-end phone test

With camera connected and Jetson reachable:
1. Open KACHOW.
2. AUTO discovery should find the laptop without manually entering its IP.
3. TAKE.
4. ARM.
5. Verify steering direction physically.
6. Press LOG.
7. Drive/command briefly.
8. Press LOG again.
9. Validate the newest episode.

Do not use old pre-fix driving episodes for training if their steering semantics disagree with the corrected mapping.

## 4. 4090 inspection BEFORE installing anything

SSH to the 4090 machine and run:

```bash
bash ~/McQueen/tools/preflight/gpu4090_preflight.sh
```

The machine previously showed:
- RTX 4090
- an existing `lerobot` conda environment
- another active GPU process
- only about 37 GB free storage

Therefore do not reinstall LeRobot/CUDA/Torch or kill jobs until the fresh preflight is reviewed.

## 5. LeRobot conversion contract

Current intended canonical LeRobot action:
- `action[0] = servo_angle_deg`
- `action[1] = motor_pwm`
- no normalization baked into conversion
- `robot_type = mcqueen_jetson_nano`

Run:

```bash
python3 ~/McQueenWork/McQueen/tools/preflight/check_converter_contract.py
```

Actual conversion on the 4090 should only be attempted after the installed LeRobot version/API is verified.

## 6. Training

Do not prepare a final training command until:
- LeRobot version is known on the 4090,
- the converter is proven compatible with that version,
- one converted episode is inspected,
- GPU availability and disk space are acceptable.

This avoids another unnecessary local/remote CUDA installation or version mismatch.
