"""sim_pilot.py — drive the DonkeyCar simulator with McQueen predictions.

Two prediction sources:
    --model zero-shot : comma master plan -> action_to_command_torch (v_ego=0)
    --model head      : trained MLP head on hidden_state (donkey_head_best.pt)

Modes:
    --mode metrics   : gym_donkeycar programmatic run, prints per-run metrics
                       (steps, max_abs_cte, mean_abs_cte, max_speed, done, total_reward)
    --mode visual    : windowed sim run on the RTX display, keyboard ESC to exit

Frames are packed YUV (6,128,256) and consumed by the same FrozenActionModel
pipeline as training (frames arrive in pairs to preserve temporal state).

Usage (RTX, mcqueen-openpilot env, run from the dir holding action_adapter.py):
    PYTHONPATH=~/mcqueen/models python tools/donkey/sim_pilot.py \
        --onnx ~/mcqueen/models/driving_supercombo_master.onnx \
        --ckpt ~/mcqueen/models/donkey_head_best.pt \
        --model head --mode metrics --track circuit_launch --runs 3
"""

from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np
import torch

from action_adapter import FrozenActionModel, action_to_command_torch

TRACKS = {
    "circuit_launch": "donkey-circuit-launch-track-v0",
    "generated": "donkey-generated-track-v0",
}
class McQueenPilot:
    """Drives the gym env with supercombo predictions; keeps its own history."""

    def __init__(self, model, head, stats, device, use_head: bool, max_throttle: float = 1.0,
                 steer_gain: float = 1.0, warmup: int = 0, steer_trim: float = 0.0):
        self.model = model
        self.head = head
        self.stats = stats
        self.device = device
        self.use_head = use_head
        self.max_throttle = max_throttle
        self.steer_gain = steer_gain
        self.warmup = warmup
        self.steer_trim = steer_trim
        self.frames = []  # last 2 packed YUV arrays
        self.buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device=device)
        self.zeros_desire = torch.zeros(1, 25, 8, dtype=torch.float16, device=device)
        self.zeros_traffic = torch.zeros(1, 2, dtype=torch.float16, device=device)
        self.zeros_action_t = torch.zeros(1, 2, dtype=torch.float16, device=device)
        self.pred_stats = {"min": [1.0, 1.0], "max": [-1.0, -1.0], "count": 0}
        self._step_count = 0

    def act(self, rgb_bgr: np.ndarray) -> tuple[float, float]:
        self._step_count += 1
        if self.pred_stats["count"] == 0:
            print(f"obs: shape={rgb_bgr.shape} dtype={rgb_bgr.dtype} "
                  f"mean_ch0={rgb_bgr[..., 0].mean():.1f} mean_ch2={rgb_bgr[..., 2].mean():.1f}",
                  flush=True)
        rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (512, 256), interpolation=cv2.INTER_AREA)
        packed = _yuv(rgb).astype(np.uint8)
        self.frames.append(packed)
        if len(self.frames) < 2:
            return 0.0, 0.0
        self.frames = self.frames[-2:]
        img = np.concatenate([self.frames[0], self.frames[1]], axis=0)[None]

        with torch.no_grad(), torch.amp.autocast("cuda"):
            img_t = torch.from_numpy(img).to(self.device)
            action, hidden, _ = self.model(
                img=img_t, big_img=img_t,
                desire_pulse=self.zeros_desire, traffic_convention=self.zeros_traffic,
                action_t=self.zeros_action_t, features_buffer=self.buffer,
            )
            if self.use_head:
                mean = torch.tensor(self.stats["mean"], device=self.device)
                std = torch.tensor(self.stats["std"], device=self.device)
                pred_norm = self.head(hidden).float()
                steer, throttle = (pred_norm[0] * std + mean).tolist()
            else:
                steer, throttle = action_to_command_torch(action, v_ego=0.0)
                steer = float(steer.reshape(-1)[0].item())
                throttle = float(throttle.reshape(-1)[0].item())
            self.buffer = torch.cat(
                [self.buffer[:, 1:, :], hidden.detach().unsqueeze(1).to(self.buffer.dtype)], dim=1)

        steer = float(np.clip(steer * self.steer_gain + self.steer_trim, -1.0, 1.0))
        throttle = float(np.clip(throttle, -self.max_throttle, self.max_throttle))
        if self._step_count <= self.warmup:
            throttle = 0.03
        for k, v in enumerate((steer, throttle)):
            self.pred_stats["min"][k] = min(self.pred_stats["min"][k], v)
            self.pred_stats["max"][k] = max(self.pred_stats["max"][k], v)
            self.pred_stats["count"] += 1
        return steer, throttle


