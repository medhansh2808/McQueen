#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/McQueen/teleop"

source "${ROOT}/.venv/bin/activate"

exec python3 \
  "${ROOT}/linux/unoq_udp_receiver.py" \
  --bind 0.0.0.0 \
  --port 5007 \
  --failsafe-ms 300
