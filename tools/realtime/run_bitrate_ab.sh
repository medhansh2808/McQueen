#!/usr/bin/env bash
# =============================================================================
# run_bitrate_ab.sh — McQueen WAN RTP bitrate A/B harness (NEW file, lab-only)
#
# Runs the SAME sender/receiver pipeline as run_rtp_wan_test.sh but sweeps
# --bitrate-kbps over {150, 300, 400} x {2 iterations} and captures per-run
# evidence into docs/evidence/<date>/ab/run_<bitrate>_<iter>/.
#
# PURPOSE: the bitrate for realtime use must come from measured throughput +
# loss (Fix 3 in gst_jetson_rtp_wan.py), not a guess. This harness produces
# the measurement evidence, loss-logged per run.
#
# RULES:
#   - This file is NEW and standalone. It does NOT modify run_rtp_wan_test.sh.
#   - It calls the same deployed scripts (gst_jetson_rtp_wan.py on Jetson,
#     gst_rtx_rtp_receiver.py on RTX) — pipeline behavior unchanged, only the
#     bitrate argument varies.
#   - Requires interactive ssh (passwords) and explicit human authorization.
#     Run in a REAL terminal at the lab.
#   - Evidence files carry run labels + rates/loss, never clock timestamps
#     (no-timestamps rule, AGENTS.md C).
#
# Usage: ./tools/realtime/run_bitrate_ab.sh
# =============================================================================
set +e

RTX_WIRED="192.168.0.132"
RTX_WIFI="192.168.0.179"
JETSON="192.168.55.1"
HERE="$(cd "$(dirname "$0")" && pwd)"
STUN_HOST="stun.cloudflare.com"
STUN_PORT="3478"
SESSION="mcqueen"

RTX_DIR="/var/tmp/mcqueen-junior"
RTX_PY="$RTX_DIR/gst-webrtc-venv/bin/python"
RTX_BROKER_PY="/home/junior/miniforge3/envs/lerobot/bin/python"
CAM="/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0"

BITRATES=(150 300 400)
ITERATIONS=2
OBSERVE_SEC=25
DATE="$(date +%Y-%m-%d)"
EVIDENCE="$HERE/../../docs/evidence/$DATE/ab"

say() { echo; echo "===== $* ====="; }

# -----------------------------------------------------------------------------
say "0. REACHABILITY"
ssh sravjti@$JETSON 'echo OK-JETSON' || { echo "Jetson unreachable"; exit 1; }
RTX="$RTX_WIRED"
if ! ssh junior@$RTX 'echo OK-RTX' 2>/dev/null; then
    RTX="$RTX_WIFI"
    ssh junior@$RTX 'echo OK-RTX' || { echo "RTX unreachable"; exit 1; }
fi
echo "RTX = $RTX"

# -----------------------------------------------------------------------------
say "1. BROKER HEALTH (start if needed, same as run_rtp_wan_test.sh)"
ssh junior@$RTX "
set +e
curl -fsS --max-time 3 http://127.0.0.1:8765/health >/dev/null && { echo 'broker healthy'; exit 0; }
cd $RTX_DIR
nohup $RTX_BROKER_PY broker.py --host 127.0.0.1 --port 8765 > broker_lab.log 2>&1 </dev/null &
echo \$! > broker.pid
sleep 2
curl -fsS --max-time 3 http://127.0.0.1:8765/health && echo || { echo 'BROKER FAILED'; cat broker_lab.log; exit 2; }
"

# -----------------------------------------------------------------------------
say "2. CLOUDFLARED URL (same logic as run_rtp_wan_test.sh, step 3)"
PUBLIC_URL="$(ssh junior@$RTX "cat $RTX_DIR/cloudflared.url 2>/dev/null" | tr -d '\r\n')"
[ -n "$PUBLIC_URL" ] || { echo "no tunnel URL on RTX ($RTX_DIR/cloudflared.url)"; exit 9; }
PUBLIC_HOST="${PUBLIC_URL#https://}"
JETSON_BROKER="wss://${PUBLIC_HOST}/ws?role=jetson&session=$SESSION"
echo "JETSON_BROKER=$JETSON_BROKER"

# -----------------------------------------------------------------------------
say "3. DEPLOY REPO COPIES (same as run_rtp_wan_test.sh step 5)"
scp "$HERE/gst_jetson_rtp_wan.py" sravjti@$JETSON:/tmp/gst_jetson_rtp_wan.py || exit 6
scp "$HERE/gst_rtx_rtp_receiver.py" junior@$RTX:$RTX_DIR/gst_rtx_rtp_receiver.py || exit 6
echo "deployed"

