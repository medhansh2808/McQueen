"""train_frozen_action.py — McQueen temporal action-head trainer (donkey-tub data).

Model: comma 2026-master driving_supercombo.onnx trunk (FROZEN, via
action_adapter.FrozenActionModel) + trainable MLP head on hidden_state[512]:
    Linear(512,128) -> ReLU -> Linear(128,2) -> [steering, throttle]

Data: McQueen session dirs produced by tools/donkey/tub_to_sessions.py +
tools/donkey/prepack_sessions.py (frames pre-packed to (6,128,256) uint8 .npy):
    <root>/session_XXX/controls.csv  (steering, throttle in [-1,1])
    <root>/session_XXX/rgb_raw_upright/frame_000000.npy ... (packed YUV)

Labels are normalized with train-set mean/std; val MSE reported denormalized.

Training is batched for high GPU utilization (machine is ours): within a
session, contiguous windows form batches; a per-sample features_buffer
[B,24,512] carries temporal state across batches of the same session and
resets at session boundaries. Mixed precision (fp16 AMP) throughout.

Usage (RTX, mcqueen-openpilot env, run from the dir containing action_adapter.py):
    PYTHONPATH=~/mcqueen/models python train_frozen_action.py \
        --onnx ~/mcqueen/models/driving_supercombo_master.onnx \
        --sessions-root ~/mcqueen/run/donkey_sessions/train \
        --val-root ~/mcqueen/run/donkey_sessions/val \
        --out ~/mcqueen/models/donkey_head_best.pt \
        --epochs 25 --batch-size 32 --lr 1e-4

Checkpoint (dict): model_state_dict (head only), backbone, config (asdict),
action_names, stats (steering/throttle mean+std), history, epochs, seed.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.amp import GradScaler, autocast

from action_adapter import FrozenActionModel, action_to_command_torch

FRAME_GLOB = "rgb_raw_upright/frame_*.npy"
ACTION_NAMES = ("steering", "throttle")


@dataclass
class HeadConfig:
    hidden: int = 128
    in_dim: int = 512
    out_dim: int = 2


class ActionHead(nn.Module):
    def __init__(self, cfg: HeadConfig):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.in_dim, cfg.hidden),
            nn.ReLU(),
            nn.Linear(cfg.hidden, cfg.out_dim),
        )

    def forward(self, hidden_state: torch.Tensor) -> torch.Tensor:
        return self.net(hidden_state)


class SessionData:
    """One converted session, preloaded into CPU tensors (frames + labels)."""

    def __init__(self, session_dir: Path):
        frames = sorted(glob.glob(str(session_dir / FRAME_GLOB)))
        if not frames:
            raise RuntimeError(f"no packed frames ({FRAME_GLOB}) in {session_dir}")
        with open(session_dir / "controls.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != len(frames):
            raise RuntimeError(
                f"label/frame mismatch in {session_dir}: {len(rows)} labels vs {len(frames)} frames"
            )
        self.session_dir = session_dir
        self.frames = np.stack([np.load(p) for p in frames]).astype(np.uint8)  # (T,6,128,256)
        self.labels = np.array(
            [[float(r["steering"]), float(r["throttle"])] for r in rows], dtype=np.float32
        )
        self.length = len(frames)

    def window(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """Consecutive pair (f_{i-1}, f_i) + label of f_i; valid for i in [1, T)."""
        return self.frames[i - 1], self.frames[i]


def load_sessions(root: Path) -> list[SessionData]:
    sessions = [SessionData(d) for d in sorted(root.glob("session_*")) if d.is_dir()]
    print(f"loaded {len(sessions)} sessions from {root}, "
          f"{sum(s.length for s in sessions)} frames total", file=sys.stderr)
    if not sessions:
        raise RuntimeError(f"no sessions in {root}")
    return sessions


def compute_label_stats(sessions: list[SessionData]) -> dict:
    labels = np.concatenate([s.labels[1:] for s in sessions], axis=0)
    mean = labels.mean(axis=0)
    std = labels.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return {"mean": mean.tolist(), "std": std.tolist()}


def run_epoch(
    model: nn.Module,
    head: nn.Module,
    sessions: list[SessionData],
    stats: dict,
    device: torch.device,
    *,
    train: bool,
    opt=None,
    scaler=None,
    batch_size: int = 32,
) -> float:
    mean = torch.tensor(stats["mean"], device=device)
    std = torch.tensor(stats["std"], device=device)
    zeros_desire = torch.zeros(batch_size, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)

    head.train(train)
    model.train(train)
    total_loss, total_n = 0.0, 0

    order = sessions if train else sessions
    if train:
        random.shuffle(order)

    for session in order:
        n_windows = session.length - 1
        if n_windows <= 0:
            continue
        # per-sample temporal buffer: [B,24,512]; rolled per batch, reset per session
        buffer = torch.zeros(batch_size, 24, 512, dtype=torch.float16, device=device)
        for start in range(0, n_windows, batch_size):
            ids = list(range(start, min(start + batch_size, n_windows)))
            b = len(ids)
            if b < batch_size:  # tail batch: trim constant tensors
                d = torch.zeros(b, 25, 8, dtype=torch.float16, device=device)
                t = torch.zeros(b, 2, dtype=torch.float16, device=device)
                a = torch.zeros(b, 2, dtype=torch.float16, device=device)
            else:
                d, t, a = zeros_desire, zeros_traffic, zeros_action_t

            img = np.stack(
                [np.concatenate([session.window(i)[0], session.window(i)[1]], axis=0) for i in ids],
                axis=0,
            )  # (B,12,128,256) uint8
            img_t = torch.from_numpy(img).to(device)
            labels = session.labels[ids]  # (B,2)
            labels_t = torch.from_numpy(labels).to(device)
            norm_labels = (labels_t - mean) / std

            with torch.set_grad_enabled(train), autocast("cuda"):
                action, hidden_state, _ = model(
                    img=img_t, big_img=img_t,
                    desire_pulse=d, traffic_convention=t, action_t=a,
                    features_buffer=buffer[:b],
                )
                pred = head(hidden_state)  # (B,2) normalized
                loss = nn.functional.mse_loss(pred, norm_labels)

            if train:
                opt.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()

            total_loss += loss.item() * b
            total_n += b

            with torch.no_grad():
                buffer = torch.cat([buffer[:b, 1:, :], hidden_state.detach().unsqueeze(1).to(buffer.dtype)], dim=1)

    return total_loss / max(1, total_n)


def zero_shot_mse(model: nn.Module, sessions: list[SessionData], device: torch.device,
                  batch_size: int = 32) -> float:
    """Plan-derived action -> steering/throttle (action_to_command_torch) vs labels."""
    zeros_desire = torch.zeros(batch_size, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)
    err_sq, n = 0.0, 0
    model.eval()
    with torch.no_grad(), autocast("cuda"):
        for session in sessions:
            buffer = torch.zeros(batch_size, 24, 512, dtype=torch.float16, device=device)
            for start in range(0, session.length - 1, batch_size):
                ids = list(range(start, min(start + batch_size, session.length - 1)))
                b = len(ids)
                img = np.stack(
                    [np.concatenate([session.window(i)[0], session.window(i)[1]], axis=0)
                     for i in ids], axis=0)
                img_t = torch.from_numpy(img).to(device)
                action, hidden_state, _ = model(
                    img=img_t, big_img=img_t,
                    desire_pulse=zeros_desire[:b], traffic_convention=zeros_traffic[:b],
                    action_t=zeros_action_t[:b], features_buffer=buffer[:b],
                )
                labels = torch.from_numpy(session.labels[ids]).to(device)
                for k in range(b):
                    steer, throttle = action_to_command_torch(action[k : k + 1], v_ego=0.0)
                    pred = torch.stack([steer, throttle]).squeeze().float()
                    err_sq += ((pred - labels[k]) ** 2).sum().item()
                    n += 2
                buffer = torch.cat([buffer[:b, 1:, :], hidden_state.detach().unsqueeze(1).to(buffer.dtype)], dim=1)
    return err_sq / max(1, n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--sessions-root", required=True)
    ap.add_argument("--val-root", required=True)
    ap.add_argument("--out", default="donkey_head_best.pt")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--smoke", action="store_true", help="single train batch, no val, quick exit")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    model = FrozenActionModel(args.onnx).to(device)
    head = ActionHead(HeadConfig()).to(device)
    n_head = sum(p.numel() for p in head.parameters())
    print(f"trainable head: {n_head} params ({n_head:,})")

    train_sessions = load_sessions(Path(args.sessions_root))
    val_sessions = load_sessions(Path(args.val_root))
    stats = compute_label_stats(train_sessions)
    print(f"label stats: mean={stats['mean']} std={stats['std']}")

    opt = torch.optim.AdamW(head.parameters(), lr=args.lr, eps=1e-4)
    scaler = GradScaler("cuda")

    if args.smoke:
        loss = run_epoch(model, head, train_sessions[:1], stats, device,
                         train=True, opt=opt, scaler=scaler, batch_size=args.batch_size)
        print(f"SMOKE OK  train loss={loss:.5f}")
        return

    best_val = float("inf")
    history = []
    t0 = time.time()
    for epoch in range(args.epochs):
        t_ep = time.time()
        tr = run_epoch(model, head, train_sessions, stats, device,
                       train=True, opt=opt, scaler=scaler, batch_size=args.batch_size)
        va = run_epoch(model, head, val_sessions, stats, device,
                       train=False, batch_size=args.batch_size)
        zs = zero_shot_mse(model, val_sessions, device, batch_size=args.batch_size)
        elapsed = time.time() - t_ep
        history.append({"train_loss": tr, "val_mse": va, "zero_shot_mse": zs})
        tag = ""
        if va < best_val:
            best_val = va
            tag = "  *best*"
            torch.save(
                {
                    "model_state_dict": head.state_dict(),
                    "head_config": HeadConfig().__dict__,
                    "backbone": "supercombo_frozen",
                    "action_names": list(ACTION_NAMES),
                    "stats": stats,
                    "history": history,
                    "epochs": epoch + 1,
                    "seed": args.seed,
                },
                args.out,
            )
        print(f"epoch {epoch:03d}  train={tr:.5f}  val_mse={va:.5f}  zero_shot_mse={zs:.5f}"
              f"  {elapsed:.0f}s{tag}", flush=True)
        eta = (time.time() - t0) / (epoch + 1) * (args.epochs - epoch - 1)
        print(f"  ETA remaining: {eta:.0f}s", flush=True)

    print(f"best val_mse={best_val:.5f}  saved -> {args.out}")


if __name__ == "__main__":
    main()
