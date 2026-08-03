from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class EpisodeWriter:
    """Simple RGB-only recording spool for later LeRobot conversion."""

    def __init__(
        self,
        dataset_root: Path,
        default_task: str,
        min_free_bytes: int,
        min_episode_seconds: float,
        fps: int,
        rgb_width: int,
        rgb_height: int,
    ) -> None:
        self.dataset_root = dataset_root
        self.default_task = default_task
        self.min_free_bytes = min_free_bytes
        self.min_episode_seconds = min_episode_seconds
        self.fps = fps
        self.rgb_width = rgb_width
        self.rgb_height = rgb_height
        self.lock = threading.RLock()
        self.active = False
        self.task = default_task
        self.session_dir: Optional[Path] = None
        self.rgb_dir: Optional[Path] = None
        self.frames_file = None
        self.started_monotonic = 0.0
        self.frame_index = 0

    def status(self) -> dict[str, object]:
        with self.lock:
            return {
                "logging": self.active,
                "recording": self.active,
                "session": str(self.session_dir or ""),
                "frame_index": self.frame_index,
                "task": self.task,
            }

    def _write_episode_json(self, status: str, **extra: object) -> None:
        if self.session_dir is None:
            return

        payload: dict[str, object] = {
            "schema_version": "mcqueen-rgb-spool-v1",
            "target_format": "lerobot-dataset-v3",
            "status": status,
            "task": self.task,
            "fps": self.fps,
            "rgb_width": self.rgb_width,
            "rgb_height": self.rgb_height,
            "rgb_encoding": "jpeg",
            "labels": ["action.servo_angle", "action.motor_pwm"],
            "frame_count": self.frame_index,
            **extra,
        }

        path = self.session_dir / "episode.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def start(self, task: Optional[str], camera_ready: bool) -> tuple[bool, str]:
        with self.lock:
            if self.active:
                return True, "already recording"

            if not camera_ready:
                return False, "camera is not ready"

            self.dataset_root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.dataset_root).free < self.min_free_bytes:
                return False, "free storage is below the configured minimum"

            base = datetime.now().strftime("episode_%Y%m%d_%H%M%S")
            session_dir = self.dataset_root / base
            suffix = 1

            while session_dir.exists():
                session_dir = self.dataset_root / f"{base}_{suffix}"
                suffix += 1

            rgb_dir = session_dir / "rgb"
            rgb_dir.mkdir(parents=True)
            frames_file = (session_dir / "frames.jsonl").open(
                "w", encoding="utf-8", buffering=1
            )

            self.active = True
            self.task = (task or self.default_task).strip() or self.default_task
            self.session_dir = session_dir
            self.rgb_dir = rgb_dir
            self.frames_file = frames_file
            self.started_monotonic = time.monotonic()
            self.frame_index = 0
            self._write_episode_json("recording", started_at=_now_iso())
            print(f"[LOG] Started {session_dir}", flush=True)
            return True, "recording started"

    def stop(self, reason: str) -> None:
        with self.lock:
            if not self.active:
                return

            session_dir = self.session_dir
            duration = time.monotonic() - self.started_monotonic
            frames = self.frame_index

            if self.frames_file is not None:
                self.frames_file.flush()
                os.fsync(self.frames_file.fileno())
                self.frames_file.close()

            if session_dir is not None:
                self._write_episode_json(
                    "completed",
                    stopped_at=_now_iso(),
                    stop_reason=reason,
                    duration_s=round(duration, 6),
                )

            self.active = False
            self.session_dir = None
            self.rgb_dir = None
            self.frames_file = None
            self.started_monotonic = 0.0
            self.frame_index = 0

            if session_dir is not None and duration < self.min_episode_seconds:
                shutil.rmtree(session_dir, ignore_errors=True)
                print(
                    f"[LOG] Deleted short episode "
                    f"({duration:.2f}s, {frames} frames): {reason}",
                    flush=True,
                )
            else:
                print(
                    f"[LOG] Stopped ({duration:.2f}s, {frames} frames): {reason}",
                    flush=True,
                )

    def save(self, clean_jpeg: bytes, motor_pwm: int, servo_angle: int) -> bool:
        with self.lock:
            if (
                not self.active
                or self.rgb_dir is None
                or self.frames_file is None
            ):
                return False

            if shutil.disk_usage(self.dataset_root).free < self.min_free_bytes:
                self.stop("storage fell below configured minimum")
                return False

            index = self.frame_index
            rgb_name = f"frame_{index:06d}.jpg"
            rgb_path = self.rgb_dir / rgb_name
            temporary = rgb_path.with_suffix(".jpg.tmp")
            temporary.write_bytes(clean_jpeg)
            temporary.replace(rgb_path)

            elapsed = time.monotonic() - self.started_monotonic
            row = {
                "timestamp": _now_iso(),
                "timestamp_s": round(elapsed, 6),
                "frame_index": index,
                "observation.images.front_rgb": f"rgb/{rgb_name}",
                "action.servo_angle": int(servo_angle),
                "action.motor_pwm": int(motor_pwm),
                "task": self.task,
            }

            self.frames_file.write(json.dumps(row, separators=(",", ":")) + "\n")
            if index and index % self.fps == 0:
                self.frames_file.flush()

            self.frame_index += 1
            return True
