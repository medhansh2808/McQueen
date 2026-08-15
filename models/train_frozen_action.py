import argparse
import glob
import os

import cv2
import numpy as np
import pandas as pd
import torch

from action_adapter import FrozenActionModel, action_to_command_torch, rgb_to_supercombo_yuv

FRAME_GLOB = "rgb_raw_upright/frame_*.png"   

MAX_STEER_ANGLE_RAD = 0.78
MAX_SPEED_MPS = 3.0


def dead_reckon_positions(steer_labels: list, throttle_labels: list, dt: float = 0.1) -> np.ndarray:
    """Crude bicycle-model integration of your OWN logged controls, for
    eyeballing against the frozen model's plan output in logs — not a
    real label, not used in any loss. See train/labels.py for the more
    complete version used elsewhere in this project."""
    x, y, theta = 0.0, 0.0, 0.0
    pts = []
    for steer, throttle in zip(steer_labels, throttle_labels):
        v = throttle * MAX_SPEED_MPS
        delta = steer * MAX_STEER_ANGLE_RAD
        x += v * np.cos(theta) * dt
        y += v * np.sin(theta) * dt
        theta += (v / CAR_LENGTH_M) * np.tan(delta) * dt
        pts.append((x, y))
    return np.array(pts, dtype=np.float32)


def load_sessions(sessions_root: str):

    for session_dir in sorted(glob.glob(os.path.join(sessions_root, "session_*"))):
        controls_path = os.path.join(session_dir, "controls.csv")
        frames = sorted(glob.glob(os.path.join(session_dir, FRAME_GLOB)))
        if not os.path.exists(controls_path) or len(frames) < 2:
            continue
        df = pd.read_csv(controls_path)
        n = min(len(df), len(frames))
        session_examples = []
        for i in range(1, n):
            f0 = cv2.resize(cv2.cvtColor(cv2.imread(frames[i - 1]), cv2.COLOR_BGR2RGB), (512, 256))
            f1 = cv2.resize(cv2.cvtColor(cv2.imread(frames[i]), cv2.COLOR_BGR2RGB), (512, 256))
            session_examples.append((f0, f1, float(df["steering"].iloc[i]), float(df["throttle"].iloc[i])))
        if session_examples:
            yield session_examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True, help="the EXTRACTED SUBGRAPH, e.g. mcqueen_action_subgraph.onnx")
    ap.add_argument("--sessions_root", required=True)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--out", default="mcqueen_action_head.pt")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = FrozenActionModel(args.onnx).to(device)

    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"{len(trainable)} trainable tensors, {sum(p.numel() for p in trainable)} params")
  
    opt = torch.optim.AdamW(trainable, lr=args.lr, eps=1e-4)
    mse = torch.nn.MSELoss()

    sessions = list(load_sessions(args.sessions_root))
    total_examples = sum(len(s) for s in sessions)
    print(f"loaded {len(sessions)} sessions, {total_examples} total examples")
    if total_examples == 0:
        raise RuntimeError("no examples found — check --sessions_root and FRAME_GLOB match your real logger layout")

    zeros_desire = torch.zeros(1, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(1, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(1, 2, dtype=torch.float16, device=device)

    for epoch in range(args.epochs):
        total_loss, total_n = 0.0, 0

        for session in sessions:
            features_buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device=device)  # reset per session
            session_steers, session_throttles = [], []

            for step_i, (f0, f1, steer_label, throttle_label) in enumerate(session):
                img0 = torch.from_numpy(rgb_to_supercombo_yuv(f0)).unsqueeze(0).to(device)   # uint8
                img1 = torch.from_numpy(rgb_to_supercombo_yuv(f1)).unsqueeze(0).to(device)   # uint8
                stacked = torch.cat([img0, img1], dim=1)  # (1, 12, 128, 256) uint8

                action, hidden_state, plan_positions = model(
                    img=stacked, big_img=stacked,   # no separate wide cam — reusing narrow, imperfect but simplest start
                    desire_pulse=zeros_desire, traffic_convention=zeros_traffic,
                    action_t=zeros_action_t, features_buffer=features_buffer,
                )

                steer_pred, throttle_pred = action_to_command_torch(action, v_ego=0.0)  # v_ego blocker — see module docstring
                loss = (
                    mse(steer_pred, torch.tensor(steer_label, dtype=steer_pred.dtype, device=device))
                    + mse(throttle_pred, torch.tensor(throttle_label, dtype=throttle_pred.dtype, device=device))
                )

                opt.zero_grad()
                loss.backward()
                opt.step()
                total_loss += loss.item()
                total_n += 1

                session_steers.append(steer_label)
                session_throttles.append(throttle_label)

                if step_i > 0 and step_i % 50 == 0:
                    # Rough plausibility check, not a metric that feeds training:
                    # does the frozen model's predicted path shape resemble where
                    # your own controls would have dead-reckoned the car to?
                    dr = dead_reckon_positions(session_steers[-20:], session_throttles[-20:])
                    model_plan_xy = plan_positions[0, :len(dr), :2].detach().cpu().numpy()
                    diff = np.abs(dr - model_plan_xy).mean()
                    print(f"  [diagnostic] step {step_i}: mean |dead-reckon - frozen plan| = {diff:.3f} "
                          f"(not used in loss, just a sanity check)")

                features_buffer = torch.cat(
                    [features_buffer[:, 1:, :], hidden_state.detach().unsqueeze(1)], dim=1
                )

        print(f"epoch {epoch:03d}  loss={total_loss / max(1, total_n):.5f}")

    torch.save(model.state_dict(), args.out)
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