mkdir -p "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
echo "bitrate_kbps iteration frames_rx loss_pct assoc_loss_pct full_loop" > "$SUMMARY"

# -----------------------------------------------------------------------------
for BR in "${BITRATES[@]}"; do
  for ITER in $(seq 1 $ITERATIONS); do
    RUN="$EVIDENCE/run_${BR}_${ITER}"
    mkdir -p "$RUN"
    say "RUN bitrate=${BR} kbps iteration=${ITER}"

    ssh junior@$RTX "
set +e
cd $RTX_DIR
[ -f receiver_ab.pid ] && kill \$(cat receiver_ab.pid) 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  $RTX_PY gst_rtx_rtp_receiver.py \
  --broker 'ws://127.0.0.1:8765/ws?role=rtx&session=$SESSION' \
  --stun-host '$STUN_HOST' --stun-port $STUN_PORT \
  > gst_rtx_rtp_receiver_ab.log 2>&1 </dev/null &
echo \$! > receiver_ab.pid
sleep 4
kill -0 \$(cat receiver_ab.pid) 2>/dev/null && echo 'receiver alive' || { echo 'receiver DEAD'; tail -20 gst_rtx_rtp_receiver_ab.log; exit 7; }
"

    ssh sravjti@$JETSON "
set +e
[ -f /tmp/sender_ab.pid ] && kill \$(cat /tmp/sender_ab.pid) 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  python3 /tmp/gst_jetson_rtp_wan.py \
  --broker '$JETSON_BROKER' \
  --device '$CAM' \
  --stun-host '$STUN_HOST' --stun-port $STUN_PORT \
  --bitrate-kbps $BR \
  > /tmp/gst_jetson_rtp_wan_ab.log 2>&1 </dev/null &
echo \$! > /tmp/sender_ab.pid
sleep 10
kill -0 \$(cat /tmp/sender_ab.pid) 2>/dev/null && echo 'sender alive' || { echo 'sender DEAD'; tail -40 /tmp/gst_jetson_rtp_wan_ab.log; exit 8; }
"

    say "OBSERVE (${OBSERVE_SEC}s)"
    sleep $OBSERVE_SEC

    ssh sravjti@$JETSON 'tail -200 /tmp/gst_jetson_rtp_wan_ab.log' > "$RUN/sender.log"
    ssh junior@$RTX 'tail -200 '"$RTX_DIR"'/gst_rtx_rtp_receiver_ab.log' > "$RUN/receiver.log"
    echo "saved: $RUN/{sender,receiver}.log"

    FRAMES_RX=$(grep -oE 'frames_rx=[0-9]+' "$RUN/receiver.log" | tail -1 | cut -d= -f2)
    # Frames sent = the sender's meta= count (1 META per frame). NOTE: sent_pkts
    # is PACKETS, not frames — never compute frame loss against it.
    META=$(grep -oE 'meta=[0-9]+' "$RUN/sender.log" | tail -1 | cut -d= -f2)
    ASSOC_OK=$(grep -oE 'assoc_ok=[0-9]+' "$RUN/receiver.log" | tail -1 | cut -d= -f2)
    ASSOC_MISS=$(grep -oE 'assoc_miss=[0-9]+' "$RUN/receiver.log" | tail -1 | cut -d= -f2)
    LOSS="n/a"
    if [ -n "$FRAMES_RX" ] && [ -n "$META" ] && [ "$META" -gt 0 ] 2>/dev/null; then
        LOSS=$(awk -v rx="$FRAMES_RX" -v tx="$META" 'BEGIN{printf "%.1f", 100*(1-rx/tx)}')
    fi
    ASSOC_LOSS="n/a"
    if [ -n "$ASSOC_OK" ] && [ -n "$ASSOC_MISS" ] && [ $((ASSOC_OK + ASSOC_MISS)) -gt 0 ] 2>/dev/null; then
        ASSOC_LOSS=$(awk -v m="$ASSOC_MISS" -v t="$((ASSOC_OK + ASSOC_MISS))" 'BEGIN{printf "%.1f", 100*m/t}')
    fi
    FULL_LOOP="no"
    grep -qE 'CTRL_RX n=' "$RUN/sender.log" && FULL_LOOP="yes"
    echo "${BR} ${ITER} ${FRAMES_RX:-0} ${LOSS} ${ASSOC_LOSS} ${FULL_LOOP}" >> "$SUMMARY"
    echo "frames_rx=${FRAMES_RX:-0} frames_sent=${META:-0} loss=${LOSS}% assoc_loss=${ASSOC_LOSS}% full_loop=${FULL_LOOP}"
  done
done

# -----------------------------------------------------------------------------
say "A/B SUMMARY"
cat "$SUMMARY"
echo
echo "Evidence: $EVIDENCE"