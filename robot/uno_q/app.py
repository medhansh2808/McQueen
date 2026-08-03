#!/usr/bin/env python3
"""McQueen: phone teleop + local 15 Hz RGB/depth/YOLO dataset recorder.

One process owns everything on the Linux side:
- UDP 5007: Kachow phone control
- HTTP 8080: phone LOG start/stop
- OAK-D: 1080p clean RGB, depth heatmap, YOLOv6 annotations
- Local episodes: controls.csv + clean/viz JPEG pairs
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import signal
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import depthai as dai
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from arduino.app_utils import Bridge
from recorder import EpisodeWriter as SpoolEpisodeWriter

# ------------------------------ fixed project configuration -----------------
PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_ROOT / "models/yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob"
DATASET_ROOT = PROJECT_ROOT / "datasets"

UDP_BIND = "0.0.0.0"
UDP_PORT = 5007
HTTP_BIND = "0.0.0.0"
HTTP_PORT = 8080
FAILSAFE_SECONDS = 0.300

SOURCE_FPS = 30
SAVE_HZ = 10
SAVE_INTERVAL = 1.0 / SAVE_HZ
RGB_WIDTH = 1920
RGB_HEIGHT = 1080
DEPTH_WIDTH = 640
DEPTH_HEIGHT = 360
NN_WIDTH = 512
NN_HEIGHT = 288
JPEG_QUALITY = 85
VIZ_JPEG_QUALITY = 75

CONFIDENCE_THRESHOLD = 0.45
NMS_IOU_THRESHOLD = 0.45
MAX_DETECTIONS = 20
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
MAX_CAMERA_STALE_SECONDS = 1.0
MIN_EPISODE_SECONDS = 1.0
DEFAULT_TASK = "Teleoperate McQueen around the track"

COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


FONT = load_font(18)
SMALL_FONT = load_font(15)


class BridgeClient:
    """Serializes all RouterBridge RPC calls across app threads."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ready = False

    def call(self, method: str, *args: object) -> object:
        with self.lock:
            try:
                result = Bridge.call(method, *args)
                self.ready = True
                return result
            except Exception:
                self.ready = False
                raise

    def wait_until_ready(self, stop_event: threading.Event) -> None:
        print("[BRIDGE] Waiting for MCU ping...", flush=True)
        while not stop_event.is_set():
            try:
                ping = self.call("ping")
                self.call("estop")
                print(f"[BRIDGE] Ready, ping={ping}", flush=True)
                return
            except Exception as error:
                self.ready = False
                print(f"[BRIDGE] Not ready: {error}", flush=True)
                stop_event.wait(1.0)


@dataclass
class ControlState:
    phone_address: Optional[tuple[str, int]] = None
    session: str = ""
    session_armed: bool = False
    last_sequence: int = -1
    echo_timestamp_ms: int = 0
    steering_command: int = 0
    throttle_command: int = 0
    motor_enabled: bool = False
    last_command_monotonic: float = 0.0
    failsafe: bool = True


