#!/usr/bin/env python3
"""test_checkpoint_inference.py — offline tests for InferenceEngine checkpoint loading.

Runs WITHOUT GStreamer and WITHOUT any training: a tiny-backbone policy with
random weights is constructed and saved as a synthetic checkpoint in a temp
dir, then loaded back through InferenceEngine(checkpoint=...) on CPU.

    PYTHONPATH=$PWD/../.. /home/kartik/miniforge3/envs/mcqueen-laptop/bin/python \
        tools/realtime/test_checkpoint_inference.py [--checkpoint REAL.pt]

Optional --checkpoint REAL.pt: smoke-test a real checkpoint from
train_temporal_v2.py (e.g. after the lab training run).

Covered:
  1. synthetic checkpoint created with the train_temporal_v2.py dict format
  2. InferenceEngine(checkpoint=...) loads it; history/image_size from ckpt
  3. prediction pipeline works with loaded weights (denorm applied)
  4. denorm correctness: with stats mean/std known, denormed value = raw*std+mean
  5. action contract clamp still applies after denorm
"""

from __future__ import print_function

import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))

import numpy as np  # noqa: E402

from inference_rtx import InferenceEngine, _load_policy_classes  # noqa: E402

PASS = 0


def check(name, cond):
    global PASS
    assert cond, "FAIL: " + name
    PASS += 1
    print("PASS: " + name, flush=True)


def make_synthetic_checkpoint(path):
    """Tiny random-weight policy saved in train_temporal_v2.py checkpoint format."""
    import torch

    policy_cls, config_cls, backbone_cls = _load_policy_classes()
    config = config_cls(backbone="tiny", history=6)
    backbone = backbone_cls()
    policy = policy_cls(backbone, backbone.output_dim, config)
    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "backbone": "tiny",
            "config": config.__dict__,
            "action_names": ["servo_angle_deg", "motor_pwm"],
            "stats": {
                "servo_mean": 90.0, "servo_std": 5.0,
                "pwm_mean": 0.0, "pwm_std": 10.0,
            },
            "history": 6,
            "image_size": 224,
        },
        path,
    )
    return policy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=None)
    args = ap.parse_args()

    import torch

    tmpdir = tempfile.mkdtemp(prefix="mcqueen-ckpt-test-")
    real_path = args.checkpoint
    if real_path is None:
        real_path = os.path.join(tmpdir, "synthetic.pt")
        source_policy = make_synthetic_checkpoint(real_path)
        check("synthetic checkpoint written", os.path.isfile(real_path))

    eng = InferenceEngine(device="cpu", checkpoint=real_path)
    check("checkpoint engine loads", type(eng.policy).__name__ == "TemporalDrivingPolicy")
    check("history from checkpoint", eng.history == 6)
    check("input_size from checkpoint", eng.input_size == 224)
    check("denorm stats loaded", eng.denorm is not None)

    rng = np.random.default_rng(3)
    for i in range(eng.history):
        eng.push_frame(i, 5000 + i, rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8))
    pred = eng.predict()
    check("predict with loaded weights", pred is not None)
    check("newest frame echoed", pred["frame_id"] == eng.history - 1)

    raw_servo = None
    with torch.no_grad():
        win = torch.stack([e[2] for e in eng.buffer]).unsqueeze(0)
        wheels = torch.zeros((1, eng.history, 3))
        prev = torch.zeros((1, eng.history, 2))
        prev[:, :, 0] = 90.0
        raw_servo = float(eng.policy(win, wheels, prev)[0, 0].item())
    expected = raw_servo * eng.denorm[1] + eng.denorm[0]
    check(
        "denorm matches manual raw*std+mean",
        abs(pred["servo_angle_deg"] - expected) < 0.15,
    )
    check("servo clamp still enforced", 45.0 <= pred["servo_angle_deg"] <= 115.0)
    check("pwm clamp still enforced", -70 <= pred["motor_pwm"] <= 100)
    check("infer_ms positive", pred["infer_ms"] > 0.0)

    if real_path.endswith("synthetic.pt"):
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    print("=" * 20, flush=True)
    print("RESULT: {}/{} PASS".format(PASS, PASS), flush=True)


if __name__ == "__main__":
    main()
