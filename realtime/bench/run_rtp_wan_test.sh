#!/usr/bin/env bash
# =============================================================================
# run_rtp_wan_test.sh — McQueen Jetson<->RTX WAN RTP transport test (NEW transport)
#
# Runs the RAW-H.264-RTP-over-NAT-punched-UDP pipeline (NOT WebRTC — the Jetson's
# GStreamer 1.14.5/libnice 0.1.14 cannot gather srflx candidates through CGNAT,
# see docs/evidence/2026-08-13-wan-pipeline-errors.txt error #6).
#
# Transport design (proven pattern from realtime/bench/direct_udp_peer.py):
#   Jetson sender (gst_jetson_rtp_wan.py):
#     cv2 capture -> appsrc -> x264 (SW) -> manual RTP packetization
#     -> punched UDP. In-band META (frame_id, capture_mono_ns) before each frame.
#   RTX receiver (gst_rtx_rtp_receiver.py):
#     punched UDP -> appsrc -> rtph264depay -> decodebin -> CUDA dummy inference
#     -> CTRL return echoing frame identity -> Jetson computes full-loop latency.
#   Rendezvous: broker.py on RTX (127.0.0.1:8765) + cloudflared Quick Tunnel.
#
# 2026-08-13 lab lessons encoded here:
#   F1: sender bug `% 30 < n` NameError (froze rtp_ts) — FIXED; this script
#       deploys the FIXED laptop copy to the Jetson every run.
#   F2: RTX receiver MUST run with the gst-webrtc-venv python (system python
#       lacks websocket) — enforced here.
#   F3: newer sender drops AUD NALs + manual packetization (lab15 "waiting for
#       start" orphans came from the old NVENC sender).
#   Both peers announce continuously + wait without timeout, so any start order
#   works.
#
# Usage: run in a REAL terminal (interactive ssh passwords, like
# run_direct_wan_test.sh).  ./realtime/bench/run_rtp_wan_test.sh
# =============================================================================
set +e

RTX_WIRED="192.168.0.132"
RTX_WIFI="192.168.0.179"
JETSON="192.168.55.1"
HERE="$(cd "$(dirname "$0")" && pwd)"
STUN_HOST="stun.cloudflare.com"
STUN_PORT="3478"
SESSION="mcqueen"

# -------- machine paths (verified 2026-08-13) --------------------------------
RTX_DIR="/var/tmp/mcqueen-junior"
RTX_PY="$RTX_DIR/gst-webrtc-venv/bin/python"     # F2: venv python (has websocket)
RTX_BROKER_PY="/home/junior/miniforge3/envs/lerobot/bin/python"  # broker host env
CAM="/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0"

say() { echo; echo "===== $* ====="; }

# -----------------------------------------------------------------------------
say "1. REACHABILITY"
ssh sravjti@$JETSON 'echo "OK Jetson USB SSH"' || { echo "Jetson unreachable (USB?)"; exit 1; }
RTX="$RTX_WIRED"
if ! ssh junior@$RTX 'echo "OK RTX SSH (wired)"' 2>/dev/null; then
    RTX="$RTX_WIFI"
    ssh junior@$RTX 'echo "OK RTX SSH (wifi)"' || { echo "RTX unreachable (try .132 or .179)"; exit 1; }
fi
echo "RTX = $RTX"

# -----------------------------------------------------------------------------
say "2. BROKER HEALTH / START"
# Start broker.py if not healthy (persistent-ish: survives; tunnel URL changes).
ssh -t junior@$RTX "
set +e
curl -fsS --max-time 3 http://127.0.0.1:8765/health >/dev/null && { echo 'broker already healthy'; exit 0; }
cd $RTX_DIR
nohup $RTX_BROKER_PY broker.py --host 127.0.0.1 --port 8765 > broker_lab.log 2>&1 </dev/null &
echo \$! > broker.pid
sleep 2
curl -fsS --max-time 3 http://127.0.0.1:8765/health && echo || { echo 'BROKER FAILED'; cat broker_lab.log; exit 2; }
"

# -----------------------------------------------------------------------------
say "3. CLOUDFLARED TUNNEL / PUBLIC URL"
PUBLIC_URL="$(ssh junior@$RTX "cat $RTX_DIR/cloudflared.url 2>/dev/null" | tr -d '\r\n')"
if [ -z "$PUBLIC_URL" ]; then
    PUBLIC_URL="$(ssh -t junior@$RTX "
set +e
cd $RTX_DIR
if ! curl -fsS --max-time 3 http://127.0.0.1:8765/health >/dev/null; then echo 'no broker'; exit 3; fi
if ! pgrep -f 'cloudflared tunnel' >/dev/null; then
    nohup ./cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate > cloudflared_lab.log 2>&1 </dev/null &
