"""prepack_sessions.py — pre-pack McQueen session frames into supercombo YUV .npy.

Reads session dirs produced by tub_to_sessions.py (rgb_raw_upright/frame_*.jpg,
original donkey 160x120 JPEGs) and writes frame_*.npy next to each JPEG:
packed YUV (6,128,256) uint8 — the exact input format of supercombo's `img`
channel (replicated from models/action_adapter.py rgb_to_supercombo_yuv).

Removes the JPEG decode + resize cost from the training loop (14k frames are
precomputed once; the trainer preloads .npy into RAM).

Requires cv2 + numpy (mcqueen-openpilot env on the RTX). Torch-free.

Usage (RTX):
    PYTHONPATH=~/mcqueen/models:~/.local python tools/donkey/prepack_sessions.py \
        --root ~/mcqueen/run/donkey_sessions/train
    PYTHONPATH=~/mcqueen/models:~/.local python tools/donkey/prepack_sessions.py \
        --root ~/mcqueen/run/donkey_sessions/val
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    from action_adapter import rgb_to_supercombo_yuv
except ImportError:
    sys.exit("cannot import action_adapter.rgb_to_supercombo_yuv — set PYTHONPATH to the "
             "dir holding models/action_adapter.py (mcqueen-openpilot env, RTX)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, help="sessions root (train or val)")
    args = ap.parse_args()

    root = Path(args.root)
    sessions = sorted(root.glob("session_*")) if root.is_dir() else []
    if not sessions:
        sys.exit(f"no session_* dirs under {root}")

    n_packed = 0
    for session in sessions:
        frame_dir = session / "rgb_raw_upright"
        for jpg in sorted(frame_dir.glob("frame_*.jpg")):
            npy = jpg.with_suffix(".npy")
            if npy.exists():
                continue
            bgr = cv2.imread(str(jpg))
            if bgr is None:
                raise RuntimeError(f"failed to decode {jpg}")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            rgb = cv2.resize(rgb, (512, 256), interpolation=cv2.INTER_AREA)
            packed = rgb_to_supercombo_yuv(rgb).astype(np.uint8)
            np.save(npy, packed)
            n_packed += 1
        print(f"packed {session.name}", file=sys.stderr)

    print(f"packed {n_packed} frames under {root}")


if __name__ == "__main__":
    main()