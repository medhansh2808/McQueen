#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/McQueen/teleop"
FQBN="arduino:zephyr:unoq"

echo "=== McQueen UNO Q teleop installer ==="

mkdir -p \
  "${ROOT}/sketch/UnoQDrive" \
  "${ROOT}/linux" \
  "${ROOT}/scripts"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cp -f \
  "${SCRIPT_DIR}/sketch/UnoQDrive/UnoQDrive.ino" \
  "${ROOT}/sketch/UnoQDrive/UnoQDrive.ino"

cp -f \
  "${SCRIPT_DIR}/linux/unoq_udp_receiver.py" \
  "${ROOT}/linux/unoq_udp_receiver.py"

cp -f \
  "${SCRIPT_DIR}/tests/direct_bridge_test.py" \
  "${ROOT}/linux/direct_bridge_test.py"

chmod +x "${ROOT}/linux/"*.py

echo
echo "=== Arduino core ==="
arduino-cli core update-index
arduino-cli core list

if ! arduino-cli core list | grep -q '^arduino:zephyr'; then
  echo "Installing Arduino Zephyr core..."
  arduino-cli core install arduino:zephyr
fi

echo
echo "=== Sketch libraries ==="
arduino-cli lib update-index
arduino-cli lib install "Arduino_RouterBridge"
arduino-cli lib install "Servo"

echo
echo "=== Python teleop environment ==="
python3 -m venv --system-site-packages "${ROOT}/.venv"
source "${ROOT}/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel

if ! python -c 'from arduino.app_utils import Bridge' >/dev/null 2>&1; then
  echo "Installing Arduino App Bricks from the official Arduino repository..."
  python -m pip install \
    "git+https://github.com/arduino/app-bricks-py.git@main"
fi

python - <<'PY'
from arduino.app_utils import Bridge
print("Arduino Python Bridge import: OK")
PY

echo
echo "=== Compile MCU sketch ==="
arduino-cli compile \
  --fqbn "${FQBN}" \
  "${ROOT}/sketch/UnoQDrive"

echo
echo "INSTALL + COMPILE COMPLETE"
echo "Sketch: ${ROOT}/sketch/UnoQDrive"
echo "Receiver: ${ROOT}/linux/unoq_udp_receiver.py"
