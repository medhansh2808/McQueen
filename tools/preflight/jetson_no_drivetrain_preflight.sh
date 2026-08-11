#!/usr/bin/env bash
set -u

echo "===== McQUEEN JETSON NO-DRIVETRAIN PREFLIGHT ====="
echo "host: $(hostname)"
echo "date: $(date -Is 2>/dev/null || date)"
echo

echo "===== OS / PYTHON ====="
uname -a || true
python3 --version || true

echo
echo "===== REPO ====="
if [ -d "$HOME/McQueen/.git" ]; then
  cd "$HOME/McQueen"
  git status --short --branch || true
  git log -1 --oneline --decorate || true
else
  echo "WARN: $HOME/McQueen git checkout not found"
fi

echo
echo "===== SERVICES ====="
for svc in mcqueen-edge.service mcqueen-discovery.service; do
  printf '%-28s ' "$svc"
  systemctl is-active "$svc" 2>/dev/null || echo "unknown/not-active"
done

echo
echo "===== LISTENERS ====="
ss -lntu 2>/dev/null | grep -E ':(5006|5007|8080)\b' || echo "No 5006/5007/8080 listeners shown"

echo
echo "===== NETWORK ====="
ip -br addr 2>/dev/null || ip addr || true
ip route || true
getent hosts stun.cloudflare.com 2>/dev/null | head -2 || echo "WARN: DNS lookup failed"

echo
echo "===== USB ====="
if command -v lsusb >/dev/null 2>&1; then
  lsusb || true
else
  echo "WARN: lsusb not installed"
fi

echo
echo "===== CAMERA ====="
CAM="$(find /dev/v4l/by-id -maxdepth 1 -type l -name '*Lenovo*video-index0*' 2>/dev/null | head -1)"
if [ -n "$CAM" ]; then
  echo "CAMERA_DEVICE=$CAM"
  if command -v v4l2-ctl >/dev/null 2>&1; then
    v4l2-ctl -d "$CAM" --all 2>/dev/null | sed -n '1,80p' || true
    echo "--- formats containing 1280x720 / MJPG ---"
    v4l2-ctl -d "$CAM" --list-formats-ext 2>/dev/null | grep -A8 -B2 -E 'MJPG|1280x720' | head -100 || true
  else
    echo "WARN: v4l2-ctl not installed"
  fi
else
  echo "WARN: stable Lenovo camera path not found"
fi

echo
echo "===== GSTREAMER ELEMENTS ====="
for elem in v4l2src jpegparse nvv4l2decoder nvvidconv nvv4l2h264enc h264parse webrtcbin; do
  if gst-inspect-1.0 "$elem" >/dev/null 2>&1; then
    echo "PASS $elem"
  else
    echo "MISS $elem"
  fi
done

echo
echo "===== PREFLIGHT COMPLETE ====="
echo "This script made no configuration changes."
