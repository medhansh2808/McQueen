#!/usr/bin/env bash
set -euo pipefail

UNO_Q_HOST="${1:-192.168.4.1}"
DESTINATION="${2:-$HOME/McQueenData/spool}"

mkdir -p "$DESTINATION"

echo "UNO Q:       arduino@$UNO_Q_HOST"
echo "Destination: $DESTINATION"
echo

ping -c 1 -W 2 "$UNO_Q_HOST" >/dev/null

rsync \
  -avh \
  --partial \
  --append-verify \
  --exclude='*.tmp' \
  "arduino@$UNO_Q_HOST:/home/arduino/McQueen/datasets/" \
  "$DESTINATION/"

echo
echo "PHASE 4 COMPLETE"
