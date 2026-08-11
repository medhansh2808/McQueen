from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from mcqueen_ml.dataset.schema_v2 import (
    SCHEMA_VERSION,
    validate_sequence,
)


V1_SCHEMA = "mcqueen-rgb-spool-v1"
EXPECTED_RGB_SIZE = (1280, 720)


@dataclass
class EpisodeResult:
    path: Path
    frames: int
    actual_hz: float
    issues: list[str]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    rows = []

    for line_number, line in enumerate(
        path.read_text().splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{path}: invalid JSON line "
                f"{line_number}: {error}"
            ) from error

    return rows


def validate_episode(episode: Path) -> EpisodeResult:
    issues = []

    metadata_path = episode / "episode.json"
    frames_path = episode / "frames.jsonl"

    if not metadata_path.is_file():
        return EpisodeResult(
            episode, 0, 0.0, ["missing episode.json"]
        )

    if not frames_path.is_file():
        return EpisodeResult(
            episode, 0, 0.0, ["missing frames.jsonl"]
        )

    metadata = load_json(metadata_path)
    rows = load_jsonl(frames_path)

    schema = metadata.get("schema_version")

    if schema not in (V1_SCHEMA, SCHEMA_VERSION):
        issues.append(
            f"unsupported schema_version={schema!r}"
        )

    if metadata.get("status") != "completed":
        issues.append(
            f"episode status={metadata.get('status')!r}; "
            "expected 'completed'"
        )

    declared = metadata.get("frame_count")

    if declared is not None and int(declared) != len(rows):
        issues.append(
            f"declared frame_count={declared}; "
            f"actual rows={len(rows)}"
        )

    if not rows:
        issues.append("episode contains no frames")
        return EpisodeResult(
            episode, 0, 0.0, issues
        )

    timestamps = []

    if schema == SCHEMA_VERSION:
        issues.extend(validate_sequence(rows))

    for expected_index, row in enumerate(rows):

        try:
            stored_index = int(row["frame_index"])
        except Exception:
            issues.append(
                f"frame {expected_index}: invalid frame_index"
            )
            continue

        if stored_index != expected_index:
            issues.append(
                f"frame position {expected_index}: "
                f"stored frame_index={stored_index}"
            )

        relative_rgb = row.get(
            "observation.images.front_rgb"
        )

        if not relative_rgb:
            issues.append(
                f"frame {expected_index}: missing RGB path"
            )
            continue

        rgb_path = episode / relative_rgb

        if not rgb_path.is_file():
            issues.append(
                f"frame {expected_index}: "
                f"missing RGB file {rgb_path}"
            )

        if schema == SCHEMA_VERSION:
            try:
                timestamps.append(
                    int(row["capture_monotonic_ns"])
                    / 1_000_000_000.0
                )
            except Exception:
                pass
        else:
            required_v1 = (
                "timestamp_s",
                "action.servo_angle",
                "action.motor_pwm",
            )

            for key in required_v1:
                if key not in row:
                    issues.append(
                        f"frame {expected_index}: "
                        f"missing {key}"
                    )

            try:
                timestamps.append(
                    float(row["timestamp_s"])
                )
            except Exception:
                pass

    if any(
        current <= previous
        for previous, current
        in zip(timestamps, timestamps[1:])
    ):
        issues.append(
            "timestamps are not strictly increasing"
        )

    actual_hz = 0.0

    if len(timestamps) > 1:
        duration = timestamps[-1] - timestamps[0]

        if duration <= 0:
            issues.append(
                "episode duration is not positive"
            )
        else:
            actual_hz = (
                (len(timestamps) - 1) / duration
            )

            if not 9.0 <= actual_hz <= 11.0:
                issues.append(
                    f"actual rate {actual_hz:.2f} Hz "
                    "outside expected 9-11 Hz"
                )

    for index in sorted({0, len(rows) - 1}):
        relative_rgb = rows[index].get(
            "observation.images.front_rgb"
        )

        if not relative_rgb:
            continue

        rgb_path = episode / relative_rgb

        if rgb_path.is_file():
            with Image.open(rgb_path) as image:

                if image.size != EXPECTED_RGB_SIZE:
                    issues.append(
                        f"{rgb_path}: size={image.size}; "
                        f"expected={EXPECTED_RGB_SIZE}"
                    )

                if image.mode != "RGB":
                    issues.append(
                        f"{rgb_path}: mode={image.mode}; "
                        "expected RGB"
                    )

    return EpisodeResult(
        episode,
        len(rows),
        actual_hz,
        issues,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    root = args.input.expanduser().resolve()

    if not root.is_dir():
        print(
            f"ERROR: spool directory does not exist: {root}"
        )
        return 2

    episodes = sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and path.name.startswith("episode_")
    )

    if not episodes:
        print(
            f"ERROR: no episode_* directories under {root}"
        )
        return 2

    failed = False
    total_frames = 0

    for episode in episodes:
        try:
            result = validate_episode(episode)
        except Exception as error:
            failed = True
            print(
                f"[FAIL] {episode.name}: {error}"
            )
            continue

        total_frames += result.frames

        if result.issues:
            failed = True

            print(
                f"[FAIL] {episode.name}: "
                f"frames={result.frames}, "
                f"hz={result.actual_hz:.2f}"
            )

            for issue in result.issues:
                print("       - " + issue)
        else:
            print(
                f"[OK]   {episode.name}: "
                f"frames={result.frames}, "
                f"hz={result.actual_hz:.2f}"
            )

    print()
    print(f"Episodes: {len(episodes)}")
    print(f"Frames:   {total_frames}")
    print(
        f"Result:   "
        f"{'FAILED' if failed else 'PASSED'}"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
