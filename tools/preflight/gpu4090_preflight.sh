#!/usr/bin/env bash
set -u

echo "===== McQueen 4090 preflight — NO INSTALLS ====="

echo
echo "===== SYSTEM ====="
hostname
whoami
cat /etc/os-release | head -6

echo
echo "===== GPU ====="
nvidia-smi || true

echo
echo "===== STORAGE / RAM ====="
df -h ~
free -h

echo
echo "===== PYTHON / GIT / CONDA ====="
python3 --version || true
git --version || true
command -v conda || true
conda --version 2>/dev/null || true

echo
echo "===== CONDA ENVS ====="
conda env list 2>/dev/null || true

echo
echo "===== EXISTING MCQUEEN REPOS ====="
find ~ -maxdepth 3 -type d -name McQueen -print 2>/dev/null

echo
echo "===== LEROBOT ENV ====="
if conda env list 2>/dev/null | awk '{print $1}' | grep -qx lerobot; then
  conda run -n lerobot python - <<'PY'
import sys
print("Python:", sys.version.split()[0])

try:
    import torch
    print("Torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
except Exception as e:
    print("Torch import failed:", repr(e))

try:
    import lerobot
    print("LeRobot:", getattr(lerobot, "__version__", "installed/no __version__"))
    print("LeRobot path:", getattr(lerobot, "__file__", "?"))
except Exception as e:
    print("LeRobot import failed:", repr(e))

try:
    import wandb
    print("W&B:", wandb.__version__)
except Exception as e:
    print("W&B import failed:", repr(e))
PY
else
  echo "No conda env named 'lerobot'."
fi

echo
echo "===== GPU PROCESS SNAPSHOT ====="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null || true

echo
echo "===== IMPORTANT ====="
echo "No packages were installed and no GPU jobs were started."
echo "Send this output before changing the 4090 environment."
