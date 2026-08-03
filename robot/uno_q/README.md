# McQueen UNO Q

One project, one `uv` environment, one Python app, one firmware sketch, two services.

## What runs

- `app.py`
  - UDP `5007`: Kachow phone control
  - HTTP `8080`: phone LOG start/stop
  - OAK-D RGB + stereo depth + YOLOv6
  - local 15 Hz episode recording
- `mcqueen-mcu.service`: flashes the STM32 firmware at boot
- `mcqueen.service`: runs the complete Linux app

## Phone settings

When using the UNO Q hotspot:

```text
CAR IP:  192.168.4.1
HOST IP: 192.168.4.1
CAM:     OFF
```

The phone LOG button starts and stops a local episode.

## Dataset

```text
datasets/session_YYYYMMDD_HHMMSS/
├── controls.csv
└── frames/
    ├── frame_000000.jpg
    ├── frame_000000_viz.jpg
    └── ...
```

- `frame_*.jpg`: clean 1920×1080 RGB for training
- `frame_*_viz.jpg`: 1920×540 depth heatmap + RGB/YOLO/X/Y/Z review image
- one CSV row, control sample, clean image and visualization per saved 15 Hz sample
- one phone LOG start/stop is one future LeRobot episode

CSV columns:

```text
timestamp,timestamp_s,frame_index,motor_pwm_sent,servo_angle_sent,camera_frame,visualization_frame,task
```

## Install

The UNO Q needs internet once for `uv` and Python dependencies.

```bash
cd ~/McQueen
./setup.sh
```

## Check

```bash
sudo systemctl status mcqueen-mcu.service mcqueen.service --no-pager
curl -s http://127.0.0.1:8080/status | .venv/bin/python -m json.tool
sudo journalctl -u mcqueen.service -f
```

## Daily use

1. Power the UNO Q and OAK-D.
2. Connect the phone to `KACHOW-CAR`.
3. `AUTO → TAKE → ARM`.
4. Press `LOG`, drive, press `LOG` again.
5. Data is under `/home/arduino/McQueen/datasets`.

## Safety and data rules

- motor failsafe: 300 ms
- servo centre: 80°
- servo detaches 500 ms after returning to centre to prevent idle buzzing
- logging refuses to start without fresh camera data
- logging stops if camera data is stale for over one second
- logging stops below 2 GB free storage
- episodes shorter than one second are deleted
