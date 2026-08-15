"""train_temporal_v2.py — McQueen temporal-policy training CLI (rehearsal-grade, NEW file).

Trains TemporalDrivingPolicy (PPGeo ResNet-34 backbone by default) on one or more
LeRobot datasets converted from Jetson recording spools (mcqueen_ml/dataset/convert_spool.py).

Usage (laptop env, PYTHONPATH=$PWD):
    python mcqueen_ml/training/train_temporal_v2.py \
        --root data/lerobot/rehearsal \
        --output data/checkpoints/rehearsal_temporal.pt \
        --epochs 10 --batch-size 16 --image-size 224

Datasets: each subdirectory of --root that contains data/<repo-id>/ is opened as a
LeRobotDataset(repo_id=<repo-id>, root=<subdir>). Episodes are remapped across datasets
so build_episode_index / compute_driving_stats / TemporalDrivingDatasetV2 work unchanged.

Checkpoint format (dict):
    model_state_dict, backbone, config (asdict), action_names, stats (servo/pwm mean+std),
    history, image_size, train_loss, val_loss, epochs, seed
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from mcqueen_ml.training.backbones import PPGeoResNet34Backbone
from mcqueen_ml.training.dataset_v2 import (
    TemporalDrivingDatasetV2,
    build_episode_index,
    compute_driving_stats,
)
from mcqueen_ml.training.model_config_v2 import TemporalPolicyConfig
from mcqueen_ml.training.temporal_policy_v2 import TemporalDrivingPolicy, TinyVisualBackbone

DEFAULT_PPGEO_CKPT = os.path.join(
    os.path.expanduser("~"), "Downloads", "mcqueen_ppgeo", "ppgeo_visual_encoder.pth"
)
ACTION_NAMES = ("servo_angle_deg", "motor_pwm")


def discover_datasets(root: Path) -> list[tuple[str, Path]]:
    found = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if (sub / "meta").is_dir():
            found.append((sub.name, sub))
    return found


class CombinedDataset:
    def __init__(self, datasets: list):
        self.datasets = datasets
        self.lengths = [len(d) for d in datasets]
        self.total = sum(self.lengths)
        self.offsets = [0]
        for length in self.lengths[:-1]:
            self.offsets.append(self.offsets[-1] + length)

    def __len__(self) -> int:
        return self.total

    def __getitem__(self, item: int) -> dict:
        if item < 0:
            item += self.total
        for i, (length, offset) in enumerate(zip(self.lengths, self.offsets)):
            if item < offset + length:
                sample = dict(self.datasets[i][item - offset])
                sample["episode_index"] = torch.as_tensor(
                    sample["episode_index"] + i * 1_000_000, dtype=torch.int64
                )
                return sample
        raise IndexError(item)


class CachedImageDataset:
    def __init__(self, base, image_size: tuple[int, int]):
        self.base = base
        self.image_size = image_size
        self.cache = {}

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, item: int) -> dict:
        cached = self.cache.get(item)
        if cached is not None:
            return cached
        sample = self.base[item]
        image = torch.as_tensor(sample["observation.images.front_rgb"], dtype=torch.float32)
        if image.shape[0] != 3 and image.shape[-1] == 3:
            image = image.permute(2, 0, 1)
        image = torch.nn.functional.interpolate(
            image.unsqueeze(0), size=self.image_size, mode="bilinear", align_corners=False
        ).squeeze(0)
        sample["observation.images.front_rgb"] = image
        self.cache[item] = sample
        return sample


def split_episodes(episode_map: dict[int, list[int]], val_fraction: float, seed: int):
    episodes = sorted(episode_map.keys())
    rng = random.Random(seed)
    rng.shuffle(episodes)
    n_val = max(1, int(round(len(episodes) * val_fraction))) if len(episodes) > 1 else 0
    val_eps = set(episodes[:n_val]) if n_val else set()
    train_eps = [e for e in episodes if e not in val_eps]
    return train_eps, sorted(val_eps)


def make_loaders(root: Path, val_fraction: float, seed: int, image_size: int, batch_size: int):
    pairs = discover_datasets(root)
    if not pairs:
        raise SystemExit(f"no LeRobot datasets found under {root}")
    datasets = []
    for repo_id, sub in pairs:
        from lerobot.datasets import LeRobotDataset

        datasets.append(LeRobotDataset(repo_id=repo_id, root=sub))
    combined = CombinedDataset(datasets)
    combined = CachedImageDataset(combined, (image_size, image_size))
    episode_map = build_episode_index(combined)
    train_eps, val_eps = split_episodes(episode_map, val_fraction, seed)
    if not train_eps:
        raise SystemExit("no training episodes after split")
    train_raw = [i for e in train_eps for i in episode_map[e]]
    stats = compute_driving_stats(combined, train_raw)

    dataset = TemporalDrivingDatasetV2(
        combined,
        episode_map,
        episodes=sorted(episode_map.keys()),
        stats=stats,
        history=6,
        image_size=(image_size, image_size),
    )
    train_set = set(train_eps)
    val_set = set(val_eps)
    train_positions = [i for i, (ep, _) in enumerate(dataset.samples) if ep in train_set]
    val_positions = [i for i, (ep, _) in enumerate(dataset.samples) if ep in val_set]
    if not train_positions:
        raise SystemExit("no training samples after split")

    train_loader = DataLoader(
        Subset(dataset, train_positions), batch_size=batch_size, shuffle=True, drop_last=False, num_workers=0
    )
    val_loader = (
        DataLoader(Subset(dataset, val_positions), batch_size=batch_size, shuffle=False, num_workers=0)
        if val_positions
        else None
    )
    return train_loader, val_loader, stats


def build_policy(backbone: str, device: torch.device, weights_path: str | None):
    config = TemporalPolicyConfig(backbone=backbone, history=6)
    if backbone == "tiny":
        visual = TinyVisualBackbone()
    elif backbone == "ppgeo_resnet34":
        path = weights_path or os.environ.get("MCQUEEN_PPGEO_CKPT") or DEFAULT_PPGEO_CKPT
        visual = PPGeoResNet34Backbone(weights_path=path)
    else:
        raise SystemExit(f"unsupported backbone: {backbone}")
    policy = TemporalDrivingPolicy(visual, visual.output_dim, config)
    return policy, config


def run_epoch(model, loader, optimizer, device, train: bool):
    model.train() if train else model.eval()
    total_loss, total = 0.0, 0
    with torch.set_grad_enabled(train):
        for batch in loader:
            frames = batch["frames"].to(device)
            wheels = batch["wheels"].to(device)
            prev_actions = batch["previous_actions"].to(device)
            target = batch["target_normalized"].to(device)
            prediction = model(frames, wheels, prev_actions)
            loss = nn.functional.mse_loss(prediction, target)
            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * target.size(0)
            total += target.size(0)
    return total_loss / max(total, 1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="McQueen temporal-policy training (rehearsal)")
    parser.add_argument("--root", required=True, help="dir containing one LeRobot dataset per subdir")
    parser.add_argument("--output", required=True, help="checkpoint .pt path")
    parser.add_argument("--backbone", default="ppgeo_resnet34", choices=("ppgeo_resnet34", "tiny"))
    parser.add_argument("--weights-path", default=None, help="PPGeo encoder .pth (default: MCQUEEN_PPGEO_CKPT or ~/Downloads/mcqueen_ppgeo)")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.device != "auto":
        device = torch.device(args.device)

    train_loader, val_loader, stats = make_loaders(
        Path(args.root), args.val_split, args.seed, args.image_size, args.batch_size
    )
    model, config = build_policy(args.backbone, device, args.weights_path)
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_val, best_state = float("inf"), None
    for epoch in range(1, args.epochs + 1):
        train_loss = run_epoch(model, train_loader, optimizer, device, train=True)
        val_loss = run_epoch(model, val_loader, optimizer, device, train=False) if val_loader else float("nan")
        print(f"epoch {epoch}/{args.epochs}  train={train_loss:.6f}  val={val_loss:.6f}", flush=True)
        if val_loader is not None and val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": best_state,
            "backbone": args.backbone,
            "config": asdict(config),
            "action_names": list(ACTION_NAMES),
            "stats": {
                "servo_mean": stats.action.mean[0].item(),
                "servo_std": stats.action.std[0].item(),
                "pwm_mean": stats.action.mean[1].item(),
                "pwm_std": stats.action.std[1].item(),
            },
            "history": 6,
            "image_size": args.image_size,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "epochs": args.epochs,
            "seed": args.seed,
        },
        output,
    )
    print(f"checkpoint saved: {output}  (best_val={best_val:.6f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())