class EpisodeWriter:
    CSV_HEADER = [
        "timestamp",
        "timestamp_s",
        "frame_index",
        "motor_pwm_sent",
        "servo_angle_sent",
        "camera_frame",
        "visualization_frame",
        "task",
    ]

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.active = False
        self.task = DEFAULT_TASK
        self.session_dir: Optional[Path] = None
        self.frames_dir: Optional[Path] = None
        self.csv_file: Optional[Any] = None
        self.csv_writer: Optional[csv.writer] = None
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

    def start(self, task: Optional[str], camera_ready: bool) -> tuple[bool, str]:
        with self.lock:
            if self.active:
                return True, "already recording"
            if not camera_ready:
                return False, "camera is not ready"
            DATASET_ROOT.mkdir(parents=True, exist_ok=True)
            free_bytes = shutil.disk_usage(DATASET_ROOT).free
            if free_bytes < MIN_FREE_BYTES:
                return False, "less than 2 GB free storage"

            base = datetime.now().strftime("session_%Y%m%d_%H%M%S")
            session_dir = DATASET_ROOT / base
            suffix = 1
            while session_dir.exists():
                session_dir = DATASET_ROOT / f"{base}_{suffix}"
                suffix += 1

            frames_dir = session_dir / "frames"
            frames_dir.mkdir(parents=True)
            csv_file = (session_dir / "controls.csv").open(
                "w", newline="", encoding="utf-8", buffering=1
            )
            writer = csv.writer(csv_file)
            writer.writerow(self.CSV_HEADER)

            self.active = True
            self.task = (task or DEFAULT_TASK).strip() or DEFAULT_TASK
            self.session_dir = session_dir
            self.frames_dir = frames_dir
            self.csv_file = csv_file
            self.csv_writer = writer
            self.started_monotonic = time.monotonic()
            self.frame_index = 0
            print(f"[LOG] Started {session_dir}", flush=True)
            return True, "recording started"

    def stop(self, reason: str) -> None:
        with self.lock:
            if not self.active:
                return
            session_dir = self.session_dir
            duration = time.monotonic() - self.started_monotonic
            frames = self.frame_index
            if self.csv_file is not None:
                self.csv_file.flush()
                os.fsync(self.csv_file.fileno())
                self.csv_file.close()

            self.active = False
            self.session_dir = None
            self.frames_dir = None
            self.csv_file = None
            self.csv_writer = None
            self.started_monotonic = 0.0
            self.frame_index = 0

            if session_dir is not None and duration < MIN_EPISODE_SECONDS:
                shutil.rmtree(session_dir, ignore_errors=True)
                print(
                    f"[LOG] Deleted short episode ({duration:.2f}s, {frames} frames): {reason}",
                    flush=True,
                )
            else:
                print(
                    f"[LOG] Stopped ({duration:.2f}s, {frames} frames): {reason}",
                    flush=True,
                )

    def save(
        self,
        clean_jpeg: bytes,
        visualization_jpeg: bytes,
        motor_pwm: int,
        servo_angle: int,
    ) -> bool:
        with self.lock:
            if (
                not self.active
                or self.frames_dir is None
                or self.csv_writer is None
                or self.csv_file is None
            ):
                return False

            free_bytes = shutil.disk_usage(DATASET_ROOT).free
            if free_bytes < MIN_FREE_BYTES:
                self.stop("storage fell below 2 GB")
                return False

            index = self.frame_index
            filename = f"frame_{index:06d}.jpg"
            viz_filename = f"frame_{index:06d}_viz.jpg"
            clean_path = self.frames_dir / filename
            viz_path = self.frames_dir / viz_filename

            # Write temporary files first, then atomically rename them.
            clean_tmp = clean_path.with_suffix(".jpg.tmp")
            viz_tmp = viz_path.with_suffix(".jpg.tmp")
            clean_tmp.write_bytes(clean_jpeg)
            viz_tmp.write_bytes(visualization_jpeg)
            clean_tmp.replace(clean_path)
            viz_tmp.replace(viz_path)

            elapsed = time.monotonic() - self.started_monotonic
            self.csv_writer.writerow(
                [
                    now_iso(),
                    f"{elapsed:.6f}",
                    index,
                    motor_pwm,
                    servo_angle,
                    f"frames/{filename}",
                    f"frames/{viz_filename}",
                    self.task,
                ]
            )
            self.csv_file.flush()
            self.frame_index += 1
            return True


class RuntimeState:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.bridge = BridgeClient()
        self.control = ControlState()
        self.control_lock = threading.Lock()
        self.episode = SpoolEpisodeWriter(
            DATASET_ROOT, DEFAULT_TASK, MIN_FREE_BYTES, MIN_EPISODE_SECONDS, SAVE_HZ
        )
        self.camera_ready = False
        self.camera_last_packet = 0.0
        self.camera_lock = threading.Lock()

    def set_camera_ready(self, ready: bool) -> None:
        with self.camera_lock:
            self.camera_ready = ready
            if ready:
                self.camera_last_packet = time.monotonic()

    def touch_camera(self) -> None:
        with self.camera_lock:
            self.camera_ready = True
            self.camera_last_packet = time.monotonic()

    def camera_status(self) -> tuple[bool, float]:
        with self.camera_lock:
            age = (
                time.monotonic() - self.camera_last_packet
                if self.camera_last_packet
                else math.inf
            )
            return self.camera_ready, age


STATE = RuntimeState()


