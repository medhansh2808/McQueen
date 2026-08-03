#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/McQueen/teleop"
FQBN="arduino:zephyr:unoq"

echo "Uploading the compiled sketch persistently to the UNO Q MCU..."
arduino-cli upload \
  --fqbn "${FQBN}" \
  "${ROOT}/sketch/UnoQDrive"

echo "Upload complete."
echo "The MCU sketch is now stored persistently in flash."
