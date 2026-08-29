"""rtx_policy_v1.py — real inference policy for the RTP receiver (v1 corridor head).

Loads the frozen supercombo trunk (batch-patched ONNX via action_adapter) plus the
trained corridor head checkpoint, and turns decoded GStreamer frames into
(servon_angle_deg, pwm255) pairs.

Frame path per sample:
  I420 (GStreamer) -> BGR -> RGB -> resize 512x256 -> supercombo YUV pack
  window = [prev_packed, cur_packed] (12ch) -> trunk -> head -> [-1,1] pair

Inverse label mapping (exact inverse of tools/spool_to_sessions.normalize_label):
  steering >= 0: servo = 90 - 45*s   (right)
  steering <  0: servo = 90 - 25*s   (left)
  pwm255 = throttle * 255

GPU when available; falls back to CPU (same precedence rules as the pipeline).
"""
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np


class OrtTrunk:
    """onnxruntime fallback for the supercombo trunk.

    2026-08-22: onnx2pytorch cannot convert the export and torch-convert dies;
    ORT on the single-file big_driving_supercombo.onnx (see
    make_driving_supercombo_onnx.py) verifies at ~346 ms/frame CPU. Replicates
    FrozenActionModel.forward's contract:
    returns [full_output, hidden_state, None] with hidden = flat[1064:1576].

    NOTE: CUDAExecutionProvider runs at 11.3 ms standalone but SEGFAULTS when
    initialized inside this process alongside GStreamer + torch; keep CPU EP
    here until inference is moved to an isolated worker process.
    """

    HIDDEN_SLICE = slice(1064, 1576)

    def __init__(self, onnx_path, providers=None):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = 12
        if providers is None:
            providers = ["CPUExecutionProvider"]
        self.sess = ort.InferenceSession(onnx_path, so, providers=providers)
        self.providers = self.sess.get_providers()
        self.names = [i.name for i in self.sess.get_inputs()]
        self.types = {i.name: i.type for i in self.sess.get_inputs()}
        self._dev = ["cpu"]

    def __call__(self, img=None, big_img=None, desire_pulse=None,
                 traffic_convention=None, action_t=None,
                 features_buffer=None, **kw):
        args = {"img": img, "big_img": big_img, "desire_pulse": desire_pulse,
                "traffic_convention": traffic_convention, "action_t": action_t,
                "features_buffer": features_buffer}
        feed = {}
        for name in self.names:
            v = args[name]
            a = v.detach().cpu().numpy() if hasattr(v, "detach") else np.asarray(v)
            if "float16" in self.types[name]:
                a = a.astype(np.float16)
            elif "uint8" in self.types[name]:
                a = a.astype(np.uint8)
            else:
                a = a.astype(np.float32)
            feed[name] = a
        outs = self.sess.run(None, feed)
        o0 = np.asarray(outs[0])
        torch = self.torch
        full = torch.from_numpy(np.ascontiguousarray(o0.astype(np.float32))).to(self.torch_dev)
        if o0.ndim == 2 and o0.shape[1] >= self.HIDDEN_SLICE.stop:
            hid_np = o0[:, self.HIDDEN_SLICE].astype(np.float32)
            hid = torch.from_numpy(np.ascontiguousarray(hid_np)).to(self.torch_dev)
        else:
            hid = full
        return [full, hid, None]


