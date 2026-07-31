#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/McQueen/teleop"
source "${ROOT}/.venv/bin/activate"

python3 - <<'PY'
from arduino.app_utils import Bridge

print("Calling MCU ping...")
print("ping =", Bridge.call("ping"))
print("Sending ESTOP...")
print("estop =", Bridge.call("estop"))
print("BRIDGE TEST PASSED")
PY
