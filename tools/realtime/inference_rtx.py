#!/usr/bin/env python3
"""inference_rtx.py — McQueen real temporal-policy inference (RTX side, L1).

Replaces the torch.rand dummy inference in gst_rtx_rtp_receiver.py with the
real TemporalDrivingPolicy architecture from mcqueen_ml.

Frame-association contract (benchmark-v2):
  - push_frame(meta, image_np) keeps a NEWEST-FRAME-WINS history of the last 6
    decoded frames, each tagged with its exact (frame_id, capture_mono_ns).
  - predict() runs the policy on the 6-frame window ending at the NEWEST frame
    and returns a CTRL payload echoing THAT frame's identity, so the Jetson
    computes capture -> returned-command latency on its own monotonic clock.

Honest boundaries:
  - Weights are RANDOM until the first training run: no driving model exists
    yet. This measures the real architecture's latency in the loop, NOT
    driving performance.
  - Wheel state is a zero placeholder until wheel encoders are wired
    (NullEncoderSource is the current Jetson reality).
  - The I420 -> 3-channel conversion below is a numpy stand-in for real RGB
    conversion (cv2 is not assumed on the RTX venv); fine for latency runs.
"""

from __future__ import print_function

import time

HISTORY = 6
INPUT_SIZE = 224


def _load_policy_classes():
    """Return (policy_cls, config_cls, backbone_cls) from the mcqueen_ml repo
    package.

    The receiver is deployed together with the mcqueen_ml package by
    run_rtp_wan_test.sh (PYTHONPATH=$RTX_DIR), so mcqueen_ml is normally
    importable. There is deliberately NO silent architectural fallback: a
    latency result must never be produced by a substitute model. If the
    package is missing, this raises and the receiver stays on dummy
    inference instead of misreporting.
    """
    import os
    import sys

    search = [
        os.environ.get("MCQUEEN_ML_PATH", ""),
        "/var/tmp/mcqueen-junior",
    ]
    for path in search:
        if path and path not in sys.path:
            sys.path.insert(0, path)
        try:
            from mcqueen_ml.training.temporal_policy_v2 import (
                TemporalDrivingPolicy,
                TinyVisualBackbone,
            )
            from mcqueen_ml.training.model_config_v2 import TemporalPolicyConfig

            return TemporalDrivingPolicy, TemporalPolicyConfig, TinyVisualBackbone
        except ImportError:
            continue
    raise RuntimeError(
        "mcqueen_ml is not importable. Deploy it (run_rtp_wan_test.sh) or set "
        "MCQUEEN_ML_PATH. Refusing to substitute another architecture."
    )


