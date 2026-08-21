#!/usr/bin/env bash
# =============================================================================
# run_rtp_lan_test.sh — McQueen Jetson<->RTX LAN full-loop RTP latency test
# LAN variant of run_rtp_wan_test.sh: local broker (0.0.0.0) + local mini-STUN
# (returns LAN candidates -> direct LAN flow, no NAT hairpin, no cloudflared).
# Requires: mini_stun.py running on the RTX (starts it if absent).
# Usage: ./tools/realtime/run_rtp_lan_test.sh
# =============================================================================
set +e

RTX="${RTX:-192.168.0.132}"
JETSON="${JETSON:-192.168.55.1}"                       # USB gadget (stable)
HERE="$(cd "$(dirname "$0")" && pwd)"
SESSION="mcqueen"
RTX_DIR="${RTX_DIR:-/var/tmp/mcqueen-junior}"
RTX_PY="${RTX_PY:-$RTX_DIR/gst-webrtc-venv/bin/python}"
BROKER_PY="${BROKER_PY:-/home/junior/miniforge3/envs/lerobot/bin/python}"
CAM="${CAM:-/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0}"

say() { echo; echo "===== $* ====="; }

say "1. REACHABILITY"
ssh sravjti@$JETSON 'echo OK Jetson USB SSH' || { echo "Jetson unreachable"; exit 1; }
ssh junior@$RTX 'echo OK RTX SSH' || { echo "RTX unreachable"; exit 1; }

say "2. BROKER (LAN-visible 0.0.0.0)"
ssh junior@$RTX "
set +e
curl -fsS --max-time 3 http://192.168.0.132:8765/health >/dev/null 2>&1 && { echo 'broker healthy (LAN)'; exit 0; }
pkill -f 'broker.py --host' 2>/dev/null; sleep 1
cd $RTX_DIR
nohup $BROKER_PY broker.py --host 0.0.0.0 --port 8765 > broker_lab.log 2>&1 </dev/null &
sleep 2
curl -fsS --max-time 3 http://192.168.0.132:8765/health && echo ' broker OK' || { echo 'BROKER FAILED'; cat broker_lab.log; exit 2; }
"

say "3. MINI STUN (LAN candidates)"
ssh junior@$RTX "
set +e
pgrep -f '[m]ini_stun' >/dev/null && { echo 'mini_stun running'; exit 0; }
cd $RTX_DIR
nohup $RTX_PY mini_stun.py > mini_stun.log 2>&1 </dev/null &
sleep 2
pgrep -f '[m]ini_stun' >/dev/null && echo 'mini_stun started' || { echo 'mini_stun FAILED'; cat mini_stun.log; exit 3; }
"

say "4. DEPLOY SENDER + RECEIVER"
scp "$HERE/gst_jetson_rtp_wan.py" sravjti@$JETSON:/tmp/gst_jetson_rtp_wan.py || exit 4
scp "$HERE/gst_rtx_rtp_receiver.py" junior@$RTX:$RTX_DIR/gst_rtx_rtp_receiver.py || exit 4
echo deployed

say "5. START RTX RECEIVER (local STUN)"
ssh junior@$RTX "
set +e
cd $RTX_DIR
pkill -f '[g]st_rtx_rtp_receiver' 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  $RTX_PY gst_rtx_rtp_receiver.py \
  --broker 'ws://127.0.0.1:8765/ws?role=rtx&session=$SESSION' \
  --stun-host 192.168.0.132 --stun-port 3479 \
  > gst_rtx_rtp_receiver_lab.log 2>&1 </dev/null &
sleep 5
pgrep -f '[g]st_rtx_rtp_receiver' >/dev/null && echo 'receiver alive' || { echo 'receiver DEAD'; tail -15 gst_rtx_rtp_receiver_lab.log; exit 5; }
grep -E '^\[RTX-GST\]' gst_rtx_rtp_receiver_lab.log | tail -5
"

say "6. START JETSON SENDER (local STUN)"
ssh sravjti@$JETSON "
set +e
pkill -f '[g]st_jetson_rtp_wan' 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  python3 /tmp/gst_jetson_rtp_wan.py \
  --broker 'ws://192.168.0.132:8765/ws?role=jetson&session=$SESSION' \
  --device '$CAM' \
  --stun-host 192.168.0.132 --stun-port 3479 \
  > /tmp/gst_jetson_rtp_wan_lab.log 2>&1 </dev/null &
sleep 12
pgrep -f '[g]st_jetson_rtp_wan' >/dev/null && echo 'sender alive' || { echo 'sender DEAD'; tail -30 /tmp/gst_jetson_rtp_wan_lab.log; exit 6; }
grep -E '^\[JETSON-CAM\]' /tmp/gst_jetson_rtp_wan_lab.log | tail -6
"

say "7. OBSERVE (35s)"
sleep 35
ssh sravjti@$JETSON 'grep -E "^\[JETSON-CAM\]" /tmp/gst_jetson_rtp_wan_lab.log | tail -12'
echo
ssh junior@$RTX 'grep -E "^\[RTX-GST\]" '"$RTX_DIR"'/gst_rtx_rtp_receiver_lab.log | tail -12'

say "8. RESULT"
JLOG=/tmp/mcq_lan_jetson.log; RLOG=/tmp/mcq_lan_rtx.log
ssh sravjti@$JETSON 'tail -250 /tmp/gst_jetson_rtp_wan_lab.log' > "$JLOG"
ssh junior@$RTX 'tail -250 '"$RTX_DIR"'/gst_rtx_rtp_receiver_lab.log' > "$RLOG"

READY=0; RTXFPS=0; CTRL=0; LAT=0; JERR=0; RERR=0
grep -q 'DIRECT_UDP_READY' "$JLOG" && READY=1
grep -q '\[RTX-GST\] VIDEO frames_rx=' "$RLOG" && RTXFPS=1
grep -q '\[JETSON-CAM\] CTRL_RX' "$JLOG" && CTRL=1
grep -q 'FULL_LOOP_LATENCY n=' "$JLOG" && LAT=1
grep -q '\[JETSON-CAM\] GST ERROR\|Traceback' "$JLOG" && JERR=1
grep -q '\[RTX-GST\] GST ERROR\|Traceback' "$RLOG" && RERR=1

echo "Direct UDP ready      : $READY"
echo "RTX decoded frames    : $RTXFPS"
echo "Control returned      : $CTRL"
echo "Full-loop latency     : $LAT"
echo "Jetson error          : $JERR"
echo "RTX error             : $RERR"
echo
echo "Logs: $JLOG / $RLOG"
