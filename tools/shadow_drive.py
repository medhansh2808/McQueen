"""shadow_drive.py — shadow-mode demo generator (STANDARD FORMAT, use for every model).

Given a trained head checkpoint + prepacked val sessions, renders:
  <out-dir>/shadow_v1.mp4      expert vs our-model steering+throttle bars + trace strip
  <out-dir>/shadow_trace.csv   per-frame raw values
  <out-dir>/plot_steering.png  full-lap steering overlay graph
  <out-dir>/plot_throttle.png  full-lap throttle overlay graph

Usage:
  python tools/shadow_drive.py --ckpt run/real_head_v1.pt \
      --onnx models/driving_supercombo_master_batch.onnx \
      --val-root run/real_sessions/val --out-dir run/shadow_v1

Requires torch + onnx2pytorch + cv2 (+ matplotlib for plots): mcqueen-openpilot env.


Layout (960px wide canvas):
  Panels: STEERING (x 14..474) | THROTTLE (x 496..956)  — never overlap
  Each panel: title row, HUMAN bar (green), OUR MODEL bar (blue), value text inside panel
  Bottom: rolling steering trace strip (HUMAN green / OUR MODEL blue)
Outputs: shadow_v1.mp4 + shadow_trace.csv
"""
import sys, csv, argparse
sys.path.insert(0, "/home/junior/mcqueen/models")
sys.path.insert(0, "/home/junior/mcqueen/run")
from pathlib import Path
import cv2
import numpy as np
import torch
from train_frozen_action import load_sessions, ActionHead, HeadConfig
from action_adapter import FrozenActionModel

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", required=True, help="trained head checkpoint (.pt)")
    ap.add_argument("--onnx", required=True, help="batch-patched supercombo ONNX")
    ap.add_argument("--val-root", required=True, help="prepacked val sessions root")
    ap.add_argument("--out-dir", required=True, help="output dir for mp4/csv/plots")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--fps", type=int, default=10)
    return ap.parse_args()


args = parse_args()
DEVICE = args.device
CKPT = args.ckpt
ONNX = args.onnx
VAL = Path(args.val_root)
OUT_DIR = Path(args.out_dir)
OUT_DIR.mkdir(parents=True, exist_ok=True)

GREEN = (80, 220, 80)
BLUE = (255, 160, 20)

ckpt = torch.load(CKPT, map_location=DEVICE)
cfg = HeadConfig(**ckpt["head_config"])
mean = np.array(ckpt["stats"]["mean"], dtype=np.float32)
std = np.array(ckpt["stats"]["std"], dtype=np.float32)

print("[1/4] loading frozen trunk + head...", flush=True)
model = FrozenActionModel(ONNX).to(DEVICE).eval()
head = ActionHead(cfg).to(DEVICE)
head.load_state_dict(ckpt["model_state_dict"])
head.eval()

print("[2/4] loading val sessions...", flush=True)
sessions = load_sessions(VAL)
zd = torch.zeros(1, 25, 8, dtype=torch.float16, device=DEVICE)
zt = torch.zeros(1, 2, dtype=torch.float16, device=DEVICE)
za = torch.zeros(1, 2, dtype=torch.float16, device=DEVICE)


