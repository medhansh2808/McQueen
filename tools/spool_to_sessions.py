#!/usr/bin/env python3
"""spool_to_sessions.py — convert a McQueen recorder spool into McQueen session dirs.

Reads recorder spools produced by the Jetson edge recorder (schema
mcqueen-rgb-spool-v1):

    <spool_root>/session_YYYYMMDD_HHMMSS/
        episode_XXXXXX/
            episode.json      (metadata: status, frame_count, action ranges)
            frames.jsonl      (per-frame rows: action.servo_angle,
                               action.motor_pwm, observation.images.front_rgb, ...)
            rgb/frame_XXXXXX.jpg

and writes McQueen-format session directories consumable by
train_frozen_action.py (same layout as tools/donkey/tub_to_sessions.py):

    <out_root>/session_XXX/
        controls.csv                          (columns: steering, throttle; one row per frame)
        rgb_raw_upright/frame_000000.jpg ...  (copied frames, zero-padded names)

Label normalization (recorder space -> trainer [-1,1] space), the exact
inverse of the recorder's steering_to_servo_angle / throttle_to_pwm mapping:

    steering = (90 - servo_angle) / 25   for servo_angle >= 90 (center -> full left)
    steering = (90 - servo_angle) / 45   for servo_angle < 90  (center -> full right)
    throttle = motor_pwm / 255           # [-255, 255] -> [-1, 1]

The asymmetry is intentional: the recorder maps raw steering [-1000, 1000]
onto servo angles [115, 45], so 115 = full left and 45 = full right.

Split semantics differ from tub_to_sessions.py on purpose: the val set is the LAST
--val-frac fraction of EPISODES (whole episodes, never cut mid-episode), and episodes
are never merged across sessions — the temporal trainer's features_buffer resets on
episode boundaries, which are real time boundaries.

Episodes with status != "completed" (e.g. a recorder crash mid-episode) are skipped
with a warning and reported in split.json.

Torch-free (DECISION 024): standard-library only, runs on any python3.

Usage:
    python tools/spool_to_sessions.py \
        --spool data/spool \
        --out ~/mcqueen/run/real_sessions \
        --val-frac 0.2 --chunk 500
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

FRAME_DIR = "rgb_raw_upright"
FRAME_PREFIX = "frame_"
FRAME_EXT = ".jpg"

IMAGE_KEY = "observation.images.front_rgb"
SERVO_KEY = "action.servo_angle_deg"  # edge recorder (canonical, schema v2)
SERVO_KEY_LEGACY = "action.servo_angle"  # old standalone recorder (v1)
PWM_KEY = "action.motor_pwm"

SERVO_CENTER = 90.0
SERVO_LEFT_MAX = 115.0  # full-left servo angle (raw steering -1000)
SERVO_RIGHT_MAX = 45.0  # full-right servo angle (raw steering +1000)
PWM_RANGE = 255.0


def iter_episodes(spool_root: Path):
    """Yield (episode_dir, rows) for every completed episode in recording order.

    Episodes with status != "completed" are skipped and reported via a
    (episode_dir, status) warning through `skipped` (filled by caller).
    """
    episodes = sorted(spool_root.glob("session_*/episode_*"))
    if not episodes:
        raise RuntimeError(f"no session_*/episode_* dirs under {spool_root}")

    n_completed = 0
    for episode in episodes:
        metadata_path = episode / "episode.json"
        frames_path = episode / "frames.jsonl"

        if not metadata_path.is_file() or not frames_path.is_file():
            yield episode, [], [f"missing {metadata_path.name} or {frames_path.name}"]
            continue

        metadata = json.loads(metadata_path.read_text())
        status = metadata.get("status", "unknown")

        if status != "completed":
            yield episode, [], [f"status={status!r} (not completed)"]
            continue

        rows = []
        for line_number, line in enumerate(
            frames_path.read_text().splitlines(), start=1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"{frames_path}: invalid JSON line {line_number}: {error}"
                ) from error

        if not rows:
            yield episode, [], ["empty frames.jsonl"]
            continue

        yield episode, rows, []
        n_completed += 1

    print(f"read {n_completed} completed episodes", file=sys.stderr)


def normalize_label(servo_angle, motor_pwm):
    """Recorder label space -> trainer [-1,1] space.

    Exact inverse of the recorder's steering_to_servo_angle mapping, which is
    asymmetric around center: servo 90 = 0, 115 = -1 (full left), 45 = +1
    (full right).
    """
    servo = float(servo_angle)
    if servo >= SERVO_CENTER:
        steering = (SERVO_CENTER - servo) / (SERVO_LEFT_MAX - SERVO_CENTER)
    else:
        steering = (SERVO_CENTER - servo) / (SERVO_CENTER - SERVO_RIGHT_MAX)
    throttle = float(motor_pwm) / PWM_RANGE
    return steering, throttle


def write_session(session_dir: Path, episode_dir: Path, rows: list[dict]) -> None:
    """Write one McQueen session dir from frames.jsonl rows."""
    frame_dir = session_dir / FRAME_DIR
    frame_dir.mkdir(parents=True, exist_ok=False)
    width = max(6, len(str(len(rows) - 1)))
    with open(session_dir / "controls.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["steering", "throttle"])
        for i, row in enumerate(rows):
            image = row.get(IMAGE_KEY)
            if not image:
                raise RuntimeError(f"row {i}: missing {IMAGE_KEY}")
            src = episode_dir / image
            if not src.is_file():
                raise RuntimeError(f"row {i}: missing image file: {src}")
            steering, throttle = normalize_label(
                row.get(SERVO_KEY, row.get(SERVO_KEY_LEGACY)),
                row[PWM_KEY],
            )
            writer.writerow([f"{steering:.6f}", f"{throttle:.6f}"])
            dst = frame_dir / f"{FRAME_PREFIX}{i:0{width}d}{FRAME_EXT}"
            shutil.copyfile(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spool", required=True, help="recorder spool root (data/spool)")
    ap.add_argument("--out", required=True, help="output root (train/ + val/ subdirs created)")
    ap.add_argument("--val-frac", type=float, default=0.2, help="fraction of EPISODES for val (0..1)")
    ap.add_argument("--chunk", type=int, default=500, help="frames per session (episode-internal)")
    args = ap.parse_args()

    spool = Path(args.spool)
    out = Path(args.out)
    if not spool.is_dir():
        sys.exit(f"spool not found: {spool}")
    if args.val_frac <= 0.0 or args.val_frac >= 1.0:
        sys.exit("--val-frac must be in (0, 1)")

    episodes = []
    skipped = []
    for episode_dir, rows, issues in iter_episodes(spool):
        if issues:
            skipped.append((episode_dir, "; ".join(issues)))
            print(f"SKIP {episode_dir}: {'; '.join(issues)}", file=sys.stderr)
            continue
        episodes.append((episode_dir, rows))

    if not episodes:
        sys.exit("no completed episodes found")

    total_frames = sum(len(rows) for _, rows in episodes)
    n_val_eps = max(1, min(round(len(episodes) * args.val_frac), len(episodes) - 1))
    n_train_eps = len(episodes) - n_val_eps
    print(
        f"episodes: {len(episodes)} (train {n_train_eps} / val {n_val_eps}, "
        f"whole-episode split)  frames: {total_frames}",
        file=sys.stderr,
    )

    train_episodes = episodes[:n_train_eps]
    val_episodes = episodes[n_train_eps:]

    counts = {}
    provenance = {}
    for name, ep_list in (("train", train_episodes), ("val", val_episodes)):
        root = out / name
        if root.exists():
            sys.exit(f"refusing to overwrite existing root: {root}")
        root.mkdir(parents=True)
        n_sessions = 0
        n_frames = 0
        for episode_dir, rows in ep_list:
            for i in range(0, len(rows), args.chunk):
                chunk = rows[i : i + args.chunk]
                if len(chunk) < 2:
                    continue
                session_dir = root / f"session_{n_sessions:03d}"
                write_session(session_dir, episode_dir, chunk)
                provenance[str(session_dir)] = str(episode_dir)
                n_sessions += 1
                n_frames += len(chunk)
        counts[name] = (n_frames, n_sessions, len(ep_list))
        print(
            f"{name}: {counts[name][0]} frames -> {counts[name][1]} sessions "
            f"({counts[name][2]} episodes)",
            file=sys.stderr,
        )

    with open(out / "split.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "spool": str(spool),
                "total_episodes": len(episodes),
                "total_frames": total_frames,
                "val_frac": args.val_frac,
                "chunk": args.chunk,
                "counts": counts,
                "skipped_episodes": [
                    [str(path), reason] for path, reason in skipped
                ],
                "session_to_episode": provenance,
                "columns": ["steering", "throttle"],
                "frame_format": "jpg",
            },
            f,
            indent=2,
        )
    print(f"done -> {out}")


if __name__ == "__main__":
    main()