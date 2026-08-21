"""train_chestnut_lora.py — LoRA fine-tune chestnut on donkey-sim data.

Model: comma chestnut big_driving_supercombo.onnx (converted module
chestnut_onnx2torch_sd.pt, FROZEN) + hand-rolled LoRA (no peft): forward
hooks on EXACT nn.Linear instances (onnx2pytorch custom ops are subclasses
and are excluded), parameters in a LoRABank. Serialization-safe: LoRAModule
re-registers hooks in __setstate__.

Labels (assumed-v mapping, DECISION 2026-08-18, CORRECTED v3): training
    targets are RAW curvature (model's natural action-head scale ~[-1,1]):
    action[0] = tan(steer * MAX_STEER_ANGLE_RAD) / CAR_LENGTH_M.
    The openpilot curv*v^2 scale is applied at RUNTIME by chestnut_pilot:
    curv = action[0] * V_ASSUMED^2 / max(curv_floor, v_ego)^2 with
    V_ASSUMED = 3.0 and curv_floor = V_ASSUMED (round-trips the dataset
    steering exactly at v_ego = 3.0). v2 (curv*v^2 targets) overshot OOD
    (action 60 vs max label 26) -> crashes in sim.
    action[1] = desired_accel   = throttle * MAX_ACCEL (2.0 m/s^2 scale)
Loss: weighted MSE over action[0:2] (steer weight 0.7, accel 0.3).

Simplifications (documented): features_buffer = zeros per batch (the model
appends the current feature; inference still rolls a real 24-frame buffer);
big_img = img; desire/traffic/action_t = zeros.

Checkpoint (dict): model (LoRAModule, loadable by chestnut_pilot --module),
history, epochs, seed, lora_cfg.

Usage (RTX, mcqueen-openpilot env, run from the dir with the module):
    python train_chestnut_lora.py \
        --module ~/mcqueen/models/chestnut_onnx2torch_sd.pt \
        --sessions-root ~/mcqueen/run/donkey_sessions/train \
        --val-root ~/mcqueen/run/donkey_sessions/val \
        --out ~/mcqueen/models/chestnut_lora_best.pt \
        --epochs 10 --batch-size 16 --lr 1e-4
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.amp import GradScaler, autocast

from train_frozen_action import SessionData, load_sessions

CAR_LENGTH_M = 0.35
MAX_STEER_ANGLE_RAD = 0.78
MAX_ACCEL = 2.0
STEER_W = 0.7
ACCEL_W = 0.3
V_ASSUMED = 3.0  # dataset driving speed (m/s): labels are curv*v^2 (openpilot scale)


class _LoraHook:
    """Picklable forward hook: adds LoRA delta to the output of one Linear."""

    def __init__(self, mod: "LoRAModule", name: str):
        self.mod = mod
        self.name = name

    def __call__(self, module, args, output):
        mod, name = self.mod, self.name
        scale = mod.alpha / mod.r
        a = mod.bank[f"{name}__A"]
        b = mod.bank[f"{name}__B"]
        return output + (args[0].float() @ a.float() @ b.float() * scale).to(output.dtype)


class LoRAModule(nn.Module):
    """Frozen base + rank-r LoRA on exact nn.Linear layers via forward hooks."""

    def __init__(self, base: nn.Module, r: int = 16, alpha: int = 32, seed: int = 0):
        super().__init__()
        self.base = base
        self.r = r
        self.alpha = alpha
        self.bank = nn.ParameterDict()
        g = torch.Generator().manual_seed(seed)
        for name, m in base.named_modules():
            if type(m) is nn.Linear:
                self.bank[f"{name}__A"] = nn.Parameter(
                    torch.randn(m.in_features, r, generator=g) * 0.01)
                self.bank[f"{name}__B"] = nn.Parameter(torch.zeros(r, m.out_features))
        self._register_hooks()

    def _register_hooks(self):
        self._hooks = []
        for name, m in self.base.named_modules():
            if type(m) is nn.Linear:
                self._hooks.append(m.register_forward_hook(_LoraHook(self, name)))

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._register_hooks()

    def forward(self, *args):
        return self.base(*args)


def label_to_action(labels: np.ndarray) -> np.ndarray:
    steer = labels[:, 0]
    throttle = labels[:, 1]
    curv = np.tan(steer * MAX_STEER_ANGLE_RAD) / CAR_LENGTH_M
    accel = throttle * MAX_ACCEL
    return np.stack([curv, accel], axis=1).astype(np.float32)


def run_epoch(
    model: nn.Module,
    sessions: list[SessionData],
    device: torch.device,
    *,
    train: bool,
    opt=None,
    scaler=None,
    batch_size: int = 16,
) -> float:
    zeros_desire = torch.zeros(batch_size, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(batch_size, 2, dtype=torch.float16, device=device)

    model.train(train)
    total_loss, total_n = 0.0, 0

    order = sessions[:]
    if train:
        random.shuffle(order)

    for session in order:
        n_windows = session.length - 1
        if n_windows <= 0:
            continue
        for start in range(0, n_windows, batch_size):
            ids = list(range(start, min(start + batch_size, n_windows)))
            b = len(ids)
            d = zeros_desire[:b] if b == batch_size else torch.zeros(b, 25, 8, dtype=torch.float16, device=device)
            t = zeros_traffic[:b] if b == batch_size else torch.zeros(b, 2, dtype=torch.float16, device=device)
            a = zeros_action_t[:b] if b == batch_size else torch.zeros(b, 2, dtype=torch.float16, device=device)
            buffer = torch.zeros(b, 24, 512, dtype=torch.float16, device=device)

            img = np.stack(
                [np.concatenate([session.window(i)[0], session.window(i)[1]], axis=0) for i in ids],
                axis=0,
            )
            img_t = torch.from_numpy(img).to(device)
            targets = torch.from_numpy(label_to_action(session.labels[ids])).to(device)

            with torch.set_grad_enabled(train), autocast("cuda"):
                out = model(img_t, img_t, d, t, a, buffer)
                if isinstance(out, (tuple, list)):
                    out = out[0]
                out = out.view(b, -1).float()
                pred = out[:, 2062:2064]
                loss = STEER_W * torch.nn.functional.mse_loss(pred[:, 0], targets[:, 0]) \
                     + ACCEL_W * torch.nn.functional.mse_loss(pred[:, 1], targets[:, 1])

            if train:
                opt.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()

            total_loss += loss.item() * b
            total_n += b

    return total_loss / max(1, total_n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", default="chestnut_onnx2torch_sd.pt")
    ap.add_argument("--sessions-root", required=True)
    ap.add_argument("--val-root", required=True)
    ap.add_argument("--out", default="chestnut_lora_best.pt")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--r", type=int, default=16, help="LoRA rank")
    ap.add_argument("--alpha", type=int, default=32, help="LoRA alpha")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--smoke", action="store_true", help="single train batch, quick exit")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    state = torch.load(args.module, map_location="cpu", weights_only=False)
    base = state["model"]
    base = base.to(device).half().eval()
    for p in base.parameters():
        p.requires_grad = False
    print(f"base trunk: {sum(p.numel() for p in base.parameters())/1e6:.0f}M params (frozen)")

    model = LoRAModule(base, r=args.r, alpha=args.alpha, seed=args.seed).to(device)
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"LoRA trainable: {n_train/1e6:.2f}M params ({100.0*n_train/max(1, n_total):.2f}%)")

    train_sessions = load_sessions(Path(args.sessions_root))
    val_sessions = load_sessions(Path(args.val_root))
    print(f"train frames: {sum(s.length for s in train_sessions)}  "
          f"val frames: {sum(s.length for s in val_sessions)}")

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, eps=1e-4)
    scaler = GradScaler("cuda")

    if args.smoke:
        loss = run_epoch(model, train_sessions[:1], device, train=True, opt=opt,
                         scaler=scaler, batch_size=args.batch_size)
        print(f"SMOKE OK  train loss={loss:.5f}")
        return

    best_val = float("inf")
    history = []
    t0 = time.time()
    for epoch in range(args.epochs):
        t_ep = time.time()
        tr = run_epoch(model, train_sessions, device, train=True, opt=opt,
                       scaler=scaler, batch_size=args.batch_size)
        va = run_epoch(model, val_sessions, device, train=False, batch_size=args.batch_size)
        elapsed = time.time() - t_ep
        history.append({"train_loss": tr, "val_loss": va})
        tag = ""
        if va < best_val:
            best_val = va
            tag = "  *best*"
            # Pickle the classes under their importable module name (default
            # '__main__' would only resolve inside this script). When run as a
            # script, alias the __main__ module under the canonical name so
            # pickle finds the SAME class object (identity check).
            import sys as _sys
            LoRAModule.__module__ = "train_chestnut_lora"
            _LoraHook.__module__ = "train_chestnut_lora"
            _sys.modules.setdefault("train_chestnut_lora", _sys.modules["__main__"])
            torch.save({"model": model, "history": history, "epochs": epoch + 1,
                        "seed": args.seed, "lora_cfg": {"r": args.r, "alpha": args.alpha}},
                       args.out)
        print(f"epoch {epoch:03d}  train={tr:.5f}  val={va:.5f}  {elapsed:.0f}s{tag}", flush=True)
        eta = (time.time() - t0) / (epoch + 1) * (args.epochs - epoch - 1)
        print(f"  ETA remaining: {eta:.0f}s", flush=True)

    print(f"best val={best_val:.5f}  saved -> {args.out}")


if __name__ == "__main__":
    main()