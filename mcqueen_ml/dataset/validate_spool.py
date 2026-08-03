from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


EXPECTED_RGB_SIZE = (1280, 720)


@dataclass
class EpisodeResult:
    path: Path
    frames: int
    actual_hz: float
    issues: list[str]


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


def validate_episode(episode: Path) -> EpisodeResult:
    issues: list[str] = []
    metadata_path = episode / "episode.json"
    frames_path = episode / "frames.jsonl"

    if not metadata_path.is_file():
        return EpisodeResult(episode, 0, 0.0, ["missing episode.json"])

    if not frames_path.is_file():
        return EpisodeResult(episode, 0, 0.0, ["missing frames.jsonl"])

    metadata = load_json(metadata_path)
    rows = load_jsonl(frames_path)

    if metadata.get("schema_version") != "mcqueen-rgb-spool-v1":
        issues.append(
            f"schema_version={metadata.get('schema_version')!r}; "
            "expected 'mcqueen-rgb-spool-v1'"
        )

    if metadata.get("status") != "completed":
        issues.append(
            f"episode status is {metadata.get('status')!r}; expected 'completed'"
        )

    declared_count = metadata.get("frame_count")
    if declared_count is not None and int(declared_count) != len(rows):
        issues.append(
            f"episode.json frame_count={declared_count}, "
            f"frames.jsonl rows={len(rows)}"
        )

    if not rows:
        issues.append("episode contains no frames")
        return EpisodeResult(episode, 0, 0.0, issues)

    required_keys = {
        "timestamp",
        "timestamp_s",
        "frame_index",
        "observation.images.front_rgb",
        "action.servo_angle",
        "action.motor_pwm",
        "task",
    }
    timestamps: list[float] = []

    for expected_index, row in enumerate(rows):
        missing = required_keys.difference(row)

        if missing:
            issues.append(
                f"frame {expected_index}: missing keys {sorted(missing)}"
            )
            continue

        if int(row["frame_index"]) != expected_index:
            issues.append(
                f"frame position {expected_index}: "
                f"stored frame_index={row['frame_index']}"
            )

        timestamps.append(float(row["timestamp_s"]))
        rgb_path = episode / row["observation.images.front_rgb"]

        if not rgb_path.is_file():
            issues.append(f"missing RGB file: {rgb_path}")

        servo_angle = int(row["action.servo_angle"])
        motor_pwm = int(row["action.motor_pwm"])

        if not 0 <= servo_angle <= 180:
            issues.append(
                f"frame {expected_index}: invalid servo angle {servo_angle}"
            )

        if not -255 <= motor_pwm <= 255:
            issues.append(f"frame {expected_index}: invalid motor PWM {motor_pwm}")

    if any(
        current <= previous
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        issues.append("timestamps are not strictly increasing")

    actual_hz = 0.0
    if len(timestamps) > 1:
        duration = timestamps[-1] - timestamps[0]

        if duration <= 0:
            issues.append("episode duration is not positive")
        else:
            actual_hz = (len(timestamps) - 1) / duration

            if not 9.0 <= actual_hz <= 11.0:
                issues.append(
                    f"actual rate {actual_hz:.2f} Hz is outside 9-11 Hz"
                )

    for index in sorted({0, len(rows) - 1}):
        row = rows[index]
        rgb_path = episode / row["observation.images.front_rgb"]

        if rgb_path.is_file():
            with Image.open(rgb_path) as image:
                if image.size != EXPECTED_RGB_SIZE:
                    issues.append(
                        f"{rgb_path}: RGB size {image.size}; "
                        f"expected {EXPECTED_RGB_SIZE}"
                    )

                if image.mode != "RGB":
                    issues.append(
                        f"{rgb_path}: RGB mode {image.mode}; expected RGB"
                    )

    return EpisodeResult(episode, len(rows), actual_hz, issues)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Directory containing episode_* folders",
    )
    args = parser.parse_args()
    root = args.input.expanduser().resolve()

    if not root.is_dir():
        print(f"ERROR: spool directory does not exist: {root}")
        return 2

    episodes = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and path.name.startswith("episode_")
    )

    if not episodes:
        print(f"ERROR: no episode_* directories found under {root}")
        return 2

    failed = False
    total_frames = 0

    for episode in episodes:
        try:
            result = validate_episode(episode)
        except Exception as error:
            failed = True
            print(f"[FAIL] {episode.name}: {error}")
            continue

        total_frames += result.frames

        if result.issues:
            failed = True
            print(
                f"[FAIL] {episode.name}: "
                f"frames={result.frames}, hz={result.actual_hz:.2f}"
            )

            for issue in result.issues:
                print(f"       - {issue}")
        else:
            print(
                f"[OK]   {episode.name}: "
                f"frames={result.frames}, hz={result.actual_hz:.2f}"
            )

    print()
    print(f"Episodes: {len(episodes)}")
    print(f"Frames:   {total_frames}")
    print(f"Result:   {'FAILED' if failed else 'PASSED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
