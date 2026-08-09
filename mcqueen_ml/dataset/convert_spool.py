from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from lerobot.datasets import LeRobotDataset



def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))

    return rows


def build_features() -> dict:
    return {
        "observation.images.front_rgb": {
            "dtype": "image",
            "shape": (720, 1280, 3),
            "names": ["height", "width", "channel"],
        },
        "action": {
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

        if metadata.get("schema_version") != "mcqueen-rgb-spool-v1":
            print(
                f"[SKIP] {episode.name}: unsupported schema "
                f"{metadata.get('schema_version')!r}"
            )
            continue

        if metadata.get("status") != "completed":
            print(
                f"[SKIP] {episode.name}: status={metadata.get('status')!r}"
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
        print("ERROR: no completed RGB-only episodes found")
        return 2

    if output_root.exists():
        if not args.overwrite:
            print(
                f"ERROR: output already exists: {output_root}\n"
                "Use --overwrite only when replacing it intentionally."
            )
            return 2

        shutil.rmtree(output_root)

    output_root.parent.mkdir(parents=True, exist_ok=True)

    print(f"Input:    {input_root}")
    print(f"Output:   {output_root}")
    print(f"Repo ID:  {args.repo_id}")
    print(f"Episodes: {len(episodes)}")
    print(f"FPS:      {args.fps}")
    print()

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        root=output_root,
        fps=args.fps,
        robot_type="mcqueen_jetson_nano",
        features=build_features(),
        use_videos=False,
        image_writer_threads=4,
    )

    total_frames = 0

    try:
        for episode_number, episode in enumerate(episodes):
            rows = load_jsonl(episode / "frames.jsonl")

            if not rows:
                print(f"[SKIP] {episode.name}: no frames")
                continue

            task = str(rows[0].get("task", "Imitate expert driving"))
            print(
                f"[EPISODE {episode_number:03d}] "
                f"{episode.name}: {len(rows)} frames"
            )

            for row in rows:
                rgb_path = episode / row["observation.images.front_rgb"]

                with Image.open(rgb_path) as image:
                    rgb = np.asarray(
                        image.convert("RGB"),
                        dtype=np.uint8,
                    ).copy()

                servo_angle = float(row["action.servo_angle"])
                motor_pwm = float(row["action.motor_pwm"])
                action = np.asarray(
                [servo_angle, motor_pwm],
                dtype=np.float32,
            )
                source_timestamp = np.asarray(
                    [float(row["timestamp_s"])],
                    dtype=np.float32,
                )

                dataset.add_frame(
                    {
                        "observation.images.front_rgb": rgb,
                        "action": action,
                            "mcqueen.source_timestamp_s": source_timestamp,
                        "task": task,
                    }
                )
                total_frames += 1

            dataset.save_episode()

        dataset.finalize()
    except Exception:
        print()
        print("Conversion failed before completion.")
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
