#!/bin/bash
# McQueen autonomy stack — RTX/4090 side. ONE command, safe to re-run.
#
#   ./realtime/rtx/start_stack.sh
#
# Brings up, in order: broker (:8765) -> policy worker (:9801, CUDA) ->
# RTP receiver (dials the broker over the Cloudflare quick tunnel).
# Kills any stale instance of each first.
#
# Every path lives in realtime/config.env — nothing is hardcoded here.
set -u

REPO="${MCQUEEN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONF="$REPO/realtime/config.env"
[ -f "$CONF" ] || { echo "FATAL: $CONF missing. cp realtime/config.env.example realtime/config.env"; exit 2; }
# shellcheck disable=SC1090
. "$CONF"

RT="${MCQUEEN_RUNTIME_DIR:?MCQUEEN_RUNTIME_DIR unset}"
PY="${MCQUEEN_PY:?MCQUEEN_PY unset}"
BPY="${MCQUEEN_BROKER_PY:-$PY}"
CKPT="${MCQUEEN_CKPT:?MCQUEEN_CKPT unset}"
ONNX="${MCQUEEN_ONNX:?MCQUEEN_ONNX unset}"
PORT="${MCQUEEN_POLICY_PORT:-9801}"
BPORT="${MCQUEEN_BROKER_PORT:-8765}"
SESSION="${MCQUEEN_SESSION:-mcqueen}"
D="$REPO/realtime/rtx"

# Fail loudly on missing weights instead of 20 s later inside onnxruntime.
[ -f "$CKPT" ] || { echo "FATAL: checkpoint not found: $CKPT"; exit 2; }
KS="${ONNX%.onnx}_ks.onnx"   # rtx_policy_v1 appends _ks; that's the file that loads
[ -f "$KS" ] || { echo "FATAL: trunk not found: $KS (derived from MCQUEEN_ONNX)"; exit 2; }
[ -x "$PY" ]  || { echo "FATAL: python not executable: $PY"; exit 2; }
[ -x "$BPY" ] || { echo "FATAL: broker python not executable: $BPY"; exit 2; }
# The broker and the worker run on different interpreters on purpose (aiohttp vs
# CUDA torch/onnxruntime). Check both up front rather than failing at [2/4].
"$BPY" -c "import aiohttp" 2>/dev/null || { echo "FATAL: $BPY has no aiohttp (needed by broker.py) -- set MCQUEEN_BROKER_PY"; exit 2; }
"$PY" -c "import websocket" 2>/dev/null || { echo "FATAL: $PY has no websocket-client (needed by the receiver) -- check MCQUEEN_PY"; exit 2; }

NV="${MCQUEEN_NVIDIA_LIBS:-}"
if [ -n "$NV" ]; then
    export LD_LIBRARY_PATH="$(ls -d "$NV"/cudnn/lib "$NV"/cublas/lib "$NV"/cuda_runtime/lib 2>/dev/null | tr '\n' ':')${LD_LIBRARY_PATH:-}"
fi
mkdir -p "$RT"

echo "[1/4] killing stale stack..."
pkill -f "$D/policy_worker.py" 2>/dev/null
pkill -f "$D/gst_rtx_rtp_receiver.py" 2>/dev/null
pkill -f "$D/broker.py" 2>/dev/null
sleep 2

echo "[2/4] broker (:$BPORT)..."
setsid "$BPY" "$D/broker.py" --port "$BPORT" > "$RT/broker.log" 2>&1 < /dev/null &
sleep 3
ss -ltn | grep -q ":$BPORT" || { echo "FATAL: broker not listening on :$BPORT"; tail -5 "$RT/broker.log"; exit 3; }

echo "[3/4] policy worker (:$PORT, CUDA)..."
setsid "$PY" "$D/policy_worker.py" \
    --ckpt "$CKPT" --onnx "$ONNX" --port "$PORT" --device cuda \
    --models-dir "${MCQUEEN_MODELS_DIR:-}" > "$RT/policy_worker.log" 2>&1 < /dev/null &
for i in $(seq 1 90); do
    sleep 1
    grep -q "serving on" "$RT/policy_worker.log" && break
    grep -qE "FATAL|Traceback" "$RT/policy_worker.log" && { echo "FATAL: worker failed"; tail -20 "$RT/policy_worker.log"; exit 3; }
done
grep -q "CUDAExecutionProvider" "$RT/policy_worker.log" || { echo "FATAL: worker not on CUDA"; tail -10 "$RT/policy_worker.log"; exit 3; }
echo "      worker OK ($(grep -o 'serving on[^—]*' "$RT/policy_worker.log" | tail -1))"

echo "[4/4] receiver (broker URL read live from tunnel log)..."
# The quick tunnel mints a new hostname on every cloudflared restart. Read the
# URL from the log belonging to the cloudflared process running RIGHT NOW --
# never from a fixed filename, because stale *_tunnel.log files from earlier
# sessions sit in the same directory and will hand back a dead hostname.
TUNLOG=$(ps -eo args= | grep "[c]loudflared tunnel --url http://localhost:$BPORT" \
         | grep -oE -- '--logfile [^ ]+' | awk '{print $2}' | tail -1)
[ -n "$TUNLOG" ] || { echo "FATAL: no cloudflared tunnel running for http://localhost:$BPORT"; exit 4; }
BROKER_URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUNLOG" 2>/dev/null | tail -1)
[ -n "$BROKER_URL" ] || { echo "FATAL: no tunnel URL in $TUNLOG"; exit 4; }
echo "      tunnel log: $TUNLOG"
setsid "$PY" "$D/gst_rtx_rtp_receiver.py" \
    --broker "wss://${BROKER_URL#https://}/ws?role=rtx&session=${SESSION}" \
    --policy-endpoint "127.0.0.1:$PORT" \
    --jitter-ms "${MCQUEEN_JITTER_MS:-30}" > "$RT/receiver.log" 2>&1 < /dev/null &
sleep 8

echo "=== VERIFY ==="
grep -E "POLICY|WORKER" "$RT/policy_worker.log" | tail -2
grep -E "PUBLIC" "$RT/receiver.log" | tail -1
ss -ltn | grep -E ":$BPORT|:$PORT"
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
echo "STACK_READY"
echo "  broker host for the Jetson: ${BROKER_URL#https://}"
echo "  run there: sudo ./realtime/jetson/go_autonomy_jetson.sh --broker-host ${BROKER_URL#https://}"
