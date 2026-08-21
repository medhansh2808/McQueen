import argparse

import numpy as np
import torch

from action_adapter import FrozenActionModel, action_to_command_torch, rgb_to_supercombo_yuv


def make_frame(rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, 256, size=(256, 512, 3), dtype=np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True, help="comma driving_supercombo.onnx (2026 master export)")
    ap.add_argument("--real_frame", default=None, help="optional real RGB png (256,512,3) from the Jetson")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}")

    model = FrozenActionModel(args.onnx).to(device)

    trainable = [p for p in model.parameters() if p.requires_grad]
    n_params = sum(p.numel() for p in trainable)
    print(f"trainable tensors: {len(trainable)} | params: {n_params} (expect 0 — fully frozen, plan-derived action)")

    rng = np.random.default_rng(0)
    f0 = make_frame(rng)
    f1 = make_frame(rng)
    if args.real_frame:
        import cv2
        f0 = cv2.cvtColor(cv2.resize(cv2.imread(args.real_frame), (512, 256)), cv2.COLOR_BGR2RGB)
        print(f"using real frame: {args.real_frame}")

    img0 = torch.from_numpy(rgb_to_supercombo_yuv(f0)).unsqueeze(0).to(device)
    img1 = torch.from_numpy(rgb_to_supercombo_yuv(f1)).unsqueeze(0).to(device)
    stacked = torch.cat([img0, img1], dim=1)

    zeros_desire = torch.zeros(1, 25, 8, dtype=torch.float16, device=device)
    zeros_traffic = torch.zeros(1, 2, dtype=torch.float16, device=device)
    zeros_action_t = torch.zeros(1, 2, dtype=torch.float16, device=device)
    features_buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device=device)

    with torch.no_grad():
        action, hidden, plan = model(
            img=stacked, big_img=stacked,
            desire_pulse=zeros_desire, traffic_convention=zeros_traffic,
            action_t=zeros_action_t, features_buffer=features_buffer,
        )
        print("action:", tuple(action.shape), action.dtype)
        print("hidden:", tuple(hidden.shape), hidden.dtype)
        print("plan  :", tuple(plan.shape), plan.dtype)

        steer, throttle = action_to_command_torch(action, v_ego=0.0)
        print(f"steer={steer.item():+.4f} throttle={throttle.item():+.4f} (both in [-1,1])")

        features_buffer = torch.cat([features_buffer[:, 1:, :], hidden.unsqueeze(1)], dim=1)
        action2, _, _ = model(
            img=stacked, big_img=stacked,
            desire_pulse=zeros_desire, traffic_convention=zeros_traffic,
            action_t=zeros_action_t, features_buffer=features_buffer,
        )
        print("temporal step 2 action:", tuple(action2.shape), "OK")

    print("SMOKE PASSED")


if __name__ == "__main__":
    main()