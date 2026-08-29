#!/usr/bin/env python3
"""Isolated GPU policy worker for the McQueen autonomy loop.

2026-08-22: ORT-CUDA (11.3 ms trunk) segfaults when initialized inside the
GStreamer receiver process alongside torch. This worker runs the FULL policy
(trunk + trained head) in its OWN process and serves predictions over
localhost TCP, so the receiver never touches CUDA ORT.

Protocol (newline-delimited):
  request : {"w":640,"h":480,"sz":460800}\n  followed by exactly sz bytes I420
  reply   : {"servo_angle_deg":..,"motor_pwm":..,...,"infer_ms":..}\n

Launch on the RTX:
  LD_LIBRARY_PATH=$(ls -d ~/.local/lib/python3.10/site-packages/nvidia/{cudnn,cublas,cuda_runtime,cufft,curand}/lib | tr '\n' ':') \
  "$MCQUEEN_PY" realtime/rtx/policy_worker.py \
      --ckpt "$MCQUEEN_CKPT" --onnx "$MCQUEEN_ONNX" --port 9801

Verify "trunk=ORT ['CUDAExecutionProvider', ...]" in worker stdout.
"""
import argparse
import json
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path


def build_policy(args):
    # rtx_policy_v1 lives next to this file; import it by location rather than
    # from a hardcoded deploy dir, so the stack runs from any checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rtx_policy_v1 import CorridorPolicyV1

    models_dirs = [args.models_dir] if args.models_dir else []
    return CorridorPolicyV1(
        args.ckpt,
        args.onnx,
        models_dirs=models_dirs,
        device=args.device,
        trunk_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        policy = self.server.policy
        buf = self.rfile.readline()
        if not buf:
            return
        try:
            hdr = json.loads(buf.decode("utf-8"))
            w, h = int(hdr["w"]), int(hdr["h"])
            sz = int(hdr["sz"])
        except Exception as exc:
            self.wfile.write(json.dumps({"error": repr(exc)}).encode() + b"\n")
            self.wfile.flush()
            return
        raw = b""
        while len(raw) < sz:
            chunk = self.rfile.read(sz - len(raw))
            if not chunk:
                return
            raw += chunk
        import numpy as np

        frame = np.frombuffer(raw, dtype=np.uint8).reshape(h * 3 // 2, w)
        out = policy.infer_sample(frame)
        self.wfile.write(json.dumps(out).encode() + b"\n")
        self.wfile.flush()


class PolicyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    p = argparse.ArgumentParser()
    # Defaults come from realtime/config.env via the environment; no path is
    # baked into this file.
    p.add_argument("--ckpt", default=os.environ.get("MCQUEEN_CKPT"))
    p.add_argument("--onnx", default=os.environ.get("MCQUEEN_ONNX"))
    p.add_argument("--models-dir", default=os.environ.get("MCQUEEN_MODELS_DIR"),
                   help="dir holding train_frozen_action.py / action_adapter.py")
    p.add_argument("--port", type=int,
                   default=int(os.environ.get("MCQUEEN_POLICY_PORT", 9801)))
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    if not args.ckpt:
        p.error("--ckpt is required (or set MCQUEEN_CKPT)")
    if not args.onnx:
        p.error("--onnx is required (or set MCQUEEN_ONNX)")

    print("[WORKER] building policy...", flush=True)
    policy = build_policy(args)

    # Q43 loud-fail guard (2026-08-24): a silent CUDA->CPU fallback poisons
    # benches AND training feature spaces (v2/v3 mismatch lesson) — refuse to
    # serve unless the trunk actually came up on CUDA when --device cuda.
    providers = getattr(policy.model, "providers", None)
    if args.device == "cuda":
        if providers is None:
            print("[WORKER] FATAL: trunk=torch-convert (no provider info); "
                  "--device cuda requires ORT trunk with CUDAExecutionProvider",
                  flush=True)
            sys.exit(3)
        if not any("CUDA" in p for p in providers):
            print("[WORKER] FATAL: CUDA EP missing, got {} — check "
                  "LD_LIBRARY_PATH nvidia libs; refusing CPU fallback".format(
                      providers), flush=True)
            sys.exit(3)

    server = PolicyServer(("127.0.0.1", args.port), Handler)
    server.policy = policy
    print("[WORKER] serving on 127.0.0.1:{} — providers={}".format(
        args.port, getattr(policy.model, "providers", "torch-convert")), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
