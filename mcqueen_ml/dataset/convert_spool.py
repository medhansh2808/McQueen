from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from lerobot.datasets import LeRobotDataset

from mcqueen_ml.dataset.schema_v2 import (
    SCHEMA_VERSION,
    validate_frame,
)


V1_SCHEMA = "mcqueen-rgb-spool-v1"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def build_features() -> dict:
    return {
        "observation.images.front_rgb": {
            "dtype": "image",
            "shape": (720, 1280, 3),
            "names": [
                "height",
                "width",
                "channel",
            ],
        },

        "observation.wheels": {
            "dtype": "float32",
            "shape": (3,),
            "names": [
                "encoder_valid",
                "left_ticks_per_s",
                "right_ticks_per_s",
            ],
        },

        "action": {
            "dtype": "float32",
            "shape": (2,),
            "names": [
                "servo_angle_deg",
                "motor_pwm",
            ],
        },

        "mcqueen.source_timestamp_ms": {
            "dtype": "int64",
            "shape": (1,),
            "names": ["milliseconds"],
        },

        "mcqueen.capture_monotonic_ns": {
            "dtype": "int64",
            "shape": (1,),
            "names": ["nanoseconds"],
        },
    }


def discover_episodes(root: Path) -> list[Path]:
    episodes = []

    for episode in sorted(root.iterdir()):
        if (
            not episode.is_dir()
            or not episode.name.startswith("episode_")
        ):
            continue

        metadata_path = episode / "episode.json"
        frames_path = episode / "frames.jsonl"

        if (
            not metadata_path.is_file()
            or not frames_path.is_file()
        ):
            continue

        metadata = load_json(metadata_path)
        schema = metadata.get("schema_version")

        if schema not in (
            V1_SCHEMA,
            SCHEMA_VERSION,
        ):
            print(
                f"[SKIP] {episode.name}: "
                f"unsupported schema {schema!r}"
            )
            continue

        if metadata.get("status") != "completed":
            print(
                f"[SKIP] {episode.name}: "
                f"status={metadata.get('status')!r}"
            )
            continue

        episodes.append(episode)

    return episodes


def canonical_values(row, schema):
    if schema == SCHEMA_VERSION:
        errors = validate_frame(row)

        if errors:
            raise ValueError(
                "invalid v2 frame: "
                + "; ".join(errors)
            )

        servo = float(
            row["action.servo_angle_deg"]
        )

        motor = float(
            row["action.motor_pwm"]
        )

        wheels = np.asarray(
            [
                1.0
                if row[
                    "observation.wheels.encoder_valid"
                ]
                else 0.0,

                float(
                    row[
                        "observation.wheels.left_ticks_per_s"
                    ]
                ),

                float(
                    row[
                        "observation.wheels.right_ticks_per_s"
                    ]
                ),
            ],
            dtype=np.float32,
        )

        source_ms = int(
            float(row["timestamp_unix_s"])
            * 1000.0
        )

        mono_ns = int(
            row["capture_monotonic_ns"]
        )

    else:
        servo = float(
            row["action.servo_angle"]
        )

        motor = float(
            row["action.motor_pwm"]
        )

        wheels = np.asarray(
            [0.0, 0.0, 0.0],
            dtype=np.float32,
        )

        source_ms = int(row["timestamp"])

        # Old v1 data had no monotonic timestamp.
        mono_ns = 0

    action = np.asarray(
        [servo, motor],
        dtype=np.float32,
    )

    return (
        action,
        wheels,
        np.asarray(
            [source_ms],
            dtype=np.int64,
        ),
        np.asarray(
            [mono_ns],
            dtype=np.int64,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--repo-id",
        required=True,
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--limit",
        type=int,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    input_root = (
        args.input.expanduser().resolve()
    )
    output_root = (
        args.output.expanduser().resolve()
    )

    if not input_root.is_dir():
        print(
            f"ERROR: input directory does not exist: "
            f"{input_root}"
        )
        return 2

    episodes = discover_episodes(input_root)

    if args.limit is not None:
        episodes = episodes[:args.limit]

    if not episodes:
        print(
            "ERROR: no completed supported episodes found"
        )
        return 2

    if output_root.exists():
        if not args.overwrite:
            print(
                f"ERROR: output exists: {output_root}"
            )
            return 2

        shutil.rmtree(output_root)

    output_root.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        for episode_number, episode in enumerate(
            episodes
        ):
            metadata = load_json(
                episode / "episode.json"
            )
            schema = metadata["schema_version"]

            rows = load_jsonl(
                episode / "frames.jsonl"
            )

            if not rows:
                print(
                    f"[SKIP] {episode.name}: no frames"
                )
                continue

            task = str(
                rows[0].get(
                    "task",
                    "Imitate expert driving",
                )
            )

            print(
                f"[EPISODE {episode_number:03d}] "
                f"{episode.name}: "
                f"{len(rows)} frames "
                f"schema={schema}"
            )

            for row in rows:
                rgb_path = (
                    episode
                    / row[
                        "observation.images.front_rgb"
                    ]
                )

                with Image.open(rgb_path) as image:
                    rgb = np.asarray(
                        image.convert("RGB"),
                        dtype=np.uint8,
                    ).copy()

                (
                    action,
                    wheels,
                    source_timestamp,
                    capture_monotonic,
                ) = canonical_values(
                    row,
                    schema,
                )

                dataset.add_frame(
                    {
                        "observation.images.front_rgb":
                            rgb,

                        "observation.wheels":
                            wheels,

                        "action":
                            action,

                        "mcqueen.source_timestamp_ms":
                            source_timestamp,

                        "mcqueen.capture_monotonic_ns":
                            capture_monotonic,

                        "task":
                            task,
                    }
                )

                total_frames += 1

            dataset.save_episode()

        dataset.finalize()

    except Exception:
        print()
        print(
            "Conversion failed before completion."
        )
        print(
            f"Partial output remains at: "
            f"{output_root}"
        )
        raise

    print()
    print("Conversion complete")
    print(f"Episodes: {len(episodes)}")
    print(f"Frames:   {total_frames}")
    print(f"Output:   {output_root}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
