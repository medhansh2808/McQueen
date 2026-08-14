#!/usr/bin/env python3
"""test_inference_rtx.py — offline tests for the real-inference glue (H2/L1).

Runs WITHOUT GStreamer: engine + I420 decode only. Requires torch
(use the mcqueen-laptop env):

    PYTHONPATH=$PWD/../.. /home/kartik/miniforge3/envs/mcqueen-laptop/bin/python \
        tools/realtime/test_inference_rtx.py

Covered:
  1. decode_i420_to_np: shape + plane values
  2. predict() returns None until history is full (no partial-window output)
  3. newest-frame-wins: prediction echoes the NEWEST pushed frame identity
  4. action contract: servo in [45,115], pwm in [-70,100]
  5. infer_ms positive; stats counters sane
  6. CUDA device path when torch.cuda.is_available()
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from inference_rtx import InferenceEngine, decode_i420_to_np  # noqa: E402

PASS = 0


def check(name, cond):
    global PASS
    assert cond, "FAIL: " + name
    PASS += 1
    print("PASS: " + name, flush=True)


def main():
    # ---- 1. I420 decode -----------------------------------------------------
    w, h = 640, 360
    y_plane = np.full((h, w), 10, dtype=np.uint8)
    u_plane = np.full((h // 2, w // 2), 20, dtype=np.uint8)
    v_plane = np.full((h // 2, w // 2), 30, dtype=np.uint8)
    raw = y_plane.tobytes() + u_plane.tobytes() + v_plane.tobytes()
    img = decode_i420_to_np(raw, w, h)
    check("i420 shape", img.shape == (h, w, 3) and img.dtype == np.uint8)
    check("i420 Y plane", img[..., 0].mean() == 10.0)
    check("i420 U plane upsampled", img[0, 0, 1] == 20)
    check("i420 V plane upsampled", img[-1, -1, 2] == 30)
    try:
        decode_i420_to_np(raw[:100], w, h)
        check("i420 short buffer raises", False)
    except ValueError:
        check("i420 short buffer raises", True)

    # ---- 2/3/4/5. engine (CPU first) ---------------------------------------
    eng = InferenceEngine(device="cpu")
    check("engine uses real policy class", type(eng.policy).__name__ == "TemporalDrivingPolicy")
    check("engine buffer empty", len(eng.buffer) == 0)

    rng = np.random.default_rng(7)
    for i in range(eng.history - 1):
        eng.push_frame(i, 1000 + i, rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8))
    check("predict None before full history", eng.predict() is None)

    newest_id = 42
    newest_cap = 123456789
    eng.push_frame(newest_id, newest_cap, rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8))
    pred = eng.predict()
    check("predict returns dict when full", pred is not None)
    check("newest-frame identity echoed", pred["frame_id"] == newest_id and pred["capture_mono_ns"] == newest_cap)
    check("servo within safety range", 45.0 <= pred["servo_angle_deg"] <= 115.0)
    check("pwm within safety caps", -70 <= pred["motor_pwm"] <= 100)
    check("infer_ms positive", pred["infer_ms"] > 0.0)

    for i in range(50, 60):
        eng.push_frame(i, 2000 + i, rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8))
    pred = eng.predict()
    check("newest-frame-wins after 10 more frames", pred["frame_id"] == 59 and pred["capture_mono_ns"] == 2059)

    st = eng.stats()
    check("stats n_predict matches", st["n_predict"] == eng.n_predict and st["n_predict"] > 0)
    check("stats skip_not_full >= 1", st["n_skip_not_full"] >= 1)

    # ---- 6. CUDA path -------------------------------------------------------
    if eng.torch.cuda.is_available():
        cuda_eng = InferenceEngine(device="cuda")
        for i in range(cuda_eng.history + 2):
            cuda_eng.push_frame(i, 3000 + i, rng.integers(0, 255, size=(360, 640, 3), dtype=np.uint8))
        cp = cuda_eng.predict()
        check("cuda predict works", cp is not None and cp["frame_id"] == cuda_eng.history + 1)
        check("cuda infer_ms positive", cp["infer_ms"] > 0.0)
        print("CUDA infer_avg={:.2f}ms".format(cuda_eng.stats()["infer_avg_ms"]), flush=True)
    else:
        print("NOTE: CUDA not available on this machine — GPU path skipped", flush=True)

    print("=" * 20, flush=True)
    print("RESULT: {}/{} PASS".format(PASS, PASS), flush=True)


if __name__ == "__main__":
    main()