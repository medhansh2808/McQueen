"""eval_donkey_predictions.py — val-window prediction MSE table (no training).

Loads the frozen supercombo trunk + the trained MLP head checkpoint produced by
train_frozen_action.py, runs every val window, and reports:

    method           | steering MSE | throttle MSE | combined MSE
    zero-shot        | ...
    trained head     | ...

Zero-shot = plan-derived action via action_to_command_torch (v_ego=0, comma
master math). Both reported in the tub label space ([-1,1] steering/throttle).

Usage (RTX, mcqueen-openpilot env, run from the dir holding action_adapter.py):
    PYTHONPATH=~/mcqueen/models python eval_donkey_predictions.py \
        --onnx ~/mcqueen/models/driving_supercombo_master.onnx \
        --ckpt ~/mcqueen/models/donkey_head_best.pt \
        --val-root ~/mcqueen/run/donkey_sessions/val \
        --batch-size 32
"""

from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

import numpy as np
import torch
from torch.amp import autocast

from action_adapter import FrozenActionModel, action_to_command_torch
from train_frozen_action import ActionHead, HeadConfig, SessionData, load_sessions


def evaluate(method: str, model, head, stats, sessions, device, batch_size) -> dict:
    mean = torch.tensor(stats["mean"], device=device)
    std = torch.tensor(stats["std"], device=device)
    zeros_desire = torch.zeros(batch_size, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)

    sums = {"steer": 0.0, "throttle": 0.0, "n": 0}
    model.eval()
    if head is not None:
        head.eval()

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
                _, hidden_state, _ = model(
                    img=img_t, big_img=img_t,
                    desire_pulse=zeros_desire[:b], traffic_convention=zeros_traffic[:b],
                    action_t=zeros_action_t[:b], features_buffer=buffer[:b],
                )
                labels = session.labels[ids]

                if method == "zero-shot":
                    action, _, _ = model(
                        img=img_t, big_img=img_t,
                        desire_pulse=zeros_desire[:b], traffic_convention=zeros_traffic[:b],
                        action_t=zeros_action_t[:b], features_buffer=buffer[:b],
                    )
                    preds = np.stack(
                        [torch.stack(action_to_command_torch(action[k : k + 1], v_ego=0.0))
                         .squeeze().float().cpu().numpy() for k in range(b)],
                        axis=0,
                    )
                else:  # trained head
                    pred_norm = head(hidden_state).float()
                    preds = (pred_norm * std + mean).cpu().numpy()

                sums["steer"] += float(((preds[:, 0] - labels[:, 0]) ** 2).sum())
                sums["throttle"] += float(((preds[:, 1] - labels[:, 1]) ** 2).sum())
                sums["n"] += b
                buffer = torch.cat([buffer[:b, 1:, :], hidden_state.detach().unsqueeze(1).to(buffer.dtype)], dim=1)

    n = max(1, sums["n"])
    return {
        "steer_mse": sums["steer"] / n,
        "throttle_mse": sums["throttle"] / n,
        "combined_mse": (sums["steer"] + sums["throttle"]) / (2 * n),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--ckpt", required=True, help="train_frozen_action.py checkpoint")
    ap.add_argument("--val-root", required=True)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    ckpt = torch.load(args.ckpt, map_location="cpu")
    stats = ckpt["stats"]

    model = FrozenActionModel(args.onnx).to(device)
    head = ActionHead(HeadConfig(**ckpt["head_config"])).to(device)
    head.load_state_dict(ckpt["model_state_dict"])
    print(f"head from ckpt: backbone={ckpt['backbone']}, action_names={ckpt['action_names']}, "
          f"epochs={ckpt['epochs']}, history tail={ckpt['history'][-1]}")

    sessions = load_sessions(Path(args.val_root))
    print(f"val windows: {sum(max(0, s.length - 1) for s in sessions)}")

    rows = [("zero-shot", evaluate("zero-shot", model, None, stats, sessions, device, args.batch_size)),
            ("trained head", evaluate("head", model, head, stats, sessions, device, args.batch_size))]

    print(f"\n{'method':<14} {'steer MSE':>10} {'throttle MSE':>12} {'combined MSE':>12}")
    for name, r in rows:
        print(f"{name:<14} {r['steer_mse']:>10.5f} {r['throttle_mse']:>12.5f} {r['combined_mse']:>12.5f}")

    zs, th = rows[0][1]["combined_mse"], rows[1][1]["combined_mse"]
    print(f"\nverdict: trained head vs zero-shot = {th / zs:.2f}x combined MSE "
          f"({'better' if th < zs else 'worse'})")


if __name__ == "__main__":
    main()