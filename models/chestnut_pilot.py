"""chestnut_pilot.py — drive the DonkeyCar simulator with comma's chestnut big model.

Uses the converted chestnut module (big_driving_supercombo.onnx -> onnx2pytorch,
chestnut_onnx2torch_sd.pt) with openpilot's EXACT action mapping (modeld.py master):
    desired_curvature = action[0,0] / max(1.0, v_ego)^2
    desired_accel     = action[0,1]
steer = atan(CAR_LENGTH * curvature) / MAX_STEER_ANGLE_RAD (action_adapter convention).
Features roll through a 24x512 buffer; desire_pulse/traffic_convention/action_t
are fed per openpilot semantics (traffic_convention[is_rhd]=1 -> [0,1] India).

Mode: metrics (headless) or visual. Multiple instances can run in parallel on
different ports to use the RTX resources efficiently.

Usage (RTX, mcqueen-openpilot env, PYTHONPATH=~/mcqueen/models):
    python chestnut_pilot.py --mode metrics --track circuit_launch --runs 2 \
        --port 9091 --max-steps 1200 --warmup 25
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time

import cv2
import numpy as np
import torch

# Bind LoRAModule/_LoraHook into this module's namespace so pickle can resolve
# them: checkpoints saved by train_chestnut_lora.py name these classes under
# '__main__' (the trainer's script module), and when this file runs as a script
# IT is '__main__'.
from train_chestnut_lora import LoRAModule, _LoraHook  # noqa: F401

HIDDEN_SLICE = slice(2066, 2578)
ACTION_SLICE = slice(2062, 2066)
POSE_SLICE = slice(887, 899)
PLAN_SLICE = slice(917, 1907)
CAR_LENGTH_M = 0.35
MAX_STEER_ANGLE_RAD = 0.78
MAX_SPEED_MPS = 3.0

TRACKS = {
    "circuit_launch": "donkey-circuit-launch-track-v0",
    "generated": "donkey-generated-track-v0",
    "warehouse": "donkey-warehouse-track-v0",
}


def _yuv(rgb: np.ndarray) -> np.ndarray:
    """Mirror of action_adapter.rgb_to_supercombo_yuv — packed (6,128,256)."""
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


class ChestnutPilot:
    def __init__(self, module_path: str, device: torch.device, max_throttle: float = 1.0,
                 steer_gain: float = 1.0, warmup: int = 25, steer_trim: float = 0.0,
                 action_t: tuple[float, float] = (0.05, 0.05), curv_floor: float = 2.5,
                 max_speed: float = 12.0, throttle_kp: float = 0.5, throttle_ff: float = 0.35,
                 crop_bottom: float = 1.0, action_scale: float = 1.0):
        t0 = time.time()
        state = torch.load(module_path, map_location="cpu", weights_only=False)
        self.model = state["model"].to(device).half().eval()
        for p in self.model.parameters():
            p.requires_grad = False
        print(f"chestnut loaded in {time.time()-t0:.1f}s, params={sum(p.numel() for p in self.model.parameters())/1e6:.0f}M")

        self.device = device
        self.max_throttle = max_throttle
        self.steer_gain = steer_gain
        self.warmup = warmup
        self.steer_trim = steer_trim
        self.curv_floor = curv_floor
        self.max_speed = max_speed
        self.throttle_kp = throttle_kp
        self.throttle_ff = throttle_ff
        self.crop_bottom = crop_bottom
        self.action_scale = action_scale
        self.v_target = 0.0
        self.frames: list[np.ndarray] = []
        self.buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device=device)
        self.desire_pulse = torch.zeros(1, 25, 8, dtype=torch.float16, device=device)
        self.traffic_convention = torch.zeros(1, 2, dtype=torch.float16, device=device)
        self.traffic_convention[0, 1] = 1.0  # is_rhd=1 (India)
        self.action_t = torch.tensor([[action_t[0], action_t[1]]], dtype=torch.float16, device=device)
        self.pred_stats = {"min": [1.0, 1.0], "max": [-1.0, -1.0], "count": 0}
        self._step_count = 0

    def act(self, rgb_bgr: np.ndarray, v_ego: float = 0.0) -> tuple[float, float]:
        self._step_count += 1
        if self.pred_stats["count"] == 0:
            print(f"obs: shape={rgb_bgr.shape} dtype={rgb_bgr.dtype} "
                  f"mean_ch0={rgb_bgr[..., 0].mean():.1f} mean_ch2={rgb_bgr[..., 2].mean():.1f}",
                  flush=True)
        rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
        if self.crop_bottom < 1.0:
            h = rgb.shape[0]
            rgb = rgb[int(h * (1.0 - self.crop_bottom)):, :, :]
        rgb = cv2.resize(rgb, (512, 256), interpolation=cv2.INTER_AREA)
        packed = _yuv(rgb).astype(np.uint8)
        self.frames.append(packed)
        if len(self.frames) < 2:
            return 0.0, 0.0
        self.frames = self.frames[-2:]
        img = np.concatenate([self.frames[0], self.frames[1]], axis=0)[None]

        with torch.no_grad(), torch.amp.autocast("cuda"):
            img_t = torch.from_numpy(img).to(self.device)
            out = self.model(img_t, img_t, self.desire_pulse, self.traffic_convention,
                             self.action_t, self.buffer)
            if isinstance(out, (tuple, list)):
                out = out[0]
            out = out.view(out.shape[0], -1).float()
            if out.shape[1] != 2578:
                raise RuntimeError(f"expected flattened 2578, got {out.shape[1]}")
            action = out[:, ACTION_SLICE]
            hidden = out[:, HIDDEN_SLICE]
            pose = out[:, POSE_SLICE]
            plan = out[:, PLAN_SLICE].view(1, 33, 30)[:, :, :15]

            a0 = float(torch.clamp(action[0, 0], -30.0, 30.0))
            desired_curvature = a0 * self.action_scale / (max(self.curv_floor, v_ego) ** 2)
            desired_accel = float(torch.clamp(action[0, 1], -4.0, 4.0))
            if self._step_count % 10 == 0 and self._step_count > self.warmup:
                p0, p1 = plan[0, 0], plan[0, 1]
                print(f"A action={[round(float(x), 3) for x in action[0]]} pose_v={float(pose[0, 0]):.1f} "
                      f"plan0={[round(float(x), 3) for x in p0]} plan1={[round(float(x), 3) for x in p1]} "
                      f"v_ego={v_ego:.2f} curv={desired_curvature:.4f} accel={desired_accel:.3f}", flush=True)
            steer = math.atan(CAR_LENGTH_M * desired_curvature) / MAX_STEER_ANGLE_RAD
            self.v_target = float(np.clip(v_ego + desired_accel * 0.05, 0.0, self.max_speed))
            throttle = float(np.clip(self.throttle_ff + desired_accel * 0.2
                                     + self.throttle_kp * (self.v_target - v_ego), 0.0, 1.0))

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


def run_metrics(env, pilot: ChestnutPilot, max_steps: int, trace: bool = False) -> dict:
    obs, _ = env.reset()
    done = False
    steps, cte_sum, cte_max, speed_max, reward_sum = 0, 0.0, 0.0, 0.0, 0.0
    while not done and steps < max_steps:
        info_speed = getattr(env, "current_speed", 0.0)
        steer, throttle = pilot.act(obs, v_ego=info_speed)
        obs, reward, terminated, truncated, info = env.step([steer, throttle])
        done = terminated or truncated
        cte = abs(info.get("cte", 0.0))
        cte_sum += cte
        cte_max = max(cte_max, cte)
        speed_max = max(speed_max, info.get("speed", 0.0))
        reward_sum += float(reward)
        steps += 1
        if trace and steps % 10 == 0:
            print(f"T t={steps} v={info.get('speed', 0.0):.2f} steer={steer:.3f} "
                  f"throttle={throttle:.3f} cte={cte:.3f}", flush=True)
    return {
        "steps": steps, "done": bool(done), "max_abs_cte": cte_max,
        "mean_abs_cte": cte_sum / max(1, steps), "max_speed": speed_max,
        "total_reward": reward_sum,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", default="chestnut_onnx2torch_sd.pt")
    ap.add_argument("--mode", choices=["metrics", "visual"], default="metrics")
    ap.add_argument("--track", choices=list(TRACKS), default="circuit_launch")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=1200)
    ap.add_argument("--max-throttle", type=float, default=1.0)
    ap.add_argument("--steer-gain", type=float, default=1.0)
    ap.add_argument("--warmup", type=int, default=25)
    ap.add_argument("--steer-trim", type=float, default=0.0)
    ap.add_argument("--action-t", type=float, nargs=2, default=[0.05, 0.05])
    ap.add_argument("--curv-floor", type=float, default=2.5,
                    help="speed floor (m/s) for the curvature = action[0,0]/v^2 mapping")
    ap.add_argument("--max-speed", type=float, default=12.0,
                    help="cap target speed (m/s) from accel integration")
    ap.add_argument("--throttle-kp", type=float, default=0.5)
    ap.add_argument("--throttle-ff", type=float, default=0.35)
    ap.add_argument("--trace", action="store_true", help="log v/steer/throttle/cte every 10 steps")
    ap.add_argument("--crop-bottom", type=float, default=1.0,
                    help="keep bottom fraction of the frame (road-dominant warp A/B); 1.0 = full frame")
    ap.add_argument("--action-scale", type=float, default=1.0,
                    help="multiplier on action[0,0] before the /v^2 mapping (V_ASSUMED^2 for "
                         "raw-curvature-trained checkpoints; e.g. 9.0 for V_ASSUMED=3.0)")
    ap.add_argument("--exe",
                    default=os.path.expanduser("~/donkey_sim/DonkeySimLinux/donkey_sim.x86_64"))
    ap.add_argument("--port", type=int, default=9091)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}  track={TRACKS[args.track]}  port={args.port}  action_t={args.action_t}"
          f"  curv_floor={args.curv_floor}  action_scale={args.action_scale}  max_speed={args.max_speed}")

    pilot = ChestnutPilot(args.module, device, max_throttle=args.max_throttle,
                          steer_gain=args.steer_gain, warmup=args.warmup,
                          steer_trim=args.steer_trim, action_t=tuple(args.action_t),
                          curv_floor=args.curv_floor, max_speed=args.max_speed,
                          throttle_kp=args.throttle_kp, throttle_ff=args.throttle_ff,
                          crop_bottom=args.crop_bottom, action_scale=args.action_scale)

    import gym_donkeycar
    from gym_donkeycar import CircuitLaunchEnv, GeneratedTrackEnv
    try:
        from gym_donkeycar import WarehouseEnv
    except ImportError:
        WarehouseEnv = None
    env_class = {"circuit_launch": CircuitLaunchEnv, "generated": GeneratedTrackEnv,
                 "warehouse": WarehouseEnv}[args.track]
    env = env_class(conf={
        "exe_path": args.exe, "port": args.port, "headless": args.mode == "metrics",
        "log_level": "CRITICAL", "start_delay": 5.0,
    })
    try:
        if args.mode == "metrics":
            for r in range(args.runs):
                m = run_metrics(env, pilot, args.max_steps, trace=args.trace)
                print(f"run {r}: steps={m['steps']} done={m['done']} "
                      f"max_cte={m['max_abs_cte']:.3f} mean_cte={m['mean_abs_cte']:.3f} "
                      f"max_speed={m['max_speed']:.2f} reward={m['total_reward']:.1f}", flush=True)
        else:
            obs, _ = env.reset()
            for _ in range(args.max_steps):
                steer, throttle = pilot.act(obs)
                obs, _, terminated, truncated, _ = env.step([steer, throttle])
                cv2.imshow("mcqueen-chestnut", obs)
                if cv2.waitKey(1) == 27 or terminated or truncated:
                    break
            cv2.destroyAllWindows()
    finally:
        env.close()
        torch.cuda.empty_cache()
        print(f"pred range: steer [{pilot.pred_stats['min'][0]:.3f},{pilot.pred_stats['max'][0]:.3f}] "
              f"throttle [{pilot.pred_stats['min'][1]:.3f},{pilot.pred_stats['max'][1]:.3f}]")


if __name__ == "__main__":
    main()