def panel(img, x0, title, hum, mod):
    """One metric panel: title + HUMAN bar + OUR MODEL bar. Width budget 460px."""
    bar_h = 22
    cv2.putText(img, title, (x0, img.shape[0] - 162),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2)
    for row, (label, value, color) in enumerate([
            ("HUMAN", hum, GREEN), ("OUR MODEL", mod, BLUE)]):
        y0 = img.shape[0] - 142 + row * (bar_h + 10)
        cv2.putText(img, label, (x0, y0 + bar_h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
        bx = x0 + 104
        bw = 290
        cv2.rectangle(img, (bx, y0), (bx + bw, y0 + bar_h), (60, 60, 60), -1)
        mid = bx + bw // 2
        cv2.line(img, (mid, y0), (mid, y0 + bar_h), (200, 200, 200), 1)
        px = int(mid + max(-1.0, min(1.0, value)) * (bw // 2))
        cv2.rectangle(img, (min(mid, px), y0), (max(mid, px), y0 + bar_h), color, -1)
        cv2.putText(img, f"{value:+.2f}", (bx + bw + 8, y0 + bar_h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)


def draw(frame_jpg_path, true_s, pred_s, true_t, pred_t, trace_t, trace_p):
    img = cv2.imread(str(frame_jpg_path))
    if img is None:
        return None
    H, W = img.shape[:2]
    scale = 960 / W
    img = cv2.resize(img, (960, int(H * scale)))
    H, W = img.shape[:2]

    panel(img, 14, "STEERING", true_s, pred_s)
    panel(img, 496, "THROTTLE", true_t, pred_t)

    # rolling trace strip (bottom, below panels — no overlap)
    strip_h = 64
    y_base = H - 14
    cv2.rectangle(img, (0, H - strip_h), (W, H), (30, 30, 30), -1)
    n = len(trace_t)
    if n > 1:
        for k in range(1, n):
            x0 = int((k - 1) / (n - 1) * (W - 40)) + 20
            x1 = int(k / (n - 1) * (W - 40)) + 20
            yt = int(y_base - trace_t[k - 1] * (strip_h // 2 - 8))
            yp = int(y_base - trace_p[k - 1] * (strip_h // 2 - 8))
            cv2.line(img, (x0, yt), (x1, yt), GREEN, 2)
            cv2.line(img, (x0, yp), (x1, yp), BLUE, 2)
    cv2.putText(img, "steering trace:  GREEN = HUMAN   BLUE = OUR MODEL",
                (20, H - strip_h + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (230, 230, 230), 1)
    return img


preds = []
print("[3/4] running shadow inference + rendering...", flush=True)
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = None
trace_t, trace_p = [], []
idx = 0
with torch.no_grad(), torch.autocast("cuda"):
    for s in sessions:
        buffer = torch.zeros(1, 24, 512, dtype=torch.float16, device=DEVICE)
        frame_paths = sorted((s.session_dir / "rgb_raw_upright").glob("frame_*.jpg"))
        for i in range(1, s.length):
            img_np = np.concatenate([s.window(i)[0], s.window(i)[1]], axis=0)[None]
            img_t = torch.from_numpy(img_np).to(DEVICE)
            action, hidden, _ = model(img=img_t, big_img=img_t, desire_pulse=zd,
                                      traffic_convention=zt, action_t=za,
                                      features_buffer=buffer)
            p = (head(hidden)[0].float().cpu().numpy() * std + mean)
            true_s, true_t = float(s.labels[i][0]), float(s.labels[i][1])
            preds.append((idx, true_s, true_t, float(p[0]), float(p[1])))
            trace_t.append(true_s); trace_p.append(float(p[0]))
            if len(trace_t) > 240:
                trace_t.pop(0); trace_p.pop(0)
            jpg = frame_paths[i] if i < len(frame_paths) else frame_paths[-1]
            canvas = draw(jpg, true_s, float(p[0]), true_t, float(p[1]), trace_t, trace_p)
            if canvas is not None:
                if writer is None:
                    writer = cv2.VideoWriter(str(OUT_DIR / "shadow_v1.mp4"), fourcc,
                                             args.fps, (canvas.shape[1], canvas.shape[0]))
                writer.write(canvas)
            idx += 1
            if idx % 400 == 0:
                print(f"   rendered {idx} frames...", flush=True)

if writer:
    writer.release()
with open(OUT_DIR / "shadow_trace.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["frame", "true_steering", "true_throttle", "pred_steering", "pred_throttle"])
    w.writerows(preds)
print(f"[4/4] DONE: {idx} frames -> {OUT_DIR/'shadow_v1.mp4'}", flush=True)
