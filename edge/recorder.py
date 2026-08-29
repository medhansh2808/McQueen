"""Jetson-local canonical driving dataset recorder for McQueen.

Runs inside mcqueen-edge so camera frames are paired with the same
DriveController state used by the physical actuators.

Python 3.6+ compatible for the Jetson Nano image.
"""

import json
import threading
import time
from pathlib import Path

import cv2

from .encoder_source import NullEncoderSource
from .record_row import SCHEMA_VERSION, TASK, build_frame_row
from .server import steering_to_angle


DEFAULT_CAMERA_DEVICE = (
    "/dev/v4l/by-id/"
    "usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-"
    "video-index0"
)

RECORD_FPS = 10.0


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def throttle_to_pwm(raw_throttle, enabled):
    if not enabled:
        return 0

    throttle = clamp(int(raw_throttle), -1000, 1000)
    return int(round(throttle * 255.0 / 1000.0))


class JetsonDatasetRecorder(threading.Thread):
    """Capture RGB + exact drive command + wheel encoder observation."""

    def __init__(
        self,
        runtime_state,
        drive_controller,
        root_dir="data/spool",
        camera_device=DEFAULT_CAMERA_DEVICE,
        record_fps=RECORD_FPS,
        encoder_source=None,
    ):
        threading.Thread.__init__(self, name="mcqueen-recorder")
        self.daemon = True

        self.runtime_state = runtime_state
        self.drive = drive_controller
        self.encoder_source = (
            encoder_source
            if encoder_source is not None
            else NullEncoderSource()
        )

        self.root_dir = Path(root_dir)
        self.camera_device = str(camera_device)
        self.record_fps = float(record_fps)

        self.stop_event = threading.Event()
        self.cap = None

        self.active = False
        self.session_name = ""
        self.session_dir = None
        self.episode_dir = None
        self.frames_file = None

        self.frame_index = 0
        self.next_episode_index = 0
        self.next_save_monotonic = None
        self.last_capture_monotonic_ns = None

    def stop(self):
        self.stop_event.set()

    def _open_camera(self):
        cap = cv2.VideoCapture(self.camera_device)

        cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG")
        )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)

        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass

            self.runtime_state.set_camera_ready(False)
            return None

        self.runtime_state.set_camera_ready(True)

        print(
            "Recorder camera ready: {} ({}x{} @ {:.1f} fps reported)".format(
                self.camera_device,
                int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                cap.get(cv2.CAP_PROP_FPS),
            ),
            flush=True,
        )

        return cap

    def _discover_next_episode(self):
        highest = -1

        if self.session_dir is not None and self.session_dir.exists():
            for path in self.session_dir.glob("episode_*"):
                if not path.is_dir():
                    continue

                try:
                    index = int(path.name.split("_")[-1])
                except (ValueError, IndexError):
                    continue

                highest = max(highest, index)

        self.next_episode_index = highest + 1

    def _metadata(self, status):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": str(status),
            "task": TASK,
            "frame_count": int(self.frame_index),
            "recording_fps": int(self.record_fps),

            "camera": {
                "device": self.camera_device,
                "width": 1280,
                "height": 720,
            },

            "action": {
                "servo_angle_center_deg": 90,
                "servo_angle_range_deg": [45, 115],
                "motor_pwm_range": [-255, 255],
            },

            "wheel_encoders": {
                "stored_units": "raw_ticks",
                "physical_calibration_required": True,
            },
        }

    def _write_metadata(self, status):
        if self.episode_dir is None:
            return

        path = self.episode_dir / "episode.json"

        with path.open("w") as handle:
            json.dump(self._metadata(status), handle, indent=2)

    def _start_episode(self):
        state = self.runtime_state.snapshot()
        session_name = state.get("session", "")

        if not session_name:
            return False

        if self.session_name != session_name:
            self.session_name = session_name
            self.session_dir = self.root_dir / self.session_name
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self._discover_next_episode()

        episode_name = "episode_%06d" % self.next_episode_index
        self.episode_dir = self.session_dir / episode_name

        rgb_dir = self.episode_dir / "rgb"
        rgb_dir.mkdir(parents=True, exist_ok=False)

        self.frames_file = (
            self.episode_dir / "frames.jsonl"
        ).open("w", buffering=1)

        self.frame_index = 0
        self.last_capture_monotonic_ns = None
        self.next_save_monotonic = time.monotonic()
        self.active = True

        self.runtime_state.set_episode(episode_name, 0)
        self._write_metadata("recording")

        print(
            "Recorder episode started: {}".format(self.episode_dir),
            flush=True,
        )

        return True

    def _stop_episode(self, status):
        if not self.active:
            return

        self.active = False

        if self.frames_file is not None:
            self.frames_file.close()
            self.frames_file = None

        self._write_metadata(status)

        print(
            "Recorder episode saved: {} frames={} status={}".format(
                self.episode_dir,
                self.frame_index,
                status,
            ),
            flush=True,
        )

        self.next_episode_index += 1

    def _save_frame(
        self,
        frame,
        capture_monotonic_ns,
        timestamp_unix_s,
    ):
        drive_state = self.drive.snapshot()

        servo_angle = steering_to_angle(
            drive_state["steering"]
        )

        motor_pwm = throttle_to_pwm(
            drive_state["throttle"],
            drive_state["motor_enabled"],
        )

        encoder = self.encoder_source.snapshot(
            capture_monotonic_ns
        )

        filename = "frame_%06d.jpg" % self.frame_index
        relative_path = "rgb/" + filename
        output_path = self.episode_dir / relative_path

        if not cv2.imwrite(
            str(output_path),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 90],
        ):
            raise RuntimeError(
                "Failed to save frame: {}".format(output_path)
            )

        row = build_frame_row(
            frame_index=self.frame_index,
            relative_rgb_path=relative_path,
            capture_monotonic_ns=capture_monotonic_ns,
            timestamp_unix_s=timestamp_unix_s,
            servo_angle_deg=servo_angle,
            motor_pwm=motor_pwm,
            drive_state=drive_state,
            encoder=encoder,
        )

        self.frames_file.write(json.dumps(row) + "\n")

        self.frame_index += 1
        self.runtime_state.set_frame_index(self.frame_index)

        if self.frame_index == 1 or self.frame_index % 10 == 0:
            print(
                "Recorder frame={:05d} servo={:3d} pwm={:4d} "
                "encoder_valid={}".format(
                    self.frame_index,
                    int(servo_angle),
                    int(motor_pwm),
                    bool(encoder["encoder_valid"]),
                ),
                flush=True,
            )

    def run(self):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        camera_failures = 0

        try:
            while not self.stop_event.is_set():

                if self.cap is None:
                    self.cap = self._open_camera()

                    if self.cap is None:
                        self.stop_event.wait(1.0)
                        continue

                    camera_failures = 0

                ok, frame = self.cap.read()

                # Timestamp immediately after the camera frame is returned.
                capture_monotonic_ns = int(
                    time.monotonic() * 1000000000
                )
                timestamp_unix_s = time.time()

                if not ok:
                    camera_failures += 1

                    if camera_failures >= 10:
                        self.runtime_state.set_camera_ready(False)

                        try:
                            self.cap.release()
                        except Exception:
                            pass

                        self.cap = None
                        camera_failures = 0

                    continue

                camera_failures = 0

                requested = bool(
                    self.runtime_state.snapshot().get(
                        "recording",
                        False,
                    )
                )

                if requested and not self.active:
                    self._start_episode()

                elif not requested and self.active:
                    self._stop_episode("completed")

                if not self.active:
                    continue

                now = time.monotonic()

                if now < self.next_save_monotonic:
                    continue

                while self.next_save_monotonic <= now:
                    self.next_save_monotonic += (
                        1.0 / self.record_fps
                    )

                if (
                    self.last_capture_monotonic_ns is not None
                    and capture_monotonic_ns
                    <= self.last_capture_monotonic_ns
                ):
                    continue

                self.last_capture_monotonic_ns = (
                    capture_monotonic_ns
                )

                self._save_frame(
                    frame,
                    capture_monotonic_ns,
                    timestamp_unix_s,
                )

        except Exception as exc:
            print(
                "ERROR: Jetson dataset recorder crashed: {!r}".format(
                    exc
                ),
                flush=True,
            )

            if self.active:
                try:
                    self._stop_episode("interrupted")
                except Exception:
                    pass

        finally:
            if self.active:
                try:
                    self._stop_episode("interrupted")
                except Exception:
                    pass

            self.runtime_state.set_camera_ready(False)

            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass

            self.cap = None