class TeleopServer(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="teleop", daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((UDP_BIND, UDP_PORT))
        self.sock.settimeout(0.02)
        self.last_status_send = 0.0

    def stop_mcu(self, reason: str) -> None:
        with STATE.control_lock:
            STATE.control.steering_command = 0
            STATE.control.throttle_command = 0
            STATE.control.motor_enabled = False
            STATE.control.failsafe = True
        try:
            STATE.bridge.call("estop")
        except Exception as error:
            print(f"[BRIDGE] ESTOP failed during {reason}: {error}", flush=True)

    def process_packet(self, payload: bytes, address: tuple[str, int]) -> None:
        parts = [part.strip() for part in payload.decode("utf-8", errors="replace").strip().split(",")]
        if len(parts) < 5:
            return
        packet_type = parts[0][:1]
        try:
            session = parts[2]
            sequence = int(parts[3])
            timestamp_ms = int(parts[4])
        except (IndexError, ValueError):
            return

        with STATE.control_lock:
            state = STATE.control
            if session != state.session:
                state.session = session
                state.session_armed = False
                state.last_sequence = -1
            if sequence <= state.last_sequence:
                return
            state.phone_address = address
            state.last_sequence = sequence
            state.echo_timestamp_ms = timestamp_ms

        if packet_type == "H":
            return
        if packet_type == "E":
            with STATE.control_lock:
                STATE.control.session_armed = False
            self.stop_mcu("phone ESTOP")
            print("[PHONE] ESTOP", flush=True)
            return
        if packet_type != "C" or len(parts) != 8:
            return

        try:
            steering = clamp(int(parts[5]), -1000, 1000)
            throttle = clamp(int(parts[6]), -1000, 1000)
            motor_enabled = int(parts[7]) != 0
        except ValueError:
            return

        with STATE.control_lock:
            state = STATE.control
            if not state.session_armed:
                if steering == 0 and throttle == 0:
                    state.session_armed = True
                    print(f"[PHONE] Session armed: {session}", flush=True)
                else:
                    return

        try:
            STATE.bridge.call(
                "set_drive",
                steering,
                throttle,
                1 if (motor_enabled or throttle != 0) else 0,
            )
        except Exception as error:
            print(f"[BRIDGE] Drive failed: {error}", flush=True)
            self.stop_mcu("bridge failure")
            return

        with STATE.control_lock:
            state = STATE.control
            state.steering_command = steering
            state.throttle_command = throttle
            state.motor_enabled = motor_enabled or throttle != 0
            state.last_command_monotonic = time.monotonic()
            state.failsafe = False

    @staticmethod
    def steering_to_angle(steering: int) -> int:
        steering = -clamp(steering, -1000, 1000)
        if steering < 0:
            return 45 + ((steering + 1000) * (80 - 45)) // 1000
        return 80 + (steering * (115 - 80)) // 1000

    def send_status(self, now: float) -> None:
        if now - self.last_status_send < (1.0 / 15.0):
            return
        self.last_status_send = now
        with STATE.control_lock:
            state = STATE.control
            if state.phone_address is None or not state.session:
                return
            status = (
                f"S,{state.session},{state.last_sequence},{state.echo_timestamp_ms},"
                f"{state.steering_command},{self.steering_to_angle(state.steering_command)},"
                f"{state.throttle_command},{state.throttle_command},"
                f"{1 if state.failsafe else 0},"
                f"{'WIFI' if not state.failsafe else 'NONE'},-1\n"
            )
            address = state.phone_address
        try:
            self.sock.sendto(status.encode("utf-8"), address)
        except OSError:
            pass

    def enforce_failsafe(self, now: float) -> None:
        with STATE.control_lock:
            last = STATE.control.last_command_monotonic
            already_safe = STATE.control.failsafe
        if last and now - last > FAILSAFE_SECONDS and not already_safe:
            print("[FAILSAFE] Phone timeout", flush=True)
            self.stop_mcu("phone timeout")

    def run(self) -> None:
        STATE.bridge.wait_until_ready(STATE.stop_event)
        if STATE.stop_event.is_set():
            return
        print(f"[UDP] Listening on {UDP_BIND}:{UDP_PORT}", flush=True)
        while not STATE.stop_event.is_set():
            try:
                payload, address = self.sock.recvfrom(2048)
                self.process_packet(payload, address)
            except socket.timeout:
                pass
            except OSError as error:
                if not STATE.stop_event.is_set():
                    print(f"[UDP] {error}", flush=True)
            now = time.monotonic()
            self.enforce_failsafe(now)
            self.send_status(now)
        self.stop_mcu("app shutdown")
        self.sock.close()


class HttpHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[HTTP] {self.address_string()} {fmt % args}", flush=True)

    def read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    def send_json(self, status_code: int, extra: Optional[dict[str, object]] = None) -> None:
        camera_ready, camera_age = STATE.camera_status()
        payload: dict[str, object] = {
            "ok": status_code < 400,
            "success": status_code < 400,
            "camera_ready": camera_ready and camera_age <= MAX_CAMERA_STALE_SECONDS,
            "camera_age_s": None if math.isinf(camera_age) else round(camera_age, 3),
            **STATE.episode.status(),
        }
        if extra:
            payload.update(extra)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def handle_control(self) -> None:
        body = self.read_body()
        text = body.decode("utf-8", errors="replace")
        path = self.path.split("?", 1)[0].lower()
        combined = f"{self.command} {path} {text}".lower()

        task: Optional[str] = None
        try:
            parsed = json.loads(text) if text else {}
            if isinstance(parsed, dict) and isinstance(parsed.get("task"), str):
                task = parsed["task"]
        except json.JSONDecodeError:
            pass

        stop_request = (
            self.command == "DELETE"
            or "stop" in combined
            or '"logging":false' in combined
            or '"recording":false' in combined
            or '"enabled":false' in combined
        )
        start_request = (
            "start" in combined
            or '"logging":true' in combined
            or '"recording":true' in combined
            or '"enabled":true' in combined
        )

        if stop_request:
            STATE.episode.stop("phone LOG off")
            self.send_json(200)
            return

        if start_request or self.command in ("POST", "PUT", "PATCH"):
            camera_ready, camera_age = STATE.camera_status()
            ok, message = STATE.episode.start(
                task,
                camera_ready
                and camera_age <= MAX_CAMERA_STALE_SECONDS
                and STATE.bridge.ready,
            )
            self.send_json(200 if ok else 503, {"message": message})
            return

        self.send_json(200)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/status", "/health", "/"):
            self.send_json(200)
        else:
            self.handle_control()

    def do_POST(self) -> None:
        self.handle_control()

    def do_PUT(self) -> None:
        self.handle_control()

    def do_PATCH(self) -> None:
        self.handle_control()

    def do_DELETE(self) -> None:
        self.handle_control()

    def do_OPTIONS(self) -> None:
        self.send_json(200)


class HttpServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="http", daemon=True)
        self.server = ThreadingHTTPServer((HTTP_BIND, HTTP_PORT), HttpHandler)
        self.server.timeout = 0.5

    def run(self) -> None:
        print(f"[HTTP] Listening on {HTTP_BIND}:{HTTP_PORT}", flush=True)
        while not STATE.stop_event.is_set():
            self.server.handle_request()
        self.server.server_close()


