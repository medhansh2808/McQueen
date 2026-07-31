#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_NAME="yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob"
PYTHON="/home/arduino/McQueen/teleop/.venv/bin/python3"

mkdir -p /home/arduino/McQueen/vision /home/arduino/McQueen/models
cp "$SCRIPT_DIR/goal2_logger.py" /home/arduino/McQueen/vision/goal2_logger.py
cp "$SCRIPT_DIR/model/$MODEL_NAME" /home/arduino/McQueen/models/$MODEL_NAME
chmod +x /home/arduino/McQueen/vision/goal2_logger.py

"$PYTHON" -m py_compile /home/arduino/McQueen/vision/goal2_logger.py

sudo cp "$SCRIPT_DIR/../../services/mcqueen-goal2.service" \
  /etc/systemd/system/mcqueen-goal2.service
sudo systemctl daemon-reload
sudo systemctl enable mcqueen-goal2.service
sudo systemctl restart mcqueen-goal2.service
sleep 10
sudo systemctl --no-pager --full status mcqueen-goal2.service