fi
for I in \$(seq 1 40); do
    URL=\"\$(grep -Eo 'https://[A-Za-z0-9.-]+\\.trycloudflare\\.com' cloudflared_lab.log 2>/dev/null | head -1)\"
    [ -n \"\$URL\" ] && break
    sleep 1
done
echo \"\$URL\" > cloudflared.url
echo \"\$URL\"
" 2>/dev/null | grep -Eo 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' | head -1)"
fi
[ -n "$PUBLIC_URL" ] || { echo "no tunnel URL"; exit 4; }
echo "PUBLIC URL: $PUBLIC_URL"
PUBLIC_HOST="${PUBLIC_URL#https://}"
JETSON_BROKER="wss://${PUBLIC_HOST}/ws?role=jetson&session=$SESSION"

# -----------------------------------------------------------------------------
say "4. PROVE JETSON CAN REACH SIGNALING"
ssh sravjti@$JETSON "curl -fsS --max-time 15 '$PUBLIC_URL/health' && echo && echo 'OK Jetson -> Internet -> Cloudflare -> RTX broker'" || { echo "Jetson cannot reach broker"; exit 5; }

# -----------------------------------------------------------------------------
say "5. DEPLOY FIXED SENDER + RECEIVER"
scp "$HERE/gst_jetson_rtp_wan.py" sravjti@$JETSON:/tmp/gst_jetson_rtp_wan.py || exit 6
scp "$HERE/gst_rtx_rtp_receiver.py" junior@$RTX:$RTX_DIR/gst_rtx_rtp_receiver.py || exit 6
echo "deployed (fixed sender / receiver)"

# -----------------------------------------------------------------------------
say "6. START RTX RECEIVER (venv python!)"
ssh -t junior@$RTX "
set +e
cd $RTX_DIR
pkill -f gst_rtx_rtp_receiver.py 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  $RTX_PY gst_rtx_rtp_receiver.py \
  --broker 'ws://127.0.0.1:8765/ws?role=rtx&session=$SESSION' \
  --stun-host '$STUN_HOST' --stun-port $STUN_PORT \
  > gst_rtx_rtp_receiver_lab.log 2>&1 </dev/null &
sleep 4
pgrep -f gst_rtx_rtp_receiver.py >/dev/null && echo 'receiver alive' || { echo 'receiver DEAD'; tail -20 gst_rtx_rtp_receiver_lab.log; exit 7; }
grep -E '^\[RTX-GST\]' gst_rtx_rtp_receiver_lab.log | tail -5
"

# -----------------------------------------------------------------------------
say "7. START JETSON SENDER (fixed copy from /tmp)"
ssh -t sravjti@$JETSON "
set +e
sudo systemctl stop mcqueen-edge.service 2>/dev/null
pkill -f gst_jetson_rtp_wan.py 2>/dev/null; sleep 1
nohup env PYTHONUNBUFFERED=1 GST_DEBUG_NO_COLOR=1 \
  python3 /tmp/gst_jetson_rtp_wan.py \
  --broker '$JETSON_BROKER' \
  --device '$CAM' \
  --stun-host '$STUN_HOST' --stun-port $STUN_PORT \
  > /tmp/gst_jetson_rtp_wan_lab.log 2>&1 </dev/null &
sleep 10
pgrep -f gst_jetson_rtp_wan.py >/dev/null && echo 'sender alive' || { echo 'sender DEAD'; tail -40 /tmp/gst_jetson_rtp_wan_lab.log; exit 8; }
grep -E '^\[JETSON-CAM\]' /tmp/gst_jetson_rtp_wan_lab.log | tail -8
"

# -----------------------------------------------------------------------------
say "8. OBSERVE (35s)"
sleep 35
ssh sravjti@$JETSON 'grep -E "^\[JETSON-CAM\]" /tmp/gst_jetson_rtp_wan_lab.log | tail -25'
echo
ssh junior@$RTX 'grep -E "^\[RTX-GST\]" '"$RTX_DIR"'/gst_rtx_rtp_receiver_lab.log | tail -25'

# -----------------------------------------------------------------------------
say "9. RESULT"
JLOG=/tmp/mcq_wan_jetson.log; RLOG=/tmp/mcq_wan_rtx.log
ssh sravjti@$JETSON 'tail -200 /tmp/gst_jetson_rtp_wan_lab.log' > "$JLOG"
ssh junior@$RTX 'tail -200 '"$RTX_DIR"'/gst_rtx_rtp_receiver_lab.log' > "$RLOG"

READY=0; RTXFPS=0; CTRL=0; LAT=0; JERR=0; RERR=0
grep -q 'DIRECT_UDP_READY' "$JLOG" && READY=1
grep -q '\[RTX-GST\] VIDEO frames_rx=' "$RLOG" && RTXFPS=1
grep -q '\[JETSON-CAM\] CTRL_RX' "$JLOG" && CTRL=1
grep -q 'FULL_LOOP_LATENCY n=' "$JLOG" && LAT=1
grep -q '\[JETSON-CAM\] GST ERROR\|Traceback' "$JLOG" && JERR=1
grep -q '\[RTX-GST\] GST ERROR\|Traceback' "$RLOG" && RERR=1

echo "NAT punch ready      : $READY"
echo "RTX decoded frames   : $RTXFPS"
echo "Control returned     : $CTRL"
echo "Full-loop latency    : $LAT"
echo "Jetson error         : $JERR"
echo "RTX error            : $RERR"

if [ "$READY" = 1 ] && [ "$RTXFPS" = 1 ] && [ "$CTRL" = 1 ] && [ "$LAT" = 1 ] && [ "$JERR" = 0 ] && [ "$RERR" = 0 ]; then
    echo
    echo "✅✅✅ WAN RTP FULL LOOP OK — log the FULL_LOOP_LATENCY line above ✅✅✅"
else
    echo
    echo "❌ NOT fully green. Check:"
    echo "   - F1 sender rtp_ts: Jetson log should show SENT pkts throttle + advancing rtp_ts"
    echo "   - F2 receiver python: must be $RTX_PY"
    echo "   - depay 'waiting for start': old-sender AUD artifact; fixed sender drops AUD"
    echo "   - see docs/evidence/2026-08-13-lab-pull/README.md findings F1-F6"
fi

echo
echo "Logs: $JLOG (jetson) / $RLOG (rtx)"