# -------------------------------- YOLOv6 decode -----------------------------
def iou_xyxy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    intersection = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_a = np.maximum(0.0, box[2] - box[0]) * np.maximum(0.0, box[3] - box[1])
    area_b = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])
    return intersection / np.maximum(area_a + area_b - intersection, 1e-6)


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    if boxes.size == 0:
        return []
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        remaining = order[1:]
        order = remaining[iou_xyxy(boxes[current], boxes[remaining]) <= threshold]
    return keep


def decode_yolov6(packet: dai.NNData) -> list[dict[str, object]]:
    expected = {
        195840: (36, 64, 8),
        48960: (18, 32, 16),
        12240: (9, 16, 32),
    }
    collected: list[tuple[np.ndarray, int, int, int]] = []
    for name in packet.getAllLayerNames():
        values = np.asarray(packet.getLayerFp16(name), dtype=np.float32)
        spec = expected.get(int(values.size))
        if spec is not None:
            collected.append((values, *spec))
    if len(collected) != 3:
        raise RuntimeError(
            "expected 3 YOLO heads, got "
            + str([(name, len(packet.getLayerFp16(name))) for name in packet.getAllLayerNames()])
        )

    boxes_all: list[np.ndarray] = []
    scores_all: list[np.ndarray] = []
    classes_all: list[np.ndarray] = []

    for values, height, width, stride in collected:
        prediction = values.reshape(85, height, width).transpose(1, 2, 0).reshape(-1, 85)
        objectness = prediction[:, 4]
        class_probabilities = prediction[:, 5:]
        class_ids = class_probabilities.argmax(axis=1)
        class_scores = class_probabilities[np.arange(class_probabilities.shape[0]), class_ids]
        scores = objectness * class_scores
        mask = scores >= CONFIDENCE_THRESHOLD
        if not np.any(mask):
            continue

        filtered = prediction[mask]
        scores = scores[mask]
        class_ids = class_ids[mask]
        grid_y, grid_x = np.meshgrid(
            np.arange(height, dtype=np.float32),
            np.arange(width, dtype=np.float32),
            indexing="ij",
        )
        grid = np.stack((grid_x, grid_y), axis=-1).reshape(-1, 2)[mask]
        centers = (filtered[:, 0:2] + grid) * float(stride)
        sizes = np.exp(np.clip(filtered[:, 2:4], -10.0, 10.0)) * float(stride)
        xy1 = centers - sizes / 2.0
        xy2 = centers + sizes / 2.0
        boxes_all.append(np.concatenate((xy1, xy2), axis=1))
        scores_all.append(scores)
        classes_all.append(class_ids)

    if not boxes_all:
        return []

    boxes = np.concatenate(boxes_all, axis=0)
    scores = np.concatenate(scores_all, axis=0)
    class_ids = np.concatenate(classes_all, axis=0)
    if scores.size > 500:
        top = np.argpartition(scores, -500)[-500:]
        boxes, scores, class_ids = boxes[top], scores[top], class_ids[top]

    keep_global: list[int] = []
    for class_id in np.unique(class_ids):
        indices = np.where(class_ids == class_id)[0]
        for local in nms(boxes[indices], scores[indices], NMS_IOU_THRESHOLD):
            keep_global.append(int(indices[local]))
    keep_global.sort(key=lambda index: float(scores[index]), reverse=True)

    detections: list[dict[str, object]] = []
    for index in keep_global[:MAX_DETECTIONS]:
        x1, y1, x2, y2 = boxes[index]
        x1 = float(np.clip(x1 * RGB_WIDTH / NN_WIDTH, 0, RGB_WIDTH - 1))
        y1 = float(np.clip(y1 * RGB_HEIGHT / NN_HEIGHT, 0, RGB_HEIGHT - 1))
        x2 = float(np.clip(x2 * RGB_WIDTH / NN_WIDTH, 0, RGB_WIDTH - 1))
        y2 = float(np.clip(y2 * RGB_HEIGHT / NN_HEIGHT, 0, RGB_HEIGHT - 1))
        if x2 <= x1 or y2 <= y1:
            continue
        class_id = int(class_ids[index])
        detections.append(
            {
                "class_id": class_id,
                "label": COCO_LABELS[class_id] if 0 <= class_id < len(COCO_LABELS) else str(class_id),
                "confidence": float(scores[index]),
                "bbox": [x1, y1, x2, y2],
            }
        )
    return detections


