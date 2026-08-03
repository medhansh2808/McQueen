from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset


SERVO_CENTER_DEG = 80.0
SERVO_HALF_RANGE_DEG = 35.0
MAX_COMMAND = 1000.0
MAX_MOTOR_PWM = 255.0


FEATURES = {
    "observation.images.front_rgb": {
        "dtype": "image",
        "shape": (1080, 1920, 3),
        "names": ["height", "width", "channel"],
    },
    "observation.images.front_depth": {
        "dtype": "image",
        "shape": (360, 640, 1),
        "names": ["height", "width", "channel"],
        "info": {"is_depth_map": True},
    },
    "observation.state": {
        "dtype": "float32",
        "shape": (2,),
        "names": ["applied_steering", "applied_throttle"],
    },
    "action": {
        "dtype": "float32",
        "shape": (2,),
        "names": ["steering", "throttle"],
    },
    "mcqueen.requested_action": {
        "dtype": "float32",
        "shape": (2,),
        "names": ["requested_steering", "requested_throttle"],
    },
    "mcqueen.raw_actuator": {
        "dtype": "float32",
        "shape": (2,),
        "names": ["servo_angle_deg", "motor_pwm"],
    },
    "mcqueen.source_timestamp_s": {
        "dtype": "float32",
        "shape": (1,),
        "names": ["seconds"],
    },
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}: invalid JSON on line {line_number}: {error}"
                ) from error
    return rows


def normalize_applied_steering(servo_angle: float) -> float:
    value = (servo_angle - SERVO_CENTER_DEG) / SERVO_HALF_RANGE_DEG
    return float(np.clip(value, -1.0, 1.0))


def normalize_applied_throttle(motor_pwm: float) -> float:
    return float(np.clip(motor_pwm / MAX_MOTOR_PWM, -1.0, 1.0))


def normalize_requested(value: float) -> float:
    return float(np.clip(value / MAX_COMMAND, -1.0, 1.0))


def discover_episodes(root: Path) -> list[Path]:
    episodes: list[Path] = []
    for episode in sorted(root.iterdir()):
        if not episode.is_dir() or not episode.name.startswith("episode_"):
            continue

        metadata_path = episode / "episode.json"
        frames_path = episode / "frames.jsonl"
        if not metadata_path.is_file() or not frames_path.is_file():
            continue

        metadata = load_json(metadata_path)
        if metadata.get("status") != "completed":
            print(
                f"[SKIP] {episode.name}: status={metadata.get('status')!r}",
                flush=True,
            )
            continue

        episodes.append(episode)

    return episodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_root = args.input.expanduser().resolve()
    output_root = args.output.expanduser().resolve()

    if not input_root.is_dir():
        print(f"ERROR: input directory does not exist: {input_root}")
        return 2

    episodes = discover_episodes(input_root)
    if args.limit is not None:
        episodes = episodes[: args.limit]

    if not episodes:
        print("ERROR: no completed episode_* folders found")
        return 2

    if output_root.exists():
        if not args.overwrite:
            print(
                f"ERROR: output already exists: {output_root}\n"
                "Use --overwrite only when replacing a disposable/test dataset."
            )
            return 2
        shutil.rmtree(output_root)

    output_root.parent.mkdir(parents=True, exist_ok=True)

    print(f"Input:    {input_root}")
    print(f"Output:   {output_root}")
    print(f"Repo ID:  {args.repo_id}")
    print(f"Episodes: {len(episodes)}")
    print(f"FPS:      {args.fps}")
    print("Storage:  LeRobotDataset v3 image-backed")
    print()

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        root=output_root,
        fps=args.fps,
        robot_type="mcqueen_uno_q",
        features=FEATURES,
        use_videos=False,
        image_writer_processes=0,
        image_writer_threads=4,
    )

    total_frames = 0

    try:
        for episode_number, episode in enumerate(episodes):
            metadata = load_json(episode / "episode.json")
            rows = load_jsonl(episode / "frames.jsonl")

            if not rows:
                print(f"[SKIP] {episode.name}: no frames")
                continue

            task = str(
                metadata.get("task")
                or rows[0].get("task")
                or "Drive one lap through the corridor"
            )

            print(
                f"[EPISODE {episode_number:03d}] "
                f"{episode.name}: {len(rows)} frames",
                flush=True,
            )

            for row in rows:
                rgb_path = episode / row["observation.images.front_rgb"]
                depth_path = episode / row["observation.images.front_depth"]

                with Image.open(rgb_path) as image:
                    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()

                with Image.open(depth_path) as image:
                    depth = np.asarray(image, dtype=np.uint16).copy()

                if depth.ndim == 2:
                    depth = depth[..., None]

                applied = np.asarray(
                    [
                        normalize_applied_steering(
                            float(row["action.servo_angle"])
                        ),
                        normalize_applied_throttle(
                            float(row["action.motor_pwm"])
                        ),
                    ],
                    dtype=np.float32,
                )

                requested = np.asarray(
                    [
                        normalize_requested(
                            float(row["action.steering_command"])
                        ),
                        normalize_requested(
                            float(row["action.throttle_command"])
                        ),
                    ],
                    dtype=np.float32,
                )

                raw_actuator = np.asarray(
                    [
                        float(row["action.servo_angle"]),
                        float(row["action.motor_pwm"]),
                    ],
                    dtype=np.float32,
                )

                source_timestamp = np.asarray(
                    [float(row["timestamp_s"])],
                    dtype=np.float32,
                )

                dataset.add_frame(
                    {
                        "observation.images.front_rgb": rgb,
                        "observation.images.front_depth": depth,
                        "observation.state": applied.copy(),
                        "action": applied.copy(),
                        "mcqueen.requested_action": requested,
                        "mcqueen.raw_actuator": raw_actuator,
                        "mcqueen.source_timestamp_s": source_timestamp,
                        "task": task,
                    }
                )
                total_frames += 1

            dataset.save_episode()

        dataset.finalize()

    except Exception:
        print()
        print("Conversion failed.")
        print(f"Partial output remains at: {output_root}")
        raise

    print()
    print("Conversion complete")
    print(f"Episodes: {len(episodes)}")
    print(f"Frames:   {total_frames}")
    print(f"Output:   {output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
