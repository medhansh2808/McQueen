#!/usr/bin/env bash
set -u

echo "===== McQUEEN RTX4090 PREFLIGHT V2 ====="
echo "host: $(hostname)"
echo "date: $(date -Is 2>/dev/null || date)"
echo

echo "===== GPU ====="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi || true
else
  echo "WARN: nvidia-smi not found"
fi

echo
echo "===== STORAGE ====="
df -h "$HOME" /var/tmp 2>/dev/null || df -h || true

echo
echo "===== REPO ====="
for REPO in "$HOME/McQueen" "/var/tmp/mcqueen-junior/McQueen"; do
  if [ -d "$REPO/.git" ]; then
    echo "REPO=$REPO"
    (cd "$REPO" && git status --short --branch && git log -1 --oneline --decorate) || true
  fi
done

echo
echo "===== KNOWN LEROBOT ENV ====="
PY="$HOME/miniforge3/envs/lerobot/bin/python"
if [ -x "$PY" ]; then
  echo "PYTHON=$PY"
  "$PY" - <<'INNERPY'
import sys
print("python", sys.version.replace("\n", " "))
try:
    import torch
    print("torch", torch.__version__)
    print("cuda", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("gpu", torch.cuda.get_device_name(0))
except Exception as exc:
    print("torch_error", repr(exc))
try:
    import lerobot
    print("lerobot", getattr(lerobot, "__version__", "unknown"))
except Exception as exc:
    print("lerobot_error", repr(exc))
INNERPY
else
  echo "WARN: known lerobot env missing at $PY"
fi

echo
echo "===== GPU PROCESSES ====="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null || true
else
  echo "WARN: nvidia-smi not found"
fi

echo
echo "===== PREFLIGHT COMPLETE ====="
echo "No packages were installed and no processes were killed."