def add_spatial_data(
    detections: list[dict[str, object]],
    depth: np.ndarray,
    intrinsics: list[list[float]],
) -> None:
    fx, fy = float(intrinsics[0][0]), float(intrinsics[1][1])
    cx, cy = float(intrinsics[0][2]), float(intrinsics[1][2])
    for detection in detections:
        x1, y1, x2, y2 = [float(value) for value in detection["bbox"]]  # type: ignore[index]
        dx1 = clamp(int(x1 * DEPTH_WIDTH / RGB_WIDTH), 0, DEPTH_WIDTH - 1)
        dy1 = clamp(int(y1 * DEPTH_HEIGHT / RGB_HEIGHT), 0, DEPTH_HEIGHT - 1)
        dx2 = clamp(int(x2 * DEPTH_WIDTH / RGB_WIDTH), dx1 + 1, DEPTH_WIDTH)
        dy2 = clamp(int(y2 * DEPTH_HEIGHT / RGB_HEIGHT), dy1 + 1, DEPTH_HEIGHT)

        # Use the central 50% of the box to reduce background contamination.
        margin_x = max(1, (dx2 - dx1) // 4)
        margin_y = max(1, (dy2 - dy1) // 4)
        roi = depth[dy1 + margin_y : dy2 - margin_y, dx1 + margin_x : dx2 - margin_x]
        valid = roi[(roi >= 250) & (roi <= 10000)]
        if valid.size == 0:
            detection["x_mm"] = None
            detection["y_mm"] = None
            detection["z_mm"] = None
            continue
        z = float(np.median(valid))
        u = ((dx1 + dx2) / 2.0)
        v = ((dy1 + dy2) / 2.0)
        detection["x_mm"] = (u - cx) * z / fx
        detection["y_mm"] = (v - cy) * z / fy
        detection["z_mm"] = z


# ---------------------------- visualization generation ----------------------
def depth_heatmap(depth: np.ndarray) -> Image.Image:
    valid = depth > 0
    normalized = np.clip((depth.astype(np.float32) - 300.0) / 4700.0, 0.0, 1.0)
    # Jet-like heatmap: near=red, far=blue, invalid=black.
    x = 1.0 - normalized
    red = np.clip(1.5 - np.abs(4.0 * x - 3.0), 0.0, 1.0)
    green = np.clip(1.5 - np.abs(4.0 * x - 2.0), 0.0, 1.0)
    blue = np.clip(1.5 - np.abs(4.0 * x - 1.0), 0.0, 1.0)
    image = np.stack((red, green, blue), axis=-1)
    image[~valid] = 0.0
    return Image.fromarray((image * 255.0).astype(np.uint8), mode="RGB")


def draw_detection(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    color: tuple[int, int, int],
    full_text: bool,
) -> None:
    x1, y1, x2, y2 = box
    draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
    if not lines:
        return
    shown = lines if full_text else lines[:1]
    text = "\n".join(shown)
    bbox = draw.multiline_textbbox((x1, y1), text, font=SMALL_FONT, spacing=2)
    text_height = bbox[3] - bbox[1]
    text_width = bbox[2] - bbox[0]
    top = max(0, y1 - text_height - 6)
    draw.rectangle((x1, top, min(959, x1 + text_width + 8), top + text_height + 6), fill=(0, 0, 0))
    draw.multiline_text((x1 + 4, top + 3), text, fill=color, font=SMALL_FONT, spacing=2)


def make_visualization(
    clean_jpeg: bytes,
    depth: np.ndarray,
    detections: list[dict[str, object]],
) -> bytes:
    rgb = Image.open(io.BytesIO(clean_jpeg)).convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
    heat = depth_heatmap(depth).resize((960, 540), Image.Resampling.BILINEAR)
    rgb_draw = ImageDraw.Draw(rgb)
    heat_draw = ImageDraw.Draw(heat)

    for detection in detections:
        x1, y1, x2, y2 = [float(value) for value in detection["bbox"]]  # type: ignore[index]
        box = (
            clamp(round(x1 / 2.0), 0, 959),
            clamp(round(y1 / 2.0), 0, 539),
            clamp(round(x2 / 2.0), 0, 959),
            clamp(round(y2 / 2.0), 0, 539),
        )
        class_id = int(detection["class_id"])
        color = (
            64 + (class_id * 53) % 192,
            64 + (class_id * 97) % 192,
            64 + (class_id * 151) % 192,
        )
        confidence = 100.0 * float(detection["confidence"])
        lines = [f"{detection['label']} {confidence:.0f}%"]
        if detection.get("z_mm") is None:
            lines += ["X: n/a", "Y: n/a", "Z: n/a"]
        else:
            lines += [
                f"X: {float(detection['x_mm']):.0f} mm",
                f"Y: {float(detection['y_mm']):.0f} mm",
                f"Z: {float(detection['z_mm']):.0f} mm",
            ]
        draw_detection(heat_draw, box, lines, color, full_text=False)
        draw_detection(rgb_draw, box, lines, color, full_text=True)

    canvas = Image.new("RGB", (1920, 540), color=(0, 0, 0))
    canvas.paste(heat, (0, 0))
    canvas.paste(rgb, (960, 0))
    header = ImageDraw.Draw(canvas)
    header.rectangle((0, 0, 210, 30), fill=(0, 0, 0))
    header.text((8, 5), "DEPTH HEATMAP", font=FONT, fill=(255, 255, 255))
    header.rectangle((960, 0, 1160, 30), fill=(0, 0, 0))
    header.text((968, 5), "RGB + YOLO", font=FONT, fill=(255, 255, 255))
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=VIZ_JPEG_QUALITY, optimize=False)
    return output.getvalue()


# -------------------------------- DepthAI pipeline ---------------------------
def create_pipeline() -> dai.Pipeline:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"YOLO model missing: {MODEL_PATH}")
    pipeline = dai.Pipeline()
    version = getattr(dai.OpenVINO.Version, "VERSION_2022_1", None)
    if version is not None:
        pipeline.setOpenVINOVersion(version)

    color = pipeline.create(dai.node.ColorCamera)
    color.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    color.setResolution(dai.ColorCameraProperties.SensorResolution.THE_4_K)
    color.setFps(SOURCE_FPS)
    color.setIspScale(1, 2)
    try:
        color.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
    except Exception as error:
        print(f"[CAMERA] RGB rotation warning: {error}", flush=True)

    full = pipeline.create(dai.node.ImageManip)
    full.initialConfig.setResizeThumbnail(RGB_WIDTH, RGB_HEIGHT)
    full.initialConfig.setFrameType(dai.RawImgFrame.Type.NV12)
    full.setMaxOutputFrameSize(RGB_WIDTH * RGB_HEIGHT * 3 // 2)
    full.inputImage.setBlocking(False)
    full.inputImage.setQueueSize(1)
    color.isp.link(full.inputImage)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(SOURCE_FPS, dai.VideoEncoderProperties.Profile.MJPEG)
    try:
        encoder.setQuality(JPEG_QUALITY)
    except Exception:
        pass
    full.out.link(encoder.input)
    rgb_out = pipeline.create(dai.node.XLinkOut)
    rgb_out.setStreamName("rgb")
    encoder.bitstream.link(rgb_out.input)

    nn_manip = pipeline.create(dai.node.ImageManip)
    nn_manip.initialConfig.setResizeThumbnail(NN_WIDTH, NN_HEIGHT)
    nn_manip.initialConfig.setFrameType(dai.RawImgFrame.Type.BGR888p)
    nn_manip.setMaxOutputFrameSize(NN_WIDTH * NN_HEIGHT * 3)
    nn_manip.inputImage.setBlocking(False)
    nn_manip.inputImage.setQueueSize(1)
    color.isp.link(nn_manip.inputImage)

    network = pipeline.create(dai.node.NeuralNetwork)
    network.setBlobPath(str(MODEL_PATH))
    network.setNumInferenceThreads(2)
    network.input.setBlocking(False)
    network.input.setQueueSize(1)
    nn_manip.out.link(network.input)
    nn_out = pipeline.create(dai.node.XLinkOut)
    nn_out.setStreamName("nn")
    network.out.link(nn_out.input)

    left = pipeline.create(dai.node.MonoCamera)
    right = pipeline.create(dai.node.MonoCamera)
    left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
    right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
    left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    left.setFps(SOURCE_FPS)
    right.setFps(SOURCE_FPS)
    try:
        left.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
        right.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
    except Exception as error:
        print(f"[CAMERA] Mono rotation warning: {error}", flush=True)

    stereo = pipeline.create(dai.node.StereoDepth)
    preset = getattr(dai.node.StereoDepth.PresetMode, "DEFAULT", None)
    stereo.setDefaultProfilePreset(preset or dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setLeftRightCheck(True)
    stereo.setSubpixel(False)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setOutputSize(DEPTH_WIDTH, DEPTH_HEIGHT)
    left.out.link(stereo.left)
    right.out.link(stereo.right)
    depth_out = pipeline.create(dai.node.XLinkOut)
    depth_out.setStreamName("depth")
    stereo.depth.link(depth_out.input)
    return pipeline


def run_camera_once() -> None:
    pipeline = create_pipeline()
    print("[CAMERA] Opening OAK-D in forced USB2 mode", flush=True)
    with dai.Device(pipeline, dai.UsbSpeed.HIGH) as device:
        print(f"[CAMERA] Ready, USB={device.getUsbSpeed()}", flush=True)
        intrinsics = device.readCalibration().getCameraIntrinsics(
            dai.CameraBoardSocket.CAM_A, DEPTH_WIDTH, DEPTH_HEIGHT
        )
        rgb_queue = device.getOutputQueue("rgb", maxSize=2, blocking=False)
        depth_queue = device.getOutputQueue("depth", maxSize=2, blocking=False)
        nn_queue = device.getOutputQueue("nn", maxSize=2, blocking=False)

        latest_rgb: Optional[bytes] = None
        latest_depth: Optional[np.ndarray] = None
        latest_nn: Optional[dai.NNData] = None
        rgb_generation = 0
        depth_generation = 0
        nn_generation = 0
        last_saved_generations = (-1, -1)
        last_save = 0.0
        saved_this_session = 0
        STATE.set_camera_ready(True)

        while not STATE.stop_event.is_set():
            # Drain each queue and keep only the newest packet.
            while True:
                packet = rgb_queue.tryGet()
                if packet is None:
                    break
                data = packet.getData().tobytes()
                if data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
                    latest_rgb = data
                    rgb_generation += 1
                    STATE.touch_camera()
            while True:
                packet = depth_queue.tryGet()
                if packet is None:
                    break
                latest_depth = packet.getFrame().copy()
                depth_generation += 1
                STATE.touch_camera()
            while True:
                packet = nn_queue.tryGet()
                if packet is None:
                    break
                latest_nn = packet
                nn_generation += 1
                STATE.touch_camera()

            camera_ready, camera_age = STATE.camera_status()
            if STATE.episode.active and (not camera_ready or camera_age > MAX_CAMERA_STALE_SECONDS):
                STATE.episode.stop("camera data stale for more than 1 second")

            now = time.monotonic()
            if (
                STATE.episode.active
                and now - last_save >= SAVE_INTERVAL
                and latest_rgb is not None
                and latest_depth is not None
                and (
                    rgb_generation,
                    depth_generation,
                ) != last_saved_generations
                and rgb_generation > last_saved_generations[0]
                and depth_generation > last_saved_generations[1]
            ):
                last_save = now
                try:
                    motor_pwm = clamp(int(STATE.bridge.call("get_motor_pwm")), -255, 255)
                    servo_angle = clamp(int(STATE.bridge.call("get_servo_angle")), 0, 180)
                    with STATE.control_lock:
                        steering_command = STATE.control.steering_command
                        throttle_command = STATE.control.throttle_command
                    if STATE.episode.save(
                        latest_rgb,
                        latest_depth,
                        motor_pwm,
                        servo_angle,
                        steering_command,
                        throttle_command,
                    ):
                        last_saved_generations = (
                            rgb_generation,
                            depth_generation,
                        )
                        saved_this_session += 1
                        if saved_this_session <= 3 or saved_this_session % SAVE_HZ == 0:
                            print(
                                f"[SAMPLE] count={saved_this_session} pwm={motor_pwm} "
                                f"servo={servo_angle}",
                                flush=True,
                            )
                except Exception as error:
                    print(f"[SAMPLE] Failed: {type(error).__name__}: {error}", flush=True)

            time.sleep(0.001)

    STATE.set_camera_ready(False)


def camera_loop() -> None:
    while not STATE.stop_event.is_set():
        try:
            run_camera_once()
        except Exception as error:
            STATE.set_camera_ready(False)
            if STATE.episode.active:
                STATE.episode.stop(f"camera failure: {error}")
            print(f"[CAMERA] {type(error).__name__}: {error}; retrying in 5s", flush=True)
            STATE.stop_event.wait(5.0)


def main() -> int:
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    print("[START] McQueen single-app runtime", flush=True)
    print("[CONFIG] phone UDP=5007, LOG HTTP=8080, local recording=15 Hz", flush=True)
    print("[CONFIG] clean RGB=1920x1080, visualization=1920x540", flush=True)

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        STATE.stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    teleop = TeleopServer()
    http = HttpServerThread()
    teleop.start()
    http.start()

    try:
        camera_loop()
    finally:
        STATE.stop_event.set()
        STATE.episode.stop("app shutdown")
        teleop.join(timeout=3.0)
        http.join(timeout=3.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
