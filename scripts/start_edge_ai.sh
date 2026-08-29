#!/bin/bash
# McQueen autonomy edge — idempotent start (GPIO, camera-less, no recorder).
# Run WITH sudo. Safe to run repeatedly; stops stale instances first.
#
# Starts the edge as the TRANSIENT SYSTEMD UNIT mcqueen-edge-autonomy, never
# `setsid nohup … &`. A setsid child reparents to PID 1 with no systemd handle,
# so `systemctl stop mcqueen-edge` cannot reach it and the process keeps driving
# the motors. Anything holding the GPIO must be stoppable by unit name.
#
#   STOP:  sudo systemctl stop mcqueen-edge-autonomy
set -euo pipefail

REPO="${MCQUEEN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONF="$REPO/realtime/config.env"
[ -f "$CONF" ] || { echo "FATAL: $CONF missing. cp realtime/config.env.example realtime/config.env"; exit 2; }
# shellcheck disable=SC1090
. "$CONF"

SERVO_ARGS="--servo-left-us ${MCQUEEN_SERVO_LEFT_US:?} --servo-center-us ${MCQUEEN_SERVO_CENTER_US:?} --servo-right-us ${MCQUEEN_SERVO_RIGHT_US:?}"
UNIT=mcqueen-edge-autonomy

echo "[1/3] stopping stale edge instances..."
systemctl stop mcqueen-edge 2>/dev/null || true
systemctl stop "$UNIT" 2>/dev/null || true
systemctl reset-failed "$UNIT" 2>/dev/null || true
pkill -9 -f "[m]cqueen_edge.app" 2>/dev/null || true
sleep 1

echo "[2/3] clearing stale .pyc (forces fresh compile of patched code)..."
rm -f "$REPO"/robot/jetson_nano/mcqueen_edge/__pycache__/drive*.pyc \
      "$REPO"/robot/jetson_nano/mcqueen_edge/__pycache__/jetson_gpio*.pyc 2>/dev/null || true

echo "[3/3] starting edge (GPIO, no-record) as $UNIT..."
cd "$REPO"
# --working-directory needs systemd 240+; Jetson runs 237 -> -p WorkingDirectory=
systemd-run --unit="$UNIT" --collect \
    -p WorkingDirectory="$REPO" -p Environment=PYTHONPATH="$REPO" \
    -p Environment=PYTHONUNBUFFERED=1 -- \
    python3 -m robot.jetson_nano.mcqueen_edge.app --jetson --no-record $SERVO_ARGS
sleep 3

journalctl -u "$UNIT" --no-pager -n 100 | grep -q "JETSON GPIO" || {
    echo "FATAL: edge not in GPIO mode"; journalctl -u "$UNIT" --no-pager -n 20; exit 3; }
ss -lun | grep -q :5007 || { echo "FATAL: :5007 not listening"; exit 3; }
echo "EDGE_AI_OK — :5007 listening (GPIO, no recorder)"
echo "  logs: journalctl -u $UNIT -f"
echo "  STOP: sudo systemctl stop $UNIT"
