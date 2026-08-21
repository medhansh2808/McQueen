"""Tests for tools/spool_to_sessions.py — spool -> session conversion."""

import base64
import csv
import json

import pytest

from tools.spool_to_sessions import (
    iter_episodes,
    normalize_label,
    write_session,
)

TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
)


def make_spool(tmp_path, episodes):
    """Build a synthetic recorder spool.

    episodes: list of (name, status, frames) where frames is a list of
    (servo_angle, motor_pwm) label pairs.
    """
    spool = tmp_path / "spool"
    session_dir = spool / "session_20260819_000000"
    for ep_index, (name, status, frames) in enumerate(episodes):
        episode = session_dir / f"episode_{ep_index:06d}"
        rgb = episode / "rgb"
        rgb.mkdir(parents=True)
        meta = {
            "schema_version": "mcqueen-rgb-spool-v1",
            "status": status,
            "frame_count": len(frames),
            "recording_fps": 10,
            "camera": {"width": 1280, "height": 720},
            "action": {
                "servo_angle_center_deg": 90,
                "servo_angle_range_deg": [45, 115],
                "motor_pwm_range": [-255, 255],
            },
        }
        (episode / "episode.json").write_text(json.dumps(meta))
        with open(episode / "frames.jsonl", "w") as f:
            for i, (servo, pwm) in enumerate(frames):
                fname = f"frame_{i:06d}.jpg"
                (rgb / fname).write_bytes(TINY_JPEG)
                f.write(
                    json.dumps(
                        {
                            "timestamp": 1000 + i * 100,
                            "timestamp_s": 1.0 + i * 0.1,
                            "frame_index": i,
                            "observation.images.front_rgb": "rgb/" + fname,
                            "action.servo_angle": servo,
                            "action.motor_pwm": pwm,
                            "task": "Imitate expert driving",
                            "mcqueen.raw.steering_command": 0,
                            "mcqueen.raw.throttle_command": 0,
                            "mcqueen.raw.motor_enabled": True,
                        }
                    )
                    + "\n"
                )
    return spool


def test_normalize_label():
    assert normalize_label(90, 0) == (0.0, 0.0)
    assert normalize_label(115, -255) == (-1.0, -1.0)
    assert normalize_label(45, 255) == (1.0, 1.0)
    assert normalize_label(103, 0)[0] == pytest.approx(-13 / 25)
    assert normalize_label(68, 0)[0] == pytest.approx(22 / 45)
    steering, throttle = normalize_label(90, 127)
    assert steering == 0.0
    assert throttle == pytest.approx(127 / 255)


def test_write_session_labels_and_frames(tmp_path):
    spool = make_spool(tmp_path, [("e0", "completed", [(90, 0), (45, 255), (115, -255)])])
    episode = sorted(spool.glob("session_*/episode_*"))[0]
    rows = [json.loads(l) for l in (episode / "frames.jsonl").read_text().splitlines()]

    session = tmp_path / "session_000"
    write_session(session, episode, rows)

    with open(session / "controls.csv", newline="") as f:
        reader = list(csv.reader(f))
    assert reader[0] == ["steering", "throttle"]
    assert float(reader[1][0]) == pytest.approx(0.0)
    assert float(reader[1][1]) == pytest.approx(0.0)
    assert float(reader[2][0]) == pytest.approx(1.0)
    assert float(reader[2][1]) == pytest.approx(1.0)
    assert float(reader[3][0]) == pytest.approx(-1.0)
    assert float(reader[3][1]) == pytest.approx(-1.0)

    frames = sorted((session / "rgb_raw_upright").glob("frame_*.jpg"))
    assert [p.name for p in frames] == [
        "frame_000000.jpg",
        "frame_000001.jpg",
        "frame_000002.jpg",
    ]
    assert frames[0].read_bytes() == TINY_JPEG


def test_write_session_edge_schema_servo_deg_key(tmp_path):
    """Edge recorder (schema v2) rows use action.servo_angle_deg."""
    spool = tmp_path / "spool"
    episode = spool / "session_20260819_000000" / "episode_000000"
    rgb = episode / "rgb"
    rgb.mkdir(parents=True)
    (episode / "episode.json").write_text(
        json.dumps({"schema_version": "mcqueen-driving-spool-v2", "status": "completed"})
    )
    with open(episode / "frames.jsonl", "w") as f:
        fname = "frame_000000.jpg"
        (rgb / fname).write_bytes(TINY_JPEG)
        f.write(
            json.dumps(
                {
                    "observation.images.front_rgb": "rgb/" + fname,
                    "action.servo_angle_deg": 45,
                    "action.motor_pwm": 255,
                    "observation.wheels.encoder_valid": True,
                }
            )
            + "\n"
        )
    rows = [json.loads(l) for l in (episode / "frames.jsonl").read_text().splitlines()]

    session = tmp_path / "session_000"
    write_session(session, episode, rows)

    with open(session / "controls.csv", newline="") as f:
        reader = list(csv.reader(f))
    assert float(reader[1][0]) == pytest.approx(1.0)
    assert float(reader[1][1]) == pytest.approx(1.0)


def test_iter_episodes_skips_non_completed(tmp_path):
    spool = make_spool(
        tmp_path,
        [
            ("e0", "completed", [(90, 0)]),
            ("e1", "recording", [(90, 0)]),
            ("e2", "aborted", [(90, 0)]),
        ],
    )
    episodes = list(iter_episodes(spool))
    assert len(episodes) == 3
    completed = [e for e in episodes if not e[2]]
    assert len(completed) == 1
    assert completed[0][0].name == "episode_000000"
    skipped = [e for e in episodes if e[2]]
    assert len(skipped) == 2
    assert "status=" in skipped[0][2][0]


def test_iter_episodes_missing_files(tmp_path):
    spool = tmp_path / "spool"
    episode = spool / "session_20260819_000000" / "episode_000000"
    episode.mkdir(parents=True)
    (episode / "episode.json").write_text("{}")
    episodes = list(iter_episodes(spool))
    assert len(episodes) == 1
    assert "missing" in episodes[0][2][0]


def test_iter_episodes_no_episodes(tmp_path):
    with pytest.raises(RuntimeError):
        list(iter_episodes(tmp_path / "empty"))


def test_iter_episodes_invalid_json(tmp_path):
    spool = make_spool(tmp_path, [("e0", "completed", [(90, 0)])])
    episode = sorted(spool.glob("session_*/episode_*"))[0]
    with open(episode / "frames.jsonl", "a") as f:
        f.write("not json\n")
    with pytest.raises(RuntimeError):
        list(iter_episodes(spool))