def _yuv(rgb: np.ndarray) -> np.ndarray:
    """Exact mirror of action_adapter.rgb_to_supercombo_yuv — packed (6,128,256)."""
    yuv = cv2.cvtColor(rgb, cv2.COLOR_RGB2YUV_I420)
    H, W = 256, 512
    y = yuv[:H, :]
    u = yuv[H:H + H // 4, :].reshape(H // 2, W // 2)
    v = yuv[H + H // 4:H + H // 2, :].reshape(H // 2, W // 2)
    y0 = y[0::2, 0::2]
    y1 = y[0::2, 1::2]
    y2 = y[1::2, 0::2]
    y3 = y[1::2, 1::2]
    return np.stack([y0, y1, y2, y3, u, v], axis=0).astype(np.uint8)


def load_checkpoint(path: str):
    from train_frozen_action import ActionHead, HeadConfig
    ckpt = torch.load(path, map_location="cpu")
    head = ActionHead(HeadConfig(**ckpt["head_config"]))
    head.load_state_dict(ckpt["model_state_dict"])
    return head, ckpt["stats"]


def run_metrics(env, pilot: McQueenPilot, max_steps: int) -> dict:
    obs, _ = env.reset()
    done = False
    steps, cte_sum, cte_max, speed_max, reward_sum = 0, 0.0, 0.0, 0.0, 0.0
    while not done and steps < max_steps:
        steer, throttle = pilot.act(obs)
        obs, reward, terminated, truncated, info = env.step([steer, throttle])
        done = terminated or truncated
        cte = abs(info.get("cte", 0.0))
        cte_sum += cte
        cte_max = max(cte_max, cte)
        speed_max = max(speed_max, info.get("speed", 0.0))
        reward_sum += float(reward)
        steps += 1
    return {
        "steps": steps, "done": bool(done), "max_abs_cte": cte_max,
        "mean_abs_cte": cte_sum / max(1, steps), "max_speed": speed_max,
        "total_reward": reward_sum,
    }


def run_visual(env, pilot: McQueenPilot, max_steps: int) -> None:
    obs, _ = env.reset()
    for _ in range(max_steps):
        steer, throttle = pilot.act(obs)
        obs, _, terminated, truncated, _ = env.step([steer, throttle])
        cv2.imshow("mcqueen-sim", obs)
        if cv2.waitKey(1) == 27 or terminated or truncated:
            break
    cv2.destroyAllWindows()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--ckpt", required=False, help="needed for --model head")
    ap.add_argument("--model", choices=["zero-shot", "head"], required=True)
    ap.add_argument("--mode", choices=["metrics", "visual"], default="metrics")
    ap.add_argument("--track", choices=list(TRACKS), default="circuit_launch")
    ap.add_argument("--runs", type=int, default=1, help="metrics runs (visual: ignored)")
    ap.add_argument("--max-steps", type=int, default=600)
    ap.add_argument("--max-throttle", type=float, default=1.0,
                    help="cap the throttle magnitude (speed limiter)")
    ap.add_argument("--steer-gain", type=float, default=1.0,
                    help="multiply model steering before sending to the sim "
                         "(sim-side tuning knob for low-speed yaw authority)")
    ap.add_argument("--warmup", type=int, default=0,
                    help="first N steps use throttle=0.03 with model steering "
                         "(smooth deterministic start while the temporal buffer fills)")
    ap.add_argument("--steer-trim", type=float, default=0.0,
                    help="constant steering offset (real-car alignment trim); "
                         "negative = left")
    ap.add_argument("--exe", default="/home/junior/donkey_sim/DonkeySimLinux/donkey_sim.x86_64",
                    help="simulator binary (required by gym_donkeycar on this box)")
    ap.add_argument("--port", type=int, default=9091, help="gym env port")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}  model={args.model}  mode={args.mode}  track={TRACKS[args.track]}")

    head, stats = None, None
    if args.model == "head":
        if not args.ckpt:
            sys.exit("--ckpt required for --model head")
        head, stats = load_checkpoint(args.ckpt)
        head.to(device).eval()
        print(f"head loaded from {args.ckpt}")

    model = FrozenActionModel(args.onnx).to(device).eval()

    import gym_donkeycar
    from gym_donkeycar import CircuitLaunchEnv, GeneratedTrackEnv
    env_class = {"circuit_launch": CircuitLaunchEnv, "generated": GeneratedTrackEnv}[args.track]
    env = env_class(
        conf={
            "exe_path": args.exe,
            "port": args.port,
            "headless": args.mode == "metrics",
            "log_level": "CRITICAL",
            "start_delay": 5.0,
        },
    )

    pilot = McQueenPilot(model, head, stats, device, use_head=args.model == "head",
                         max_throttle=args.max_throttle, steer_gain=args.steer_gain,
                         warmup=args.warmup, steer_trim=args.steer_trim)
    try:
        if args.mode == "metrics":
            for r in range(args.runs):
                m = run_metrics(env, pilot, args.max_steps)
                print(f"run {r}: steps={m['steps']} done={m['done']} "
                      f"max_cte={m['max_abs_cte']:.3f} mean_cte={m['mean_abs_cte']:.3f} "
                      f"max_speed={m['max_speed']:.2f} reward={m['total_reward']:.1f}",
                      flush=True)
        else:
            run_visual(env, pilot, args.max_steps)
    finally:
        env.close()
        torch.cuda.empty_cache()
        print(f"pred range: steer [{pilot.pred_stats['min'][0]:.3f},{pilot.pred_stats['max'][0]:.3f}] "
              f"throttle [{pilot.pred_stats['min'][1]:.3f},{pilot.pred_stats['max'][1]:.3f}]")


if __name__ == "__main__":
    main()