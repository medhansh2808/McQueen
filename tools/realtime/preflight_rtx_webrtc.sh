#!/usr/bin/env bash
set -u

echo "===== MCQUEEN RTX WEBRTC PREFLIGHT ====="
echo "Host : $(hostname)"
echo "User : $(id -un)"
echo "OS   : $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"

PY="${1:-python3}"
echo "Python command: $PY"
"$PY" --version 2>&1 || true

echo
echo "===== PYTHON MODULES ====="
"$PY" - <<'PY'
mods = ["torch", "aiortc", "av", "aiohttp", "cv2", "numpy", "wandb"]
for name in mods:
    try:
        mod = __import__(name)
        version = getattr(mod, "__version__", "(no __version__)")
        print(f"{name:10s} [PASS] {version}")
    except Exception as e:
        print(f"{name:10s} [MISSING] {type(e).__name__}: {e}")
PY

echo
echo "===== GPU ====="
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu \
    --format=csv,noheader 2>/dev/null || true

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
echo "===== PORTS OF INTEREST ====="
ss -lntup 2>/dev/null | grep -E ':(8765|8766|5006|5007|8080|8443)\b' || \
    echo "(none of the McQueen candidate ports are listening)"

echo "===== DONE ====="
