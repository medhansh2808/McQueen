#!/usr/bin/env python3
"""Create fake human-vs-model predictions only to test the replay UI at home."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path


def action(row):
    if "action.servo_angle" in row:
        return float(row["action.servo_angle"]), float(row["action.motor_pwm"])
    a=row.get("action", {})
    return float(a.get("servo_angle", a.get("servo_angle_deg"))), float(a["motor_pwm"])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--episode", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--episode-index", type=int, default=0)
    args=ap.parse_args()
    rows=[]
    for line in (args.episode/"frames.jsonl").read_text().splitlines():
        if line.strip(): rows.append(json.loads(line))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        for i,r in enumerate(rows):
            s,m=action(r)
            # Clearly fake, deterministic offsets. Never model output.
            ps=s+4.0*math.sin(i/9.0)
            pm=m+12.0*math.sin(i/13.0)
            f.write(json.dumps({
                "episode_index":args.episode_index,
                "episode_frame_index":i,
                "dataset_index":i,
                "human_servo_angle_deg":s,
                "human_motor_pwm":m,
                "pred_servo_angle_deg":ps,
                "pred_motor_pwm":pm,
                "servo_error_deg":ps-s,
                "motor_error_pwm":pm-m,
                "demo_only":True,
            })+"\n")
    print(f"Demo predictions: {args.output} ({len(rows)} frames)")
    print("WARNING: these are fake predictions for viewer testing only")

if __name__ == "__main__": main()