class CorridorPolicyV1:
    def __init__(self, ckpt_path, onnx_path,
                 models_dirs=(), device=None, steer_scale=1.0,
                 trunk_providers=None):
        import torch
        self.torch = torch
        extra_dirs = list(models_dirs)
        fallback = os.environ.get("MCQUEEN_MODELS_DIR")
        if fallback:
            extra_dirs.append(fallback)
        for p in extra_dirs:
            if Path(p).is_dir() and p not in sys.path:
                sys.path.insert(0, p)
        from train_frozen_action import ActionHead, HeadConfig
        from action_adapter import FrozenActionModel

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.steer_scale = float(steer_scale)

        ckpt = torch.load(ckpt_path, map_location=device)
        cfg = HeadConfig(**ckpt["head_config"])
        self.mean = np.array(ckpt["stats"]["mean"], dtype=np.float32)
        self.std = np.array(ckpt["stats"]["std"], dtype=np.float32)

        try:
            self.model = FrozenActionModel(onnx_path).to(device).eval()
            print("[POLICY] trunk=torch-convert", flush=True)
        except Exception as exc:
            print(
                "[POLICY] torch-convert failed ({!r}); using ORT trunk".format(exc),
                flush=True,
            )
            # Single-file layout: the canonical ONNX is the patched one (no _ks suffix).
            self.model = OrtTrunk(onnx_path, providers=trunk_providers)
            self.model.torch = torch
            self.model.torch_dev = device
            print("[POLICY] trunk=ORT", self.model.providers, "from", onnx_path,
                  flush=True)
        self.head = ActionHead(cfg).to(device)
        self.head.load_state_dict(ckpt["model_state_dict"])
        self.head.eval()

        zd = torch.zeros(1, 25, 8, dtype=torch.float16, device=device)
        zt = torch.zeros(1, 2, dtype=torch.float16, device=device)
        self._zeros = (zd, zt, za_t(device))
        # Recurrent features_buffer — training rolled hidden states through
        # this window (train_frozen_action.py); zeros-per-frame is out of
        # distribution and produced saturated head outputs (2026-08-22).
        self._fbuf = torch.zeros(1, 24, 512, dtype=torch.float16, device=device)
        self.prev_packed = None
        import threading, queue as _q
        self._lock = threading.Lock()
        self._fq = _q.Queue(maxsize=1)
        self._latest = {"servo_angle_deg": 90.0, "motor_pwm": 0,
                        "raw_steering": 0, "raw_throttle": 0,
                        "motor_on": False, "infer_ms": 0.0}
        self._worker_on = False

    def start_worker(self):
        """Non-blocking mode: push frames via submit_frame(), read self.latest()."""
        import threading
        if self._worker_on:
            return
        self._worker_on = True

        def loop():
            while True:
                frame = self._fq.get()
                try:
                    t0 = time.perf_counter()
                    out = self.infer_sample(frame)
                    out["infer_ms"] = (time.perf_counter() - t0) * 1000.0
                    with self._lock:
                        self._latest = out
                except Exception as exc:
                    print("[POLICY] worker error {!r}".format(exc), flush=True)

        threading.Thread(target=loop, daemon=True).start()

    def submit_frame(self, frame):
        """Drop-oldest push; never blocks the pipeline."""
        if self._fq.full():
            try:
                self._fq.get_nowait()
            except Exception:
                pass
        self._fq.put(frame)

    def latest(self):
        with self._lock:
            return dict(self._latest)

    def _pack(self, i420_or_bgr):
        frame = i420_or_bgr
        if frame.ndim == 2 or frame.shape[0] * 3 // 2 == frame.shape[0] * frame.shape[1]:
            pass  # heuristic below handles both; cvtColor decides
        bgr = None
        try:
            bgr = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
        except cv2.error:
            bgr = frame
        if bgr is None or bgr.ndim != 3:
            raise ValueError("undecodable frame")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (512, 256), interpolation=cv2.INTER_AREA)
        from action_adapter import rgb_to_supercombo_yuv
        return rgb_to_supercombo_yuv(rgb).astype(np.uint8)

    def infer_sample(self, frame):
        """frame: decoded sample (I420 planes or BGR). Returns dict for CTRL."""
        cur = self._pack(frame)
        prev = cur if self.prev_packed is None else self.prev_packed
        window = np.concatenate([prev, cur], axis=0)[None]
        self.prev_packed = cur

        torch = self.torch
        x = torch.from_numpy(window).to(self.device)
        zd, zt, za = self._zeros
        buf = self._fbuf
        cm = (torch.autocast("cuda")
              if self.device == "cuda"
              else torch.autocast("cpu", enabled=False))
        with torch.no_grad(), cm:
            _, hidden, _ = self.model(img=x, big_img=x, desire_pulse=zd,
                                      traffic_convention=zt, action_t=za,
                                      features_buffer=buf)
            # roll the recurrence exactly like training: shift window, append
            self._fbuf = torch.cat(
                [buf[:, 1:, :], hidden.detach().to(buf.dtype).unsqueeze(1)], dim=1)
            p = (self.head(hidden.float())[0].cpu().numpy() * self.std + self.mean)

        s = max(-1.0, min(1.0, float(p[0]) * self.steer_scale))
        t = max(-1.0, min(1.0, float(p[1])))
        if s >= 0:
            servo = 90.0 - 45.0 * s
        else:
            servo = 90.0 - 25.0 * s
        servo = max(45.0, min(115.0, servo))
        pwm255 = int(round(t * 255))
        return {"servo_angle_deg": float(servo),
                "motor_pwm": pwm255,
                "raw_steering": int(round(s * 1000)),
                "raw_throttle": int(round(abs(t) * 1000)),
                "motor_on": abs(t) > 0.01}


