#!/usr/bin/env bash
set -u

REPO="$HOME/McQueenWork/McQueen"
CAM="/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0"
JETSON_IP="192.168.55.1"

pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; }

echo "===== McQueen laptop lab preflight ====="

if [ ! -d "$REPO/.git" ]; then
  fail "Repo missing: $REPO"
  exit 1
fi
cd "$REPO" || exit 1

echo
echo "===== Git ====="
git status --short --branch || true
git log -1 --oneline || true

echo
echo "===== Steering contract ====="
python3 - <<'PY'
from robot.jetson_nano.mcqueen_edge.server import steering_to_angle
# Current contract (2026-08-13, matches tests/test_jetson_steering_mapping.py
# and the physical McQueen steering direction): -1000 -> 115 deg, 1000 -> 45 deg.
expected={-1000:115,0:90,1000:45}
ok=True
for x,y in expected.items():
    got=steering_to_angle(x)
    print(f"{x:5d} -> {got:3d} deg")
    ok &= got == y
raise SystemExit(0 if ok else 1)
PY
[ $? -eq 0 ] && pass "Steering = 115 / 90 / 45" || fail "Steering contract broken"

echo
echo "===== Laptop services ====="
for u in mcqueen-recorder.path mcqueen-discovery.service; do
  en="$(systemctl is-enabled "$u" 2>/dev/null || true)"
  ac="$(systemctl is-active "$u" 2>/dev/null || true)"
  echo "$u enabled=$en active=$ac"
done

echo
echo "===== Discovery ====="
if ss -lun 2>/dev/null | grep -q ':5006 '; then
  pass "UDP 5006 listening"
else
  fail "UDP 5006 not listening"
fi

python3 - <<'PY'
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(b"KACHOW_DISCOVER_V1\n",("127.0.0.1",5006))
responses=[]
try:
    for _ in range(2):
        data,_=s.recvfrom(512)
        responses.append(data.decode(errors="replace").strip())
except Exception:
    pass
for x in responses:
    print(x)
ok=(any(x.startswith("KACHOW_CAR_V1") for x in responses)
    and any(x.startswith("KACHOW_HOST_V1") for x in responses))
raise SystemExit(0 if ok else 1)
PY
[ $? -eq 0 ] && pass "AUTO discovery loopback" || fail "AUTO discovery loopback"

echo
echo "===== Camera / recorder ====="
if [ -e "$CAM" ]; then
  pass "Lenovo webcam stable path exists"
  rec="$(systemctl is-active mcqueen-recorder.service 2>/dev/null || true)"
  echo "mcqueen-recorder.service active=$rec"
  if [ "$rec" = "active" ]; then
    pass "Recorder active"
  else
    warn "Camera present but recorder is not active"
  fi
  ss -lunp 2>/dev/null | grep ':5007' || true
  ss -lntp 2>/dev/null | grep ':8080' || true
else
  warn "Lenovo webcam not connected"
  echo "Recorder state: $(systemctl is-active mcqueen-recorder.service 2>/dev/null || true)"
fi

echo
echo "===== Jetson USB link ====="
if ping -c 1 -W 1 "$JETSON_IP" >/dev/null 2>&1; then
  pass "Jetson reachable at $JETSON_IP"
else
  warn "Jetson not reachable at $JETSON_IP"
fi

echo
echo "===== PRE-FLIGHT COMPLETE ====="
echo "Warnings are expected when hardware is not connected."
