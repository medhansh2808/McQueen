"""bench_chestnut.py — load + warmup + per-frame latency/VRAM for chestnut.

Backend a) torch-converted model (onnx2pytorch/onnx2torch .pt) or b) onnxruntime
session. Reports: load time, warmup time, per-iteration ms (median of N), peak
VRAM. Must be run on the RTX with the mcqueen-openpilot env.

Usage:
    python bench_chestnut.py --torch chestnut_model.pt --iters 50
    python bench_chestnut.py --ort big_driving_supercombo.onnx --iters 50
"""

import argparse
import random
import time

import numpy as np
import torch


def bench_torch(path: str, iters: int):
    t0 = time.time()
    state = torch.load(path, map_location="cpu", weights_only=False)
    model = state["model"] if isinstance(state, dict) and "model" in state else None
    if model is None:
        raise SystemExit("--torch path must contain a 'model' key (torch.save(module))")
    print(f"torch load: {time.time()-t0:.1f}s")

    model = model.to("cuda").half().eval()
    torch.cuda.reset_peak_memory_stats()

    img = torch.zeros(1, 12, 128, 256, dtype=torch.float16, device="cuda")
    big_img = torch.zeros(1, 12, 128, 256, dtype=torch.float16, device="cuda")
    desire_pulse = torch.zeros(1, 25, 8, dtype=torch.float16, device="cuda")
    traffic_convention = torch.zeros(1, 2, dtype=torch.float16, device="cuda")
    action_t = torch.zeros(1, 2, dtype=torch.float16, device="cuda")
    features_buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device="cuda")
    inputs = (img, big_img, desire_pulse, traffic_convention, action_t, features_buffer)
    with torch.no_grad():
        t0 = time.time()
        for _ in range(5):
            model(*inputs)
        torch.cuda.synchronize()
        warm = (time.time() - t0) / 5 * 1000
        print(f"warmup: {warm:.1f} ms/iter")

        times = []
        for _ in range(iters):
            t0 = time.time()
            model(*inputs)
            torch.cuda.synchronize()
            times.append((time.time() - t0) * 1000)
    times.sort()
    print(f"per-iter: median={times[len(times)//2]:.1f} ms p90={times[int(len(times)*0.9)]:.1f} ms")
    print(f"peak VRAM: {torch.cuda.max_memory_allocated()/1e6:.0f} MiB")


def bench_ort(path: str, iters: int):
    import onnxruntime as ort

    sess_options = ort.SessionOptions()
    sess = ort.InferenceSession(path, sess_options, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    print(f"ort providers: {sess.get_providers()}")
    inputs = {i.name: np.zeros(i.shape, dtype=np.float16 if i.type.startswith("tensor(float16)") else np.float32)
              for i in sess.get_inputs() if all(d > 0 for d in i.shape)}
    for i in sess.get_inputs():
        if not all(d > 0 for d in i.shape):
            print(f"  (dynamic input {i.name} skipped; shape {i.shape})")
    for _ in range(5):
        sess.run(None, inputs)
    times = []
    for _ in range(iters):
        t0 = time.time()
        sess.run(None, inputs)
        times.append((time.time() - t0) * 1000)
    times.sort()
    print(f"per-iter: median={times[len(times)//2]:.1f} ms p90={times[int(len(times)*0.9)]:.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--torch", default=None)
    ap.add_argument("--ort", default=None)
    ap.add_argument("--iters", type=int, default=50)
    args = ap.parse_args()
    if args.torch:
        bench_torch(args.torch, args.iters)
    elif args.ort:
        bench_ort(args.ort, args.iters)
    else:
        raise SystemExit("need --torch or --ort")


if __name__ == "__main__":
    main()