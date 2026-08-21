#!/usr/bin/env bash
# deploy_bench.sh — deploy the encoder bench tool to the Jetson (1 command).
# Usage: ./tools/encoder/deploy_bench.sh [HOST] [PORT] [DEST_REPO]
#   default HOST=sravjti@192.168.55.1 (USB device-mode link, port 22)
#   tunnel fallback: ./tools/encoder/deploy_bench.sh sravjti@127.0.0.1 2223
# Password is entered by the human at the prompt.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${1:-sravjti@192.168.55.1}"
PORT="${2:-22}"
DEST_ROOT="${3:-~/encoder_bench}"   # clean bench dir on the Jetson

echo "Deploying encoder bench files to $HOST (port $PORT):$DEST_ROOT"
ssh -p "$PORT" "$HOST" "mkdir -p $DEST_ROOT/tools/encoder $DEST_ROOT/robot/jetson_nano/mcqueen_edge"
scp -P "$PORT" \
  "$REPO/robot/jetson_nano/mcqueen_edge/gpio_encoder_source.py" \
  "$HOST:$DEST_ROOT/robot/jetson_nano/mcqueen_edge/"
scp -P "$PORT" \
  "$REPO/tools/encoder/bench_encoder_sweep.py" \
  "$HOST:$DEST_ROOT/tools/encoder/"
echo "DEPLOY OK"
echo
echo "On the Jetson (system python3 has Jetson.GPIO):"
echo "  cd $DEST_ROOT"
echo "  python3 tools/encoder/bench_encoder_sweep.py --mode identify --pin-a 29 --pin-b 31"
echo "  python3 tools/encoder/bench_encoder_sweep.py --mode calibrate --pin-a 29 --pin-b 31 --revs 10"
echo "  python3 tools/encoder/bench_encoder_sweep.py --mode sweep --pin-a 29 --pin-b 31 --ticks-per-rev <value> --out ~/encoder_bench/encoder_sweep.csv"