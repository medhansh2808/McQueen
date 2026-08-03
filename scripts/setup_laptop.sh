#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
  pwd
)"

MINIFORGE_ROOT="${MINIFORGE_ROOT:-$HOME/miniforge3}"
CONDA="$MINIFORGE_ROOT/bin/conda"
ENV_NAME="mcqueen-ml"

echo "===== SYSTEM DEPENDENCIES ====="

sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  wget \
  git \
  rsync \
  build-essential \
  cmake \
  pkg-config \
  python3-dev

if [ ! -x "$CONDA" ]; then
  echo
  echo "===== INSTALLING MINIFORGE ====="
  INSTALLER="/tmp/Miniforge3-$(uname)-$(uname -m).sh"
  URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
  wget -O "$INSTALLER" "$URL"
  bash "$INSTALLER" -b -p "$MINIFORGE_ROOT"
else
  echo "Miniforge already installed: $MINIFORGE_ROOT"
fi

if ! "$CONDA" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo
  echo "===== CREATING CONDA ENVIRONMENT ====="
  "$CONDA" create -y -n "$ENV_NAME" python=3.12 pip
else
  echo "Conda environment already exists: $ENV_NAME"
fi

echo
echo "===== INSTALLING FFMPEG ====="
"$CONDA" install -y -n "$ENV_NAME" -c conda-forge ffmpeg=7.1.1

echo
echo "===== INSTALLING CUDA PYTORCH ====="
"$CONDA" run -n "$ENV_NAME" python -m pip install --upgrade \
  pip setuptools wheel

"$CONDA" run -n "$ENV_NAME" python -m pip install \
  torch==2.11.0 \
  torchvision==0.26.0 \
  --index-url https://download.pytorch.org/whl/cu128

echo
echo "===== INSTALLING LEROBOT + W&B + VISUALIZATION ====="
"$CONDA" run -n "$ENV_NAME" python -m pip install \
  'lerobot[training,dataset_viz]==0.6.0'

echo
echo "===== INSTALLING MCQUEEN PACKAGE ====="
"$CONDA" run -n "$ENV_NAME" python -m pip install \
  --editable "$REPO_ROOT" \
  --no-deps

echo
echo "===== VERIFYING DEPENDENCIES ====="
"$CONDA" run -n "$ENV_NAME" python -m pip check

mkdir -p "$REPO_ROOT/environments"

"$CONDA" env export -n "$ENV_NAME" --from-history \
  > "$REPO_ROOT/environments/conda-history.yml"

"$CONDA" run -n "$ENV_NAME" python -m pip freeze \
  > "$REPO_ROOT/environments/pip-freeze-linux-x86_64.txt"

nvidia-smi > "$REPO_ROOT/environments/nvidia-smi.txt"

"$CONDA" run -n "$ENV_NAME" python - <<'PY'
import sys
import torch
import lerobot
import wandb

print("Python:", sys.version.split()[0])
print("LeRobot:", lerobot.__version__)
print("W&B:", wandb.__version__)
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise SystemExit("ERROR: CUDA is not available inside mcqueen-ml")

print("GPU:", torch.cuda.get_device_name(0))
print(
    "VRAM GB:",
    round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2),
)
PY

echo
echo "PHASE 7 COMPLETE"
