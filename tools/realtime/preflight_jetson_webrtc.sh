#!/usr/bin/env bash
set -u

echo "===== MCQUEEN JETSON WEBRTC PREFLIGHT ====="
echo "Host : $(hostname)"
echo "User : $(id -un)"
echo "Arch : $(uname -m)"
echo "OS   : $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
echo "Python: $(python3 --version 2>&1 || true)"

echo
echo "===== GSTREAMER ====="
if command -v gst-inspect-1.0 >/dev/null 2>&1; then
    gst-inspect-1.0 --version
else
    echo "[FAIL] gst-inspect-1.0 not found"
fi

check_plugin() {
    local plugin="$1"
    printf "%-24s " "$plugin"
    if gst-inspect-1.0 "$plugin" >/dev/null 2>&1; then
        echo "[PASS]"
    else
        echo "[MISSING]"
    fi
}

echo
echo "===== REQUIRED / USEFUL GSTREAMER ELEMENTS ====="
for p in \
    webrtcbin \
    v4l2src \
    videoconvert \
    videoscale \
    queue \
    h264parse \
    rtph264pay \
    rtpvp8pay \
    vp8enc \
    nvv4l2h264enc \
    nvv4l2vp8enc \
    nvvidconv \
    appsink \
    appsrc
do
    check_plugin "$p"
done

echo
echo "===== WEBRTC DETAILS ====="
gst-inspect-1.0 webrtcbin 2>/dev/null | sed -n '1,80p' || true

echo
echo "===== NVIDIA ENCODER DETAILS ====="
gst-inspect-1.0 nvv4l2h264enc 2>/dev/null | sed -n '1,100p' || true

echo
echo "===== CAMERA DEVICES ====="
ls -l /dev/video* 2>/dev/null || echo "(no /dev/video* devices)"
echo
ls -l /dev/v4l/by-id/ 2>/dev/null || true

echo
echo "===== V4L2 MODES ====="
CAM="$(find /dev/v4l/by-id -type l -name '*Lenovo*video-index0' 2>/dev/null | head -1)"
if [ -n "${CAM:-}" ] && command -v v4l2-ctl >/dev/null 2>&1; then
    echo "Camera: $CAM"
    v4l2-ctl -d "$CAM" --list-formats-ext 2>/dev/null | sed -n '1,160p' || true
else
    echo "[INFO] Lenovo camera or v4l2-ctl not available"
fi

echo
echo "===== NETWORK ====="
ip -brief addr 2>/dev/null || true

echo
echo "===== TAILSCALE ====="
if command -v tailscale >/dev/null 2>&1; then
    tailscale version || true
    tailscale status || true
    tailscale ip -4 2>/dev/null || true
else
    echo "[INFO] Tailscale not installed yet"
fi

echo
echo "===== SUMMARY HINT ====="
if gst-inspect-1.0 webrtcbin >/dev/null 2>&1 && \
   gst-inspect-1.0 nvv4l2h264enc >/dev/null 2>&1; then
    echo "[GOOD] Jetson has webrtcbin + NVIDIA H.264 hardware encoder."
    echo "Preferred prototype path: v4l2src -> NVIDIA H.264 -> webrtcbin."
elif gst-inspect-1.0 webrtcbin >/dev/null 2>&1; then
    echo "[PARTIAL] webrtcbin exists, but NVIDIA H.264 encoder was not found."
    echo "Inspect available encoders before installing anything."
else
    echo "[BLOCKED] webrtcbin is missing. Do not guess-install yet; inspect apt/plugin state."
fi

echo "===== DONE ====="