def decode_i420_to_np(raw, width, height):
    """I420 bytes -> HxWx3 uint8 ndarray (numpy-only, no cv2 assumed).

    Channel 0 = Y plane; channels 1/2 = U/V upsampled by replication. This is
    a latency-run stand-in for proper RGB conversion (documented above).
    """
    import numpy as np

    y_size = width * height
    u_size = (width // 2) * (height // 2)
    if len(raw) < y_size + 2 * u_size:
        raise ValueError(
            "I420 buffer too small: {} bytes, need {}".format(
                len(raw), y_size + 2 * u_size
            )
        )
    y = np.frombuffer(raw[:y_size], dtype=np.uint8).reshape(height, width)
    u = (
        np.frombuffer(raw[y_size : y_size + u_size], dtype=np.uint8)
        .reshape(height // 2, width // 2)
        .repeat(2, axis=0)
        .repeat(2, axis=1)
    )
    v = (
        np.frombuffer(raw[y_size + u_size : y_size + 2 * u_size], dtype=np.uint8)
        .reshape(height // 2, width // 2)
        .repeat(2, axis=0)
        .repeat(2, axis=1)
    )
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[..., 0] = y
    img[..., 1] = u
    img[..., 2] = v
    return img


class InferenceEngine(object):
    """Newest-frame-wins 6-frame temporal policy engine (RTX side).

    With ``checkpoint=None`` the engine builds the tiny-backbone policy with
    RANDOM weights (latency-only mode, unchanged behavior). With a checkpoint
    path it loads the trained ``model_state_dict`` (plus backbone/history/
    image_size/stats metadata written by train_temporal_v2.py), so weights
    and pre/post-processing match the training run.
    """

    def __init__(self, device=None, history=HISTORY, input_size=INPUT_SIZE, checkpoint=None):
        import os
        import torch

        self.torch = torch
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        policy_cls, config_cls, backbone_cls = _load_policy_classes()

        self.denorm = None  # (servo_mean, servo_std, pwm_mean, pwm_std) or None
        ckpt_info = "none (random tiny)"
        if checkpoint is not None:
            ckpt = torch.load(checkpoint, map_location=self.device)
            backbone_name = ckpt.get("backbone", "tiny")
            self.history = int(ckpt.get("history", history))
            self.input_size = int(ckpt.get("image_size", input_size))
            if backbone_name == "ppgeo_resnet34":
                from mcqueen_ml.training.backbones import PPGeoResNet34Backbone

                backbone = PPGeoResNet34Backbone(
                    weights_path=os.environ.get("MCQUEEN_PPGEO_CKPT")
                )
            else:
                backbone = backbone_cls()
            config = config_cls(backbone=backbone_name, history=self.history)
            self.policy = policy_cls(backbone, backbone.output_dim, config)
            self.policy.load_state_dict(ckpt["model_state_dict"])
            stats = ckpt.get("stats") or {}
            if all(k in stats for k in ("servo_mean", "servo_std", "pwm_mean", "pwm_std")):
                self.denorm = (
                    stats["servo_mean"], stats["servo_std"],
                    stats["pwm_mean"], stats["pwm_std"],
                )
            ckpt_info = "{} backbone={} history={} input={}x{}".format(
                checkpoint, backbone_name, self.history, self.input_size, self.input_size
            )
        else:
            self.history = int(history)
            self.input_size = int(input_size)
            config = config_cls(backbone="tiny", history=self.history)
            backbone = backbone_cls()
            self.policy = policy_cls(backbone, backbone.output_dim, config)

        self.policy.to(self.device)
        self.policy.eval()

        self.buffer = []  # [(frame_id, capture_mono_ns, tensor [3,H,W])] oldest->newest
        self.infer_ms = []
        self.n_predict = 0
        self.n_skip_not_full = 0

        print(
            "[RTX-INF] ENGINE device={} policy={} ckpt={}".format(
                self.device,
                policy_cls.__name__,
                ckpt_info,
            ),
            flush=True,
        )

    # ------------------------------------------------------------------

    def _to_tensor(self, image_np):
        """HxWx3 uint8 -> [3,input,input] float32 in [0,1] on self.device."""
        t = self.torch.from_numpy(image_np).float().div_(255.0)
        t = t.permute(2, 0, 1).unsqueeze(0)  # [1,3,H,W]
        t = self.torch.nn.functional.interpolate(
            t,
            size=(self.input_size, self.input_size),
            mode="bilinear",
            align_corners=False,
        )
        return t[0].to(self.device)

    def push_frame(self, frame_id, capture_mono_ns, image_np):
        """Newest-frame-wins: drop the oldest entry when the window is full."""
        if len(self.buffer) >= self.history:
            self.buffer.pop(0)
        self.buffer.append(
            (int(frame_id), int(capture_mono_ns), self._to_tensor(image_np))
        )

    def predict(self):
        """Run the policy on the window ending at the NEWEST frame.

        Returns None until `history` frames are available (newest-frame-wins
        means stale/partial windows never produce a prediction).
        Returns dict: frame_id, capture_mono_ns, servo_angle_deg, motor_pwm,
        infer_ms — echoing the identity of the newest frame.
        """
        if len(self.buffer) < self.history:
            self.n_skip_not_full += 1
            return None

        torch = self.torch
        win = self.buffer[-self.history :]
        frames = torch.stack([e[2] for e in win]).unsqueeze(0)  # [1,T,3,H,W]
        wheels = torch.zeros((1, self.history, 3), device=self.device)
        # Neutral previous-action padding (90 deg center, 0 PWM).
        prev = torch.zeros((1, self.history, 2), device=self.device)
        prev[:, :, 0] = 90.0

        with torch.no_grad():
            t0 = time.perf_counter()
            out = self.policy(frames, wheels, prev)  # [1, action_dim]
            if self.device == "cuda":
                torch.cuda.synchronize()
            infer_ms = (time.perf_counter() - t0) * 1000.0

        servo = float(out[0, 0].item())
        pwm = float(out[0, 1].item())
        if self.denorm is not None:
            servo = servo * self.denorm[1] + self.denorm[0]
            pwm = pwm * self.denorm[3] + self.denorm[2]
        # Mirror the Jetson-side safety contract ranges; the authoritative
        # safety gate remains on the Jetson (AutoSafetyGate).
        servo = max(45.0, min(115.0, servo))
        pwm = max(-70.0, min(100.0, pwm))

        newest = win[-1]
        self.infer_ms.append(infer_ms)
        self.n_predict += 1
        return {
            "frame_id": newest[0],
            "capture_mono_ns": newest[1],
            "servo_angle_deg": float(round(servo, 1)),
            "motor_pwm": int(round(pwm)),
            "infer_ms": float(round(infer_ms, 3)),
        }

    def stats(self):
        n = len(self.infer_ms)
        avg = sum(self.infer_ms) / n if n else 0.0
        return {
            "n_predict": self.n_predict,
            "n_skip_not_full": self.n_skip_not_full,
            "infer_avg_ms": avg,
        }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="standalone latency smoke of the engine")
    p.add_argument("--device", default=None)
    p.add_argument("--frames", type=int, default=20)
    p.add_argument("--checkpoint", default=None, help="trained checkpoint .pt from train_temporal_v2.py")
    args = p.parse_args()

    import numpy as np

    eng = InferenceEngine(device=args.device, checkpoint=args.checkpoint)
    rng = np.random.default_rng(0)
    for i in range(args.frames):
        img = rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8)
        eng.push_frame(i, 1000 + i, img)
        pred = eng.predict()
        if pred is not None and (i % 5 == 0 or i == args.frames - 1):
            print(
                "[RTX-INF] frame={} servo={} pwm={} infer={}ms".format(
                    pred["frame_id"], pred["servo_angle_deg"],
                    pred["motor_pwm"], pred["infer_ms"],
                ),
                flush=True,
            )
    s = eng.stats()
    print(
        "[RTX-INF] predict={} skip_not_full={} infer_avg={:.2f}ms".format(
            s["n_predict"], s["n_skip_not_full"], s["infer_avg_ms"]
        ),
        flush=True,
    )