#!/usr/bin/env python3
"""smoke_train_batch.py — single-batch training-pipeline smoke (NOT training).

Validates the full data path of train_temporal_v2.py WITHOUT a training loop:
  - LeRobot dataset discovery + open
  - episode index + stats + TemporalDrivingDatasetV2 construction
  - ONE batch: collate + model forward (tiny backbone) + shape/range checks
  - checkpoint dict save + reload (keys/state_dict shape contract)

Guardrails (DECISION 023 letter + spirit):
  - NO backward, NO optimizer, model.eval() — this is not training
  - hard 180 s wall-clock alarm (clean exit on timeout)
  - RAM guard: refuses to run if available memory < 3 GB
  - single batch (default 8), one forward, then exit

Usage (laptop env, PYTHONPATH=$PWD):
    python mcqueen_ml/training/smoke_train_batch.py \
        --root data/lerobot/rehearsal [--device cpu]
"""

from __future__ import annotations

import argparse
import os
import signal
import tempfile
from pathlib import Path

import torch

from mcqueen_ml.training.dataset_v2 import TemporalDrivingDatasetV2
from mcqueen_ml.training.train_temporal_v2 import (
    CachedImageDataset,
    CombinedDataset,
    build_policy,
    build_episode_index,
    compute_driving_stats,
    discover_datasets,
    split_episodes,
)


class SmokeTimeout(Exception):
    pass


def _ram_available_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024.0 / 1024.0
    except OSError:
        return float("inf")
    return float("inf")


def main() -> int:
    p = argparse.ArgumentParser(description="single-batch training-pipeline smoke")
    p.add_argument("--root", required=True)
    p.add_argument("--device", default="auto", help="auto (cuda if present), cpu, cuda")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--image-size", type=int, default=224)
    args = p.parse_args()

    def _timeout_handler(_sig, _frame):
        raise SmokeTimeout("smoke exceeded 180 s wall clock — aborting cleanly")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(180)

    avail = _ram_available_gb()
    print("[SMOKE] available RAM: {:.1f} GB (need >= 3.0)".format(avail), flush=True)
    if avail < 3.0:
        print("[SMOKE] ABORT: not enough free RAM — run at the lab instead", flush=True)
        return 2

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.device != "auto":
        device = torch.device(args.device)
    print("[SMOKE] device: {}".format(device), flush=True)

    from lerobot.datasets import LeRobotDataset

    pairs = discover_datasets(Path(args.root))
    if not pairs:
        print("[SMOKE] no datasets found under {}".format(args.root), flush=True)
        return 2
    datasets = [LeRobotDataset(repo_id=name, root=sub) for name, sub in pairs]
    combined = CachedImageDataset(
        CombinedDataset(datasets), (args.image_size, args.image_size)
    )
    episode_map = build_episode_index(combined)
    train_eps, _ = split_episodes(episode_map, 0.2, 42)
    train_raw = [i for e in train_eps for i in episode_map[e]]
    stats = compute_driving_stats(combined, train_raw)
    dataset = TemporalDrivingDatasetV2(
        combined,
        episode_map,
        episodes=sorted(episode_map.keys()),
        stats=stats,
        history=6,
        image_size=(args.image_size, args.image_size),
    )
    print("[SMOKE] samples: {} episodes: {}".format(len(dataset), len(episode_map)), flush=True)

    from torch.utils.data import DataLoader, Subset

    loader = DataLoader(
        Subset(dataset, list(range(min(args.batch_size, len(dataset))))),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )
    batch = next(iter(loader))
    print(
        "[SMOKE] batch keys: {} frames={} target={}".format(
            sorted(batch.keys()),
            tuple(batch["frames"].shape),
            tuple(batch["target_normalized"].shape),
        ),
        flush=True,
    )

    model, _ = build_policy("tiny", device, None)
    model.to(device)
    model.eval()
    with torch.no_grad():
        out = model(
            batch["frames"].to(device),
            batch["wheels"].to(device),
            batch["previous_actions"].to(device),
        )
    print("[SMOKE] forward out shape: {} dtype: {}".format(tuple(out.shape), out.dtype), flush=True)
    assert out.shape == (args.batch_size, 2), "unexpected output shape"

    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp:
        ckpt_path = tmp.name
    torch.save(
        {
            "model_state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
            "backbone": "tiny",
            "history": 6,
            "image_size": args.image_size,
        },
        ckpt_path,
    )
    reloaded = torch.load(ckpt_path, map_location="cpu")
    assert sorted(reloaded.keys()) == sorted(
        ["model_state_dict", "backbone", "history", "image_size"]
    ), "checkpoint contract changed"
    assert list(reloaded["model_state_dict"].keys()) == list(model.state_dict().keys())
    os.unlink(ckpt_path)
    print("[SMOKE] checkpoint save/reload contract OK", flush=True)

    signal.alarm(0)
    print("[SMOKE] PASS — pipeline ready for the lab training run", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())