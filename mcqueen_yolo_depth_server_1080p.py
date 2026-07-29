#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import socket
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import depthai as dai
import numpy as np
from flask import Flask, Response, jsonify

MODEL_NAME = "yolov4_tiny_coco_416x416"
NN_SIZE = (416, 416)
DEPTH_SIZE = (640, 400)
LOG_RGB_SIZE = (1920, 1080)
PHONE_STREAM_SIZE = (1280, 720)
DEFAULT_CAMERA_FPS = 5.0
DEFAULT_SAVE_FPS = 5.0
OAK_MJPEG_QUALITY = 95
PHONE_JPEG_QUALITY = 93
RAW_JPEG_QUALITY = 98
ANNOTATED_JPEG_QUALITY = 96

COCO_LABELS = [
    "person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa",
    "pottedplant", "bed", "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def safe_int(value: str) -> int | None:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError, AttributeError):
        return None


def clamp(value: int, low: int = -1000, high: int = 1000) -> int:
    return max(low, min(high, value))


@dataclass
class SharedState:
    condition: threading.Condition = field(default_factory=threading.Condition)
    jpeg: bytes | None = None
    frame_number: int = 0
    camera_ready: bool = False
    logging: bool = False
    session_dir: str = ""
    saved_frames: int = 0
    detections_total: int = 0
    measured_fps: float = 0.0
    usb_speed: str = ""
    last_error: str = ""

    control_lock: threading.Lock = field(default_factory=threading.Lock)
    steering: int | None = None
    throttle: int | None = None
    armed: str = ""
    mode: str = ""
    control_timestamp_ns: int = 0
    raw_packet: str = ""
    packet_fields: list[str] = field(default_factory=list)
    packet_source: str = ""


class DatasetWriter:
    def __init__(self, root: Path, save_fps: float, camera_fps: float, model_path: Path) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session = root / f"session_{stamp}"
        self.raw_dir = self.session / "rgb_raw_upright"
        self.annotated_dir = self.session / "rgb_yolo_depth_upright"
        self.depth_dir = self.session / "depth_mm_upright"
        for directory in (self.raw_dir, self.annotated_dir, self.depth_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.csv_file = (self.session / "controls.csv").open("w", newline="", buffering=1)
        self.csv_writer = csv.DictWriter(
            self.csv_file,
            fieldnames=[
                "frame_id",
                "frame_timestamp_ns",
                "host_time_utc",
                "control_timestamp_ns",
                "command_age_ms",
                "steering_sent",
                "throttle_sent",
                "armed",
                "mode",
                "raw_packet",
                "rgb_raw_path",
                "rgb_annotated_path",
                "depth_mm_path",
                "detection_count",
            ],
        )
        self.csv_writer.writeheader()
        self.det_file = (self.session / "detections.jsonl").open("w", buffering=1)
        (self.session / "metadata.json").write_text(
            json.dumps(
                {
                    "created_utc": utc_iso(),
                    "camera": "OAK-D Pro",
                    "depthai_version": dai.__version__,
                    "forced_usb_speed": "HIGH / USB2",
                    "model": MODEL_NAME,
                    "model_blob": str(model_path),
                    "nn_size": list(NN_SIZE),
                    "rgb_log_size": list(LOG_RGB_SIZE),
                    "phone_stream_size": list(PHONE_STREAM_SIZE),
                    "depth_size": list(DEPTH_SIZE),
                    "camera_fps": camera_fps,
                    "save_fps": save_fps,
                    "rotation_degrees": 180,
                    "depth_units": "millimetres, uint16 PNG",
                    "coordinates": {
                        "x_mm": "upright-display horizontal; right positive",
                        "y_mm": "upright-display vertical; down positive",
                        "z_mm": "forward distance from camera",
                    },
                },
                indent=2,
            )
        )
        self.lock = threading.Lock()

    def close(self) -> None:
        with self.lock:
            self.csv_file.close()
            self.det_file.close()

    def write(
        self,
        frame_id: int,
        frame_timestamp_ns: int,
        raw_upright: np.ndarray,
        annotated_upright: np.ndarray,
        depth_upright: np.ndarray,
        detections: list[dict[str, Any]],
        control: dict[str, Any],
    ) -> None:
        name = f"frame_{frame_id:08d}"
        raw_path = self.raw_dir / f"{name}.jpg"
        ann_path = self.annotated_dir / f"{name}.jpg"
        depth_path = self.depth_dir / f"{name}.png"

        if not cv2.imwrite(str(raw_path), raw_upright, [cv2.IMWRITE_JPEG_QUALITY, RAW_JPEG_QUALITY]):
            raise RuntimeError(f"Failed to save {raw_path}")
        if not cv2.imwrite(str(ann_path), annotated_upright, [cv2.IMWRITE_JPEG_QUALITY, ANNOTATED_JPEG_QUALITY]):
            raise RuntimeError(f"Failed to save {ann_path}")
        if not cv2.imwrite(str(depth_path), depth_upright):
            raise RuntimeError(f"Failed to save {depth_path}")

        control_ns = int(control.get("control_timestamp_ns") or 0)
        age_ms = "" if control_ns <= 0 else round((frame_timestamp_ns - control_ns) / 1_000_000, 3)
        det_record = {
            "frame_id": frame_id,
            "frame_timestamp_ns": frame_timestamp_ns,
            "host_time_utc": utc_iso(),
            "detections": detections,
        }

        with self.lock:
            self.csv_writer.writerow(
                {
                    "frame_id": frame_id,
                    "frame_timestamp_ns": frame_timestamp_ns,
                    "host_time_utc": utc_iso(),
                    "control_timestamp_ns": control_ns or "",
                    "command_age_ms": age_ms,
                    "steering_sent": control.get("steering", ""),
                    "throttle_sent": control.get("throttle", ""),
                    "armed": control.get("armed", ""),
                    "mode": control.get("mode", ""),
                    "raw_packet": control.get("raw_packet", ""),
                    "rgb_raw_path": str(raw_path.relative_to(self.session)),
                    "rgb_annotated_path": str(ann_path.relative_to(self.session)),
                    "depth_mm_path": str(depth_path.relative_to(self.session)),
                    "detection_count": len(detections),
                }
            )
            self.det_file.write(json.dumps(det_record, separators=(",", ":")) + "\n")


def parse_named_value(text: str, names: tuple[str, ...]) -> int | None:
    joined = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?i)(?:{joined})\s*[:=]\s*(-?\d+)", text)
    return safe_int(match.group(1)) if match else None


def parse_control_packet(payload: bytes, steer_index: int | None, throttle_index: int | None) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace").strip()
    result: dict[str, Any] = {
        "raw_packet": text,
        "fields": [],
        "steering": None,
        "throttle": None,
        "armed": "",
        "mode": "",
    }
    if not text:
        return result

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None

    if isinstance(obj, dict):
        for key in ("steering", "steer", "servo", "servo_sent", "steering_sent"):
            if key in obj:
                result["steering"] = safe_int(str(obj[key]))
                break
        for key in ("throttle", "speed", "motor", "throttle_sent", "motor_sent"):
            if key in obj:
                result["throttle"] = safe_int(str(obj[key]))
                break
        result["armed"] = str(obj.get("armed", ""))
        result["mode"] = str(obj.get("mode", ""))
        result["fields"] = [f"{key}={value}" for key, value in obj.items()]
        return result

    fields = [part.strip() for part in re.split(r"[,;|]", text)]
    result["fields"] = fields
    result["steering"] = parse_named_value(text, ("steering", "steer", "servo"))
    result["throttle"] = parse_named_value(text, ("throttle", "motor", "speed"))

    if steer_index is not None and 0 <= steer_index < len(fields):
        parsed = safe_int(fields[steer_index])
        if parsed is not None:
            result["steering"] = parsed
    if throttle_index is not None and 0 <= throttle_index < len(fields):
        parsed = safe_int(fields[throttle_index])
        if parsed is not None:
            result["throttle"] = parsed

    if len(fields) == 3 and fields[0].upper() == "C":
        if result["steering"] is None:
            result["steering"] = safe_int(fields[1])
        if result["throttle"] is None:
            result["throttle"] = safe_int(fields[2])

    for token in fields:
        upper = token.upper()
        if upper in {"ARMED", "DISARMED"}:
            result["armed"] = upper
        if upper in {"JOYSTICK", "RC", "RC_SLIDERS", "AUTO", "MANUAL"}:
            result["mode"] = upper

    if result["steering"] is not None:
        result["steering"] = clamp(result["steering"])
    if result["throttle"] is not None:
        result["throttle"] = clamp(result["throttle"])
    return result


def udp_listener(
    state: SharedState,
    host: str,
    port: int,
    steer_index: int | None,
    throttle_index: int | None,
    inspect: bool,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    print(f"[UDP] Listening for phone control/log copy on {host}:{port}", flush=True)

    last_printed = ""
    while True:
        payload, address = sock.recvfrom(4096)
        parsed = parse_control_packet(payload, steer_index, throttle_index)
        tokens = {token.strip().upper() for token in parsed["fields"]}

        with state.control_lock:
            state.raw_packet = parsed["raw_packet"]
            state.packet_fields = parsed["fields"]
            state.packet_source = f"{address[0]}:{address[1]}"
            state.control_timestamp_ns = time.time_ns()
            if parsed["steering"] is not None:
                state.steering = parsed["steering"]
            if parsed["throttle"] is not None:
                state.throttle = parsed["throttle"]
            if parsed["armed"]:
                state.armed = parsed["armed"]
            if parsed["mode"]:
                state.mode = parsed["mode"]

        if tokens.intersection({"LOG", "START", "RECORD", "TAKE"}):
            state.logging = True
            print("[DATA] Logging enabled by phone packet", flush=True)
        if tokens.intersection({"STOP", "END", "STOP_LOG", "STOPLOG"}):
            state.logging = False
            print("[DATA] Logging disabled by phone packet", flush=True)

        if inspect and parsed["raw_packet"] != last_printed:
            last_printed = parsed["raw_packet"]
            print(
                f"[UDP] {address[0]}:{address[1]} fields={parsed['fields']} "
                f"steer={parsed['steering']} throttle={parsed['throttle']}",
                flush=True,
            )


def snapshot_control(state: SharedState) -> dict[str, Any]:
    with state.control_lock:
        return {
            "steering": state.steering,
            "throttle": state.throttle,
            "armed": state.armed,
            "mode": state.mode,
            "control_timestamp_ns": state.control_timestamp_ns,
            "raw_packet": state.raw_packet,
            "packet_fields": list(state.packet_fields),
            "packet_source": state.packet_source,
        }


def colourise_depth(depth_mm: np.ndarray) -> np.ndarray:
    valid = depth_mm[depth_mm > 0]
    if valid.size == 0:
        grey = np.zeros(depth_mm.shape, dtype=np.uint8)
    else:
        near = float(np.percentile(valid, 2))
        far = float(np.percentile(valid, 98))
        if far <= near:
            far = near + 1.0
        clipped = np.clip(depth_mm.astype(np.float32), near, far)
        grey = (255.0 - (clipped - near) * (255.0 / (far - near))).astype(np.uint8)
        grey[depth_mm == 0] = 0
    return cv2.applyColorMap(grey, cv2.COLORMAP_TURBO)


def upright_bbox(det: Any, width: int, height: int) -> tuple[int, int, int, int, list[float]]:
    ux1 = max(0.0, min(1.0, 1.0 - float(det.xmax)))
    uy1 = max(0.0, min(1.0, 1.0 - float(det.ymax)))
    ux2 = max(0.0, min(1.0, 1.0 - float(det.xmin)))
    uy2 = max(0.0, min(1.0, 1.0 - float(det.ymin)))
    x1 = int(round(ux1 * width))
    y1 = int(round(uy1 * height))
    x2 = int(round(ux2 * width))
    y2 = int(round(uy2 * height))
    return x1, y1, x2, y2, [ux1, uy1, ux2, uy2]


def annotate(
    raw_upright: np.ndarray,
    depth_upright: np.ndarray,
    detections: list[Any],
    control: dict[str, Any],
    fps: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    annotated = raw_upright.copy()
    height, width = annotated.shape[:2]
    scale = max(1.0, width / 1280.0)
    line_thickness = max(2, int(round(2 * scale)))
    text_scale = 0.48 * scale
    small_text_scale = 0.40 * scale
    text_thickness = max(1, int(round(scale)))

    depth_colour = colourise_depth(depth_upright)
    depth_colour = cv2.resize(depth_colour, (width, height), interpolation=cv2.INTER_NEAREST)

    records: list[dict[str, Any]] = []
    for det in detections:
        x1, y1, x2, y2, bbox_norm = upright_bbox(det, width, height)
        label_id = int(getattr(det, "label", -1))
        label = COCO_LABELS[label_id] if 0 <= label_id < len(COCO_LABELS) else str(label_id)
        confidence = float(det.confidence)

        coords = det.spatialCoordinates
        x_mm = -float(coords.x)
        y_mm = -float(coords.y)
        z_mm = float(coords.z)
        distance_mm = math.sqrt(x_mm * x_mm + y_mm * y_mm + z_mm * z_mm)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 255, 255), line_thickness)
        cv2.rectangle(depth_colour, (x1, y1), (x2, y2), (255, 255, 255), max(1, line_thickness // 2))

        title = f"{label} {confidence * 100:.0f}% Z:{z_mm / 1000.0:.2f}m"
        xyz = f"X:{x_mm / 1000.0:+.2f} Y:{y_mm / 1000.0:+.2f} D:{distance_mm / 1000.0:.2f}m"
        text_y = max(int(28 * scale), y1 - int(8 * scale))
        outline = max(3, text_thickness + 3)
        cv2.putText(annotated, title, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, text_scale, (0, 0, 0), outline, cv2.LINE_AA)
        cv2.putText(annotated, title, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, text_scale, (255, 255, 255), text_thickness, cv2.LINE_AA)
        line2_y = min(height - int(60 * scale), text_y + int(25 * scale))
        cv2.putText(annotated, xyz, (x1, line2_y), cv2.FONT_HERSHEY_SIMPLEX, small_text_scale, (0, 0, 0), outline, cv2.LINE_AA)
        cv2.putText(annotated, xyz, (x1, line2_y), cv2.FONT_HERSHEY_SIMPLEX, small_text_scale, (255, 255, 255), text_thickness, cv2.LINE_AA)

        records.append(
            {
                "label": label,
                "label_id": label_id,
                "confidence": confidence,
                "bbox_upright_normalized": bbox_norm,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "z_mm": z_mm,
                "distance_mm": distance_mm,
            }
        )

    inset_w = min(width // 3, 640)
    inset_h = max(1, int(round(inset_w * DEPTH_SIZE[1] / DEPTH_SIZE[0])))
    inset = cv2.resize(depth_colour, (inset_w, inset_h), interpolation=cv2.INTER_AREA)
    margin = max(10, int(10 * scale))
    x0 = width - inset_w - margin
    y0 = margin
    annotated[y0 : y0 + inset_h, x0 : x0 + inset_w] = inset
    cv2.rectangle(annotated, (x0, y0), (x0 + inset_w, y0 + inset_h), (255, 255, 255), line_thickness)
    cv2.putText(annotated, "DEPTH", (x0 + margin, y0 + int(27 * scale)), cv2.FONT_HERSHEY_SIMPLEX, text_scale, (255, 255, 255), text_thickness, cv2.LINE_AA)

    steer = control.get("steering")
    throttle = control.get("throttle")
    status = (
        f"YOLO+DEPTH {fps:4.1f}fps  "
        f"STEER:{'?' if steer is None else f'{steer:+d}'}  "
        f"THR:{'?' if throttle is None else f'{throttle:+d}'}"
    )
    bar_h = max(38, int(42 * scale))
    cv2.rectangle(annotated, (0, height - bar_h), (width, height), (0, 0, 0), -1)
    cv2.putText(annotated, status, (margin, height - int(12 * scale)), cv2.FONT_HERSHEY_SIMPLEX, text_scale, (255, 255, 255), text_thickness, cv2.LINE_AA)
    return annotated, records

def make_app(state: SharedState) -> Flask:
    app = Flask(__name__)

    def mjpeg_stream():
        last_frame = -1
        while True:
            with state.condition:
                state.condition.wait_for(
                    lambda: state.jpeg is not None and state.frame_number != last_frame,
                    timeout=2.0,
                )
                jpeg = state.jpeg
                last_frame = state.frame_number
            if jpeg is None:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    @app.get("/")
    @app.get("/stream.mjpg")
    def stream():
        return Response(mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/health")
    def health():
        control = snapshot_control(state)
        return jsonify(
            {
                "ok": not bool(state.last_error),
                "camera_ready": state.camera_ready,
                "depthai_version": dai.__version__,
                "usb_speed": state.usb_speed,
                "model": MODEL_NAME,
                "rgb_log_size": list(LOG_RGB_SIZE),
                "phone_stream_size": list(PHONE_STREAM_SIZE),
                "frame_number": state.frame_number,
                "measured_fps": round(state.measured_fps, 2),
                "saved_frames": state.saved_frames,
                "detections_total": state.detections_total,
                "logging": state.logging,
                "session_dir": state.session_dir,
                "steering": control["steering"],
                "throttle": control["throttle"],
                "armed": control["armed"],
                "mode": control["mode"],
                "last_udp_packet": control["raw_packet"],
                "udp_fields": control["packet_fields"],
                "udp_source": control["packet_source"],
                "last_error": state.last_error,
            }
        )

    @app.post("/logging/start")
    def logging_start():
        state.logging = True
        return jsonify({"logging": True})

    @app.post("/logging/stop")
    def logging_stop():
        state.logging = False
        return jsonify({"logging": False})

    return app


def build_pipeline(model_path: Path, camera_fps: float, confidence: float) -> dai.Pipeline:
    pipeline = dai.Pipeline()

    cam_rgb = pipeline.create(dai.node.ColorCamera)
    cam_rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam_rgb.setVideoSize(*LOG_RGB_SIZE)
    cam_rgb.setPreviewSize(*NN_SIZE)
    cam_rgb.setPreviewKeepAspectRatio(False)
    cam_rgb.setInterleaved(False)
    cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    cam_rgb.setFps(camera_fps)

    mono_left = pipeline.create(dai.node.MonoCamera)
    mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
    mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    mono_left.setFps(camera_fps)

    mono_right = pipeline.create(dai.node.MonoCamera)
    mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
    mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    mono_right.setFps(camera_fps)

    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setOutputSize(*DEPTH_SIZE)
    stereo.setLeftRightCheck(True)
    stereo.setExtendedDisparity(True)
    stereo.setSubpixel(False)

    spatial = pipeline.create(dai.node.YoloSpatialDetectionNetwork)
    spatial.setBlobPath(str(model_path))
    spatial.setConfidenceThreshold(confidence)
    spatial.input.setBlocking(False)
    spatial.setBoundingBoxScaleFactor(0.5)
    spatial.setDepthLowerThreshold(100)
    spatial.setDepthUpperThreshold(10000)
    spatial.setNumClasses(80)
    spatial.setCoordinateSize(4)
    spatial.setAnchors([10, 14, 23, 27, 37, 58, 81, 82, 135, 169, 344, 319])
    spatial.setAnchorMasks({"side26": [1, 2, 3], "side13": [3, 4, 5]})
    spatial.setIouThreshold(0.5)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(camera_fps, dai.VideoEncoderProperties.Profile.MJPEG)
    encoder.setQuality(OAK_MJPEG_QUALITY)
    encoder.input.setBlocking(False)

    xout_highres = pipeline.create(dai.node.XLinkOut)
    xout_highres.setStreamName("highres")
    xout_det = pipeline.create(dai.node.XLinkOut)
    xout_det.setStreamName("detections")
    xout_depth = pipeline.create(dai.node.XLinkOut)
    xout_depth.setStreamName("depth")

    mono_left.out.link(stereo.left)
    mono_right.out.link(stereo.right)
    cam_rgb.preview.link(spatial.input)
    cam_rgb.video.link(encoder.input)
    stereo.depth.link(spatial.inputDepth)
    encoder.bitstream.link(xout_highres.input)
    spatial.out.link(xout_det.input)
    spatial.passthroughDepth.link(xout_depth.input)
    return pipeline

def run_server(app: Flask, port: int) -> None:
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False, use_reloader=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=Path(__file__).with_name("models") / f"{MODEL_NAME}.blob")
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--udp-port", type=int, default=5008)
    parser.add_argument("--dataset-root", type=Path, default=Path.home() / "KachowDatasets")
    parser.add_argument("--steer-index", type=int, default=None)
    parser.add_argument("--throttle-index", type=int, default=None)
    parser.add_argument("--inspect-udp", action="store_true")
    parser.add_argument("--auto-log", action="store_true")
    parser.add_argument("--camera-fps", type=float, default=DEFAULT_CAMERA_FPS)
    parser.add_argument("--save-fps", type=float, default=DEFAULT_SAVE_FPS)
    parser.add_argument("--confidence", type=float, default=0.5)
    args = parser.parse_args()

    model_path = args.model.expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(
            f"YOLO blob not found: {model_path}\nRun ./prepare_model.sh while connected to internet."
        )
    if args.camera_fps <= 0 or args.save_fps <= 0:
        raise ValueError("camera-fps and save-fps must be positive")

    state = SharedState(logging=args.auto_log)
    writer = DatasetWriter(args.dataset_root, args.save_fps, args.camera_fps, model_path)
    state.session_dir = str(writer.session)

    threading.Thread(
        target=udp_listener,
        args=(state, "0.0.0.0", args.udp_port, args.steer_index, args.throttle_index, args.inspect_udp),
        daemon=True,
    ).start()
    app = make_app(state)
    threading.Thread(target=run_server, args=(app, args.http_port), daemon=True).start()

    print(f"[HTTP] Phone stream: http://<LAPTOP_IP>:{args.http_port}/", flush=True)
    print(f"[HTTP] Health:       http://127.0.0.1:{args.http_port}/health", flush=True)
    print(f"[DATA] Session:      {writer.session}", flush=True)
    print(f"[DATA] Logging:      {'ON' if state.logging else 'OFF; use phone LOG or /logging/start'}", flush=True)
    print(f"[MODEL] {MODEL_NAME}: {model_path}", flush=True)
    print("[OAK] Forced mode:   USB2 / dai.UsbSpeed.HIGH", flush=True)
    print(f"[VIDEO] 4K logs:     {LOG_RGB_SIZE[0]}x{LOG_RGB_SIZE[1]} @ {args.camera_fps:g} fps", flush=True)
    print(f"[VIDEO] Phone feed:  {PHONE_STREAM_SIZE[0]}x{PHONE_STREAM_SIZE[1]} JPEG Q{PHONE_JPEG_QUALITY}", flush=True)

    frame_id = 0
    last_save = 0.0
    fps_start = time.monotonic()
    fps_counter = 0

    try:
        pipeline = build_pipeline(model_path, args.camera_fps, args.confidence)
        with dai.Device(pipeline, maxUsbSpeed=dai.UsbSpeed.HIGH) as device:
            state.usb_speed = str(device.getUsbSpeed())
            state.camera_ready = True
            print(f"[OAK] Pipeline started. USB speed: {state.usb_speed}", flush=True)

            highres_queue = device.getOutputQueue("highres", maxSize=1, blocking=True)
            det_queue = device.getOutputQueue("detections", maxSize=2, blocking=True)
            depth_queue = device.getOutputQueue("depth", maxSize=2, blocking=True)

            while True:
                highres_msg = highres_queue.get()
                det_msg = det_queue.get()
                depth_msg = depth_queue.get()

                mjpeg = np.asarray(highres_msg.getData(), dtype=np.uint8)
                raw = cv2.imdecode(mjpeg, cv2.IMREAD_COLOR)
                depth = depth_msg.getFrame()
                if raw is None or raw.size == 0:
                    raise RuntimeError("Received empty 4K MJPEG frame")
                if depth is None or depth.size == 0:
                    raise RuntimeError("Received empty depth frame")

                raw_upright = cv2.rotate(raw, cv2.ROTATE_180)
                depth_upright = cv2.rotate(depth, cv2.ROTATE_180)
                control = snapshot_control(state)

                fps_counter += 1
                now = time.monotonic()
                elapsed = now - fps_start
                if elapsed >= 1.0:
                    state.measured_fps = fps_counter / elapsed
                    fps_counter = 0
                    fps_start = now

                annotated, records = annotate(
                    raw_upright,
                    depth_upright,
                    det_msg.detections,
                    control,
                    state.measured_fps,
                )
                phone_frame = cv2.resize(annotated, PHONE_STREAM_SIZE, interpolation=cv2.INTER_AREA)
                ok, encoded = cv2.imencode(
                    ".jpg",
                    phone_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, PHONE_JPEG_QUALITY],
                )
                if not ok:
                    raise RuntimeError("JPEG encoding failed")

                frame_id += 1
                with state.condition:
                    state.jpeg = encoded.tobytes()
                    state.frame_number = frame_id
                    state.detections_total += len(records)
                    state.condition.notify_all()

                if state.logging and (now - last_save) >= (1.0 / args.save_fps):
                    frame_timestamp_ns = time.time_ns()
                    writer.write(
                        frame_id,
                        frame_timestamp_ns,
                        raw_upright,
                        annotated,
                        depth_upright,
                        records,
                        control,
                    )
                    state.saved_frames += 1
                    last_save = now

    except KeyboardInterrupt:
        print("\n[STOP] Ctrl+C received", flush=True)
    except Exception as exc:
        state.last_error = f"{type(exc).__name__}: {exc}"
        print(f"[ERROR] {state.last_error}", flush=True)
        traceback.print_exc()
        return 1
    finally:
        state.camera_ready = False
        writer.close()
        print(f"[DATA] Closed session: {writer.session}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
