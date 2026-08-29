#!/bin/bash
# McQueen autonomy one-shot — Jetson side. Run WITH sudo (needs systemd-run).
#
#   sudo ./realtime/jetson/go_autonomy_jetson.sh [--broker-host HOST]
#
# Sequence: stop stale sender -> stop camera-holding edge service -> start edge
# (GPIO, no recorder: the sender owns the camera) -> start sender.
#
# Both children run as TRANSIENT SYSTEMD UNITS (mcqueen-edge-autonomy /
# mcqueen-sender-autonomy), never `setsid nohup ... &`. That matters: a setsid
# child reparents to PID 1 with no systemd handle, so `systemctl stop
# mcqueen-edge` only ever reached the packaged mcqueen-edge.service while the
# hand-spawned actuator kept driving the motors. Transient units make
# `systemctl stop` authoritative and send logs to journalctl.
#
# Every tunable lives in realtime/config.env — nothing is hardcoded here.
set -u

REPO="${MCQUEEN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONF="$REPO/realtime/config.env"
[ -f "$CONF" ] || { echo "FATAL: $CONF missing. cp realtime/config.env.example realtime/config.env"; exit 2; }
# shellcheck disable=SC1090
. "$CONF"

BROKER_HOST="${MCQUEEN_BROKER_HOST:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --broker-host) BROKER_HOST="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1"; exit 2 ;;
    esac
done

# The quick-tunnel hostname rotates on every cloudflared restart. Refuse to run
# on an empty/stale value rather than silently dialing a dead broker.
[ -n "$BROKER_HOST" ] || { echo "FATAL: broker host unset. Set MCQUEEN_BROKER_HOST in $CONF or pass --broker-host"; exit 2; }
BROKER_HOST="${BROKER_HOST#https://}"; BROKER_HOST="${BROKER_HOST#wss://}"; BROKER_HOST="${BROKER_HOST%%/*}"

SESSION="${MCQUEEN_SESSION:-mcqueen}"
BROKER="wss://${BROKER_HOST}/ws?role=jetson&session=${SESSION}"
CAM="${MCQUEEN_CAM:?MCQUEEN_CAM unset}"
SERVO_ARGS="--servo-left-us ${MCQUEEN_SERVO_LEFT_US:?} --servo-center-us ${MCQUEEN_SERVO_CENTER_US:?} --servo-right-us ${MCQUEEN_SERVO_RIGHT_US:?}"
EDGE_UNIT=mcqueen-edge-autonomy
SENDER_UNIT=mcqueen-sender-autonomy
SENDER=realtime/jetson/gst_jetson_rtp_wan.py

[ -e "$CAM" ] || { echo "FATAL: camera $CAM not present"; exit 2; }

kill_wait() {  # $1 = pgrep pattern; wait for death, max ~5 s
    pkill -f "$1" 2>/dev/null
    for _ in $(seq 1 10); do
        pgrep -f "$1" >/dev/null 2>&1 || return 0
        sleep 0.5
    done
    echo "WARN: '$1' still alive after 5 s" >&2
    return 1
}

stop_unit() { systemctl stop "$1" 2>/dev/null; systemctl reset-failed "$1" 2>/dev/null; true; }

echo "[1/4] stopping stale sender..."
stop_unit "$SENDER_UNIT"
kill_wait "[g]st_jetson_rtp_wan.py"

echo "[2/4] stopping mcqueen-edge service (frees camera)..."
systemctl stop mcqueen-edge 2>/dev/null
stop_unit "$EDGE_UNIT"
kill_wait "edge.app"
sleep 1

echo "[3/4] starting edge (GPIO, no recorder)..."
cd "$REPO" || exit 2
# NOTE: --working-directory needs systemd 240+; the Jetson runs 237, so use
# -p WorkingDirectory= instead. Same for PYTHONPATH via -p Environment=.
systemd-run --unit="$EDGE_UNIT" --collect \
    -p WorkingDirectory="$REPO" -p Environment=PYTHONPATH="$REPO" \
    -p Environment=PYTHONUNBUFFERED=1 -- \
    python3 -m edge.app --jetson --no-record $SERVO_ARGS
sleep 3
journalctl -u "$EDGE_UNIT" --no-pager -n 100 | grep -q "JETSON GPIO" || {
    echo "FATAL: edge not in GPIO mode"; journalctl -u "$EDGE_UNIT" --no-pager -n 20; exit 3; }
ss -lun | grep -q :5007 || { echo "FATAL: :5007 not listening"; exit 3; }
echo "      edge OK (GPIO, :5007 up)"

echo "[4/4] starting sender -> $BROKER_HOST ..."
systemd-run --unit="$SENDER_UNIT" --collect \
    -p WorkingDirectory="$REPO" -p Environment=PYTHONPATH="$REPO" \
    -p Environment=PYTHONUNBUFFERED=1 -- \
    python3 "$SENDER" \
    --broker "$BROKER" \
    --device "$CAM" \
    --ctrl-to-edge "${MCQUEEN_EDGE_ADDR:-127.0.0.1:5007}" \
    --bitrate-kbps "${MCQUEEN_BITRATE_KBPS:-400}"
sleep 12
journalctl -u "$SENDER_UNIT" --no-pager -n 200 | grep -q "DIRECT_UDP_READY" || {
    echo "FATAL: no UDP punch"; journalctl -u "$SENDER_UNIT" --no-pager -n 30; exit 4; }
journalctl -u "$SENDER_UNIT" --no-pager -n 200 | grep -q "armed" || echo "WARN: edge arm line not seen yet"
echo "CAR_GO — loop closed."
echo "  watch : journalctl -u $SENDER_UNIT -f"
echo "  STOP  : sudo systemctl stop $SENDER_UNIT $EDGE_UNIT"
