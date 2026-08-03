#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ "$(id -un)" != "arduino" ]; then
  echo "Run this as the arduino user, not root."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[1/8] Installing uv (internet required once)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "[1/8] uv already installed: $(uv --version)"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was installed but is not on PATH. Reopen SSH and rerun ./setup.sh"
  exit 1
fi

if [ ! -f models/yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob ]; then
  echo "YOLO model blob is missing."
  exit 1
fi

if [ ! -x /usr/bin/python3 ] || [ "$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.13" ]; then
  echo "System Python 3.13 is required."
  exit 1
fi

printf '[2/8] Creating one uv environment and lock file...\n'
uv lock --python /usr/bin/python3
uv sync --frozen --python /usr/bin/python3

printf '[3/8] Verifying Python dependencies...\n'
.venv/bin/python - <<'PY'
import depthai as dai
import numpy
import PIL
from arduino.app_utils import Bridge

print("DepthAI:", dai.__version__)
print("NumPy:", numpy.__version__)
print("Pillow:", PIL.__version__)
print("Arduino Bridge import: OK")
PY

printf '[4/8] Compiling STM32 firmware...\n'
rm -rf build
mkdir -p build
arduino-cli compile \
  --fqbn arduino:zephyr:unoq \
  --output-dir "$PROJECT_DIR/build" \
  "$PROJECT_DIR/firmware/UnoQDrive"

printf '[5/8] Flashing STM32 firmware...\n'
arduino-cli upload \
  --fqbn arduino:zephyr:unoq \
  --input-dir "$PROJECT_DIR/build" \
  "$PROJECT_DIR/firmware/UnoQDrive"
sleep 6

printf '[6/8] Installing the only two McQueen services...\n'
sudo systemctl disable --now \
  mcqueen-goal2.service \
  mcqueen-teleop.service \
  mcqueen-frame-uploader.service \
  mcqueen-vision.service \
  2>/dev/null || true

sudo install -m 0644 services/mcqueen-mcu.service /etc/systemd/system/mcqueen-mcu.service
sudo install -m 0644 services/mcqueen.service /etc/systemd/system/mcqueen.service
sudo systemctl daemon-reload
sudo systemctl enable mcqueen-mcu.service mcqueen.service

printf '[7/8] Setting local time and starting McQueen...\n'
sudo timedatectl set-timezone Asia/Kolkata
sudo systemctl restart arduino-router.service
sleep 3
sudo systemctl restart mcqueen-mcu.service
sudo systemctl restart mcqueen.service
sleep 10

printf '[8/8] Final checks...\n'
sudo systemctl --no-pager --full status mcqueen-mcu.service mcqueen.service || true

echo
echo "HTTP status:"
curl -fsS http://127.0.0.1:8080/status | .venv/bin/python -m json.tool || true

echo
echo "Setup complete. Do not delete the old files yet; test phone control and one recording first."