def za_t(device):
    import torch
    return torch.zeros(1, 2, dtype=torch.float16, device=device)


class PolicyEndpointPolicy:
    """Client for the isolated GPU policy_worker process (policy_worker.py).

    Same surface the receiver uses on CorridorPolicyV1: .device, start_worker(),
    submit_frame(np_i420_2d), latest() -> dict. Frames are forwarded over
    localhost TCP; CUDA stays out of the receiver process (segfault otherwise).
    """

    def __init__(self, endpoint):
        self.addr = endpoint.rsplit(":", 1)
        self.addr = (self.addr[0], int(self.addr[1]))
        self.device = "endpoint:" + endpoint
        import threading, queue as _q
        self._lock = threading.Lock()
        self._fq = _q.Queue(maxsize=1)
        self._latest = {"servo_angle_deg": 90.0, "motor_pwm": 0,
                        "raw_steering": 0, "raw_throttle": 0,
                        "motor_on": False, "infer_ms": 0.0}
        self._worker_on = False

    def _rpc(self, frame):
        import socket as _s
        h, w = frame.shape
        hdr = json.dumps({"w": int(w), "h": int(h * 2 // 3), "sz": int(frame.size)})
        payload = frame.tobytes()
        t0 = time.perf_counter()
        s = _s.create_connection(self.addr, timeout=5.0)
        try:
            s.sendall(hdr.encode() + b"\n" + payload)
            f = s.makefile()
            line = f.readline()
        finally:
            s.close()
        out = json.loads(line if isinstance(line, str) else line.decode())
        out["infer_ms"] = (time.perf_counter() - t0) * 1000.0
        with self._lock:
            self._latest = out
        return out

    def start_worker(self):
        import threading
        if self._worker_on:
            return
        self._worker_on = True

        def loop():
            while True:
                frame = self._fq.get()
                try:
                    self._rpc(frame)
                except Exception as exc:
                    print("[POLICY-EP] worker error {!r}".format(exc), flush=True)

        threading.Thread(target=loop, daemon=True).start()

    def submit_frame(self, frame):
        if self._fq.full():
            try:
                self._fq.get_nowait()
            except Exception:
                pass
        self._fq.put(frame)

    def latest(self):
        with self._lock:
            return dict(self._latest)


def c_packet(session, seq, pol, ts_ms=None):
    """Build an edge-protocol C packet from a policy result."""
    import time
    if ts_ms is None:
        ts_ms = int(time.time() * 1000) % 100000000
    return ("C,rc-car,{},{},{},{},{},{}\n".format(
        session, seq, ts_ms, pol["raw_steering"], pol["raw_throttle"],
        1 if pol["motor_on"] else 0)).encode("ascii")
