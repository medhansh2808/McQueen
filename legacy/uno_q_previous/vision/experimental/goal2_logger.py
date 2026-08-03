#!/usr/bin/env python3

import json
import math
import queue
import struct
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections import deque
from pathlib import Path
from typing import Optional

import depthai as dai
import numpy as np
from arduino.app_utils import Bridge

MODEL_PATH = Path(
    "/home/arduino/McQueen/models/"
    "yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob"
)
LAPTOP_STATUS_URL = "http://192.168.4.2:8080/status"
LAPTOP_SAMPLE_URL = "http://192.168.4.2:8080/sample"

SENSOR_FPS = 30
LOG_TARGET_HZ = 20.0
STATUS_CHECK_SECONDS = 0.4
SYNC_TOLERANCE_SECONDS = 0.09

RGB_WIDTH = 1920
RGB_HEIGHT = 1080
DEPTH_WIDTH = 640
DEPTH_HEIGHT = 360
NN_WIDTH = 512
NN_HEIGHT = 288

CONFIDENCE_THRESHOLD = 0.35
NMS_IOU_THRESHOLD = 0.45
MAX_DETECTIONS = 100

COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.logging_active = False
        self.motor_pwm = 0
        self.servo_angle = 80
        self.enqueued = 0
        self.uploaded = 0
        self.dropped = 0
        self.started_monotonic = time.monotonic()

    def set_logging(self, active: bool) -> None:
        with self.lock:
            changed = active != self.logging_active
            self.logging_active = active
        if changed:
            print(f"[STATE] Laptop logging {'ON' if active else 'OFF'}", flush=True)

    def is_logging(self) -> bool:
        with self.lock:
            return self.logging_active

    def set_controls(self, pwm: int, servo: int) -> None:
        with self.lock:
            self.motor_pwm = pwm
            self.servo_angle = servo

    def get_controls(self) -> tuple[int, int]:
        with self.lock:
            return self.motor_pwm, self.servo_angle

    def increment(self, name: str) -> None:
        with self.lock:
            setattr(self, name, getattr(self, name) + 1)

    def snapshot_counts(self) -> tuple[int, int, int, float]:
        with self.lock:
            elapsed = max(0.001, time.monotonic() - self.started_monotonic)
            return self.enqueued, self.uploaded, self.dropped, elapsed


state = SharedState()
sample_queue: queue.Queue = queue.Queue(maxsize=3)
stop_event = threading.Event()


def packet_time(packet) -> float:
    return packet.getTimestampDevice().total_seconds()


def laptop_logging_active() -> bool:
    try:
        request = urllib.request.Request(LAPTOP_STATUS_URL, method="GET")
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("logging", payload.get("recording", False)))
    except Exception:
        return False


def status_loop() -> None:
    while not stop_event.is_set():
        state.set_logging(laptop_logging_active())
        stop_event.wait(STATUS_CHECK_SECONDS)


def control_loop() -> None:
    while not stop_event.is_set():
        try:
            pwm = int(Bridge.call("get_motor_pwm"))
            servo = int(Bridge.call("get_servo_angle"))
            state.set_controls(max(-255, min(255, pwm)), max(0, min(180, servo)))
        except Exception as error:
            print(f"[BRIDGE WARNING] {error}", flush=True)
        stop_event.wait(0.05)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def encode_depth_png(depth: np.ndarray) -> bytes:
    if depth.dtype != np.uint16:
        depth = depth.astype(np.uint16, copy=False)
    height, width = depth.shape
    big_endian = depth.astype(">u2", copy=False)
    raw = b"".join(b"\x00" + big_endian[row].tobytes() for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 16, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(raw, level=1))
        + png_chunk(b"IEND", b"")
    )


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size and len(keep) < MAX_DETECTIONS:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[index], x1[rest])
        yy1 = np.maximum(y1[index], y1[rest])
        xx2 = np.minimum(x2[index], x2[rest])
        yy2 = np.minimum(y2[index], y2[rest])
        width = np.maximum(0.0, xx2 - xx1)
        height = np.maximum(0.0, yy2 - yy1)
        intersection = width * height
        union = areas[index] + areas[rest] - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        order = rest[iou <= threshold]
    return keep


def decode_yolov6(nn_packet) -> list[dict]:
    # Compiler versions may give the YOLO output layers different
    # names. Identify each head by its tensor length instead.
    expected_heads = {
        195840: (36, 64, 8),
        48960: (18, 32, 16),
        12240: (9, 16, 32),
    }

    heads = []
    discovered = []

    for layer_name in nn_packet.getAllLayerNames():
        values = np.asarray(
            nn_packet.getLayerFp16(layer_name),
            dtype=np.float32,
        )

        discovered.append(
            (layer_name, int(values.size))
        )

        specification = expected_heads.get(
            int(values.size)
        )

        if specification is not None:
            height, width, stride = specification

            heads.append(
                (
                    layer_name,
                    values,
                    height,
                    width,
                    stride,
                )
            )

    if len(heads) != 3:
        raise RuntimeError(
            "Could not identify all three YOLOv6 heads; "
            f"discovered={discovered}"
        )

    heads.sort(
        key=lambda item: item[4]
    )

    all_boxes = []
    all_scores = []
    all_classes = []

    for (
        layer_name,
        values,
        height,
        width,
        stride,
    ) in heads:

        prediction = (
            values
            .reshape(85, height, width)
            .transpose(1, 2, 0)
            .reshape(-1, 85)
        )

        objectness = prediction[:, 4]
        class_scores = prediction[:, 5:]

        class_ids = class_scores.argmax(
            axis=1
        )

        best_class_scores = class_scores[
            np.arange(class_scores.shape[0]),
            class_ids,
        ]

        scores = (
            objectness
            * best_class_scores
        )

        mask = (
            scores
            >= CONFIDENCE_THRESHOLD
        )

        if not np.any(mask):
            continue

        prediction = prediction[mask]
        scores = scores[mask]
        class_ids = class_ids[mask]

        grid_y, grid_x = np.meshgrid(
            np.arange(
                height,
                dtype=np.float32,
            ),
            np.arange(
                width,
                dtype=np.float32,
            ),
            indexing="ij",
        )

        grid = np.stack(
            (grid_x, grid_y),
            axis=-1,
        ).reshape(-1, 2)[mask]

        centres = (
            prediction[:, 0:2]
            + grid
        ) * float(stride)

        sizes = np.exp(
            np.clip(
                prediction[:, 2:4],
                -10.0,
                10.0,
            )
        ) * float(stride)

        xy1 = centres - sizes / 2.0
        xy2 = centres + sizes / 2.0

        boxes = np.concatenate(
            (xy1, xy2),
            axis=1,
        )

        all_boxes.append(boxes)
        all_scores.append(scores)
        all_classes.append(class_ids)

    if not all_boxes:
        return []

    boxes = np.concatenate(
        all_boxes,
        axis=0,
    )

    scores = np.concatenate(
        all_scores,
        axis=0,
    )

    class_ids = np.concatenate(
        all_classes,
        axis=0,
    )

    if scores.size > 500:
        top = np.argpartition(
            scores,
            -500,
        )[-500:]

        boxes = boxes[top]
        scores = scores[top]
        class_ids = class_ids[top]

    keep_indices = []

    for class_id in np.unique(
        class_ids
    ):
        class_indices = np.where(
            class_ids == class_id
        )[0]

        class_keep = nms(
            boxes[class_indices],
            scores[class_indices],
            NMS_IOU_THRESHOLD,
        )

        keep_indices.extend(
            class_indices[
                class_keep
            ].tolist()
        )

    keep_indices.sort(
        key=lambda index: float(
            scores[index]
        ),
        reverse=True,
    )

    detections = []

    scale_x = (
        RGB_WIDTH
        / NN_WIDTH
    )

    scale_y = (
        RGB_HEIGHT
        / NN_HEIGHT
    )

    for index in keep_indices[
        :MAX_DETECTIONS
    ]:
        x1, y1, x2, y2 = boxes[index]

        x1 = float(
            np.clip(
                x1 * scale_x,
                0,
                RGB_WIDTH - 1,
            )
        )

        y1 = float(
            np.clip(
                y1 * scale_y,
                0,
                RGB_HEIGHT - 1,
            )
        )

        x2 = float(
            np.clip(
                x2 * scale_x,
                0,
                RGB_WIDTH - 1,
            )
        )

        y2 = float(
            np.clip(
                y2 * scale_y,
                0,
                RGB_HEIGHT - 1,
            )
        )

        if x2 <= x1 or y2 <= y1:
            continue

        class_id = int(
            class_ids[index]
        )

        detections.append({
            "class_id": class_id,
            "label": (
                COCO_LABELS[class_id]
                if 0 <= class_id < len(
                    COCO_LABELS
                )
                else str(class_id)
            ),
            "confidence": round(
                float(scores[index]),
                5,
            ),
            "bbox_rgb": [
                round(x1, 2),
                round(y1, 2),
                round(x2, 2),
                round(y2, 2),
            ],
        })

    return detections


def add_spatial_data(detections: list[dict], depth: np.ndarray, intrinsics: list[list[float]]) -> None:
    fx, fy = float(intrinsics[0][0]), float(intrinsics[1][1])
    cx, cy = float(intrinsics[0][2]), float(intrinsics[1][2])
    sx = DEPTH_WIDTH / RGB_WIDTH
    sy = DEPTH_HEIGHT / RGB_HEIGHT

    for detection in detections:
        x1, y1, x2, y2 = detection["bbox_rgb"]
        dx1 = int(np.clip(x1 * sx, 0, DEPTH_WIDTH - 1))
        dy1 = int(np.clip(y1 * sy, 0, DEPTH_HEIGHT - 1))
        dx2 = int(np.clip(x2 * sx, dx1 + 1, DEPTH_WIDTH))
        dy2 = int(np.clip(y2 * sy, dy1 + 1, DEPTH_HEIGHT))

        width = dx2 - dx1
        height = dy2 - dy1
        roi_x1 = dx1 + int(width * 0.25)
        roi_x2 = dx2 - int(width * 0.25)
        roi_y1 = dy1 + int(height * 0.25)
        roi_y2 = dy2 - int(height * 0.25)
        if roi_x2 <= roi_x1 or roi_y2 <= roi_y1:
            roi_x1, roi_y1, roi_x2, roi_y2 = dx1, dy1, dx2, dy2

        region = depth[roi_y1:roi_y2, roi_x1:roi_x2]
        valid = region[(region >= 200) & (region <= 10000)]
        detection["bbox_depth"] = [dx1, dy1, dx2, dy2]
        if valid.size == 0:
            detection["spatial_mm"] = None
            continue

        z = float(np.median(valid))
        u = (dx1 + dx2) / 2.0
        v = (dy1 + dy2) / 2.0
        x = (u - cx) * z / fx if fx else 0.0
        y = (v - cy) * z / fy if fy else 0.0
        detection["spatial_mm"] = {
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1),
        }


def upload_sample(rgb: bytes, depth_png: bytes, metadata: dict, pwm: int, servo: int) -> bool:
    json_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    body = rgb + depth_png + json_bytes
    request = urllib.request.Request(
        LAPTOP_SAMPLE_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(body)),
            "X-RGB-Length": str(len(rgb)),
            "X-Depth-Length": str(len(depth_png)),
            "X-JSON-Length": str(len(json_bytes)),
            "X-Motor-PWM": str(pwm),
            "X-Servo-Angle": str(servo),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            response.read()
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code != 409:
            print(f"[UPLOAD HTTP ERROR] {error.code}", flush=True)
        return False
    except Exception as error:
        print(f"[UPLOAD ERROR] {error}", flush=True)
        return False


def worker_loop(intrinsics: list[list[float]]) -> None:
    while not stop_event.is_set():
        try:
            item = sample_queue.get(
                timeout=0.2
            )

        except queue.Empty:
            continue

        try:
            (
                rgb_bytes,
                depth_frame,
                nn_packet,
                device_timestamp,
                sequence,
            ) = item

            detections = []
            yolo_error = ""
            spatial_error = ""

            try:
                detections = decode_yolov6(
                    nn_packet
                )

            except Exception as error:
                yolo_error = str(error)

                print(
                    f"[YOLO WARNING] {error}",
                    flush=True,
                )

            if detections:
                try:
                    add_spatial_data(
                        detections,
                        depth_frame,
                        intrinsics,
                    )

                except Exception as error:
                    spatial_error = str(
                        error
                    )

                    print(
                        f"[SPATIAL WARNING] "
                        f"{error}",
                        flush=True,
                    )

            # Always save RGB, depth and controls.
            # A YOLO decoder problem must not empty the dataset.
            depth_png = encode_depth_png(
                depth_frame
            )

            pwm, servo = (
                state.get_controls()
            )

            (
                enqueued,
                uploaded,
                dropped,
                elapsed,
            ) = state.snapshot_counts()

            metadata = {
                "device_timestamp_seconds": round(
                    device_timestamp,
                    6,
                ),
                "sequence": int(sequence),
                "detections": detections,
                "detection_count": len(
                    detections
                ),
                "yolo_error": yolo_error,
                "spatial_error": spatial_error,
                "rgb_resolution": [
                    RGB_WIDTH,
                    RGB_HEIGHT,
                ],
                "depth_resolution": [
                    DEPTH_WIDTH,
                    DEPTH_HEIGHT,
                ],
                "model_input": [
                    NN_WIDTH,
                    NN_HEIGHT,
                ],
                "source_target_fps": (
                    SENSOR_FPS
                ),
                "logger_target_hz": (
                    LOG_TARGET_HZ
                ),
                "enqueued_samples": (
                    enqueued
                ),
                "uploaded_samples_before_this": (
                    uploaded
                ),
                "dropped_samples": (
                    dropped
                ),
                "runtime_seconds": round(
                    elapsed,
                    3,
                ),
            }

            if (
                state.is_logging()
                and upload_sample(
                    rgb_bytes,
                    depth_png,
                    metadata,
                    pwm,
                    servo,
                )
            ):
                state.increment(
                    "uploaded"
                )

                (
                    _,
                    uploaded_now,
                    _,
                    _,
                ) = state.snapshot_counts()

                if (
                    uploaded_now <= 3
                    or uploaded_now % 20 == 0
                ):
                    print(
                        f"[UPLOADED] "
                        f"samples={uploaded_now} "
                        f"pwm={pwm} "
                        f"servo={servo} "
                        f"detections="
                        f"{len(detections)}",
                        flush=True,
                    )

        except Exception as error:
            print(
                f"[WORKER ERROR] {error}",
                flush=True,
            )

        finally:
            sample_queue.task_done()


def create_pipeline() -> dai.Pipeline:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)
    pipeline = dai.Pipeline()
    version = getattr(dai.OpenVINO.Version, "VERSION_2022_1", None)
    if version is not None:
        pipeline.setOpenVINOVersion(version)

    camera = pipeline.create(dai.node.ColorCamera)
    camera.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    resolution = getattr(
        dai.ColorCameraProperties.SensorResolution,
        "THE_12_MP",
        dai.ColorCameraProperties.SensorResolution.THE_4_K,
    )
    camera.setResolution(resolution)
    camera.setFps(SENSOR_FPS)
    if resolution == getattr(dai.ColorCameraProperties.SensorResolution, "THE_12_MP", None):
        camera.setIspScale(1, 2)
    try:
        camera.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
    except Exception:
        pass

    full_view = pipeline.create(dai.node.ImageManip)
    full_view.initialConfig.setResizeThumbnail(RGB_WIDTH, RGB_HEIGHT)
    full_view.initialConfig.setFrameType(dai.RawImgFrame.Type.NV12)
    full_view.setMaxOutputFrameSize(RGB_WIDTH * RGB_HEIGHT * 3 // 2)
    full_view.inputImage.setBlocking(False)
    full_view.inputImage.setQueueSize(1)
    camera.isp.link(full_view.inputImage)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(SENSOR_FPS, dai.VideoEncoderProperties.Profile.MJPEG)
    try:
        encoder.setQuality(90)
    except Exception:
        pass
    full_view.out.link(encoder.input)

    rgb_out = pipeline.create(dai.node.XLinkOut)
    rgb_out.setStreamName("rgb_jpeg")
    encoder.bitstream.link(rgb_out.input)

    nn_manip = pipeline.create(dai.node.ImageManip)
    nn_manip.initialConfig.setResizeThumbnail(NN_WIDTH, NN_HEIGHT)
    nn_manip.initialConfig.setFrameType(dai.RawImgFrame.Type.BGR888p)
    nn_manip.setMaxOutputFrameSize(NN_WIDTH * NN_HEIGHT * 3)
    nn_manip.inputImage.setBlocking(False)
    nn_manip.inputImage.setQueueSize(1)
    camera.isp.link(nn_manip.inputImage)

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
    left.setFps(SENSOR_FPS)
    right.setFps(SENSOR_FPS)
    try:
        left.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
        right.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
    except Exception:
        pass

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


def drain(queue_object, destination: dict[int, object]) -> None:
    while True:
        packet = queue_object.tryGet()
        if packet is None:
            break
        destination[int(packet.getSequenceNum())] = packet


def find_nearest_depth(depth_history: deque, target_time: float):
    if not depth_history:
        return None
    best = min(depth_history, key=lambda item: abs(item[0] - target_time))
    return best if abs(best[0] - target_time) <= SYNC_TOLERANCE_SECONDS else None


def enqueue_sample(item) -> None:
    try:
        sample_queue.put_nowait(item)
        state.increment("enqueued")
    except queue.Full:
        try:
            sample_queue.get_nowait()
            sample_queue.task_done()
        except queue.Empty:
            pass
        state.increment("dropped")
        try:
            sample_queue.put_nowait(item)
            state.increment("enqueued")
        except queue.Full:
            state.increment("dropped")


def main() -> None:
    threading.Thread(target=status_loop, daemon=True).start()
    threading.Thread(target=control_loop, daemon=True).start()
    worker = None
    while True:
        try:
            # Build pipeline/device here so calibrated intrinsics can be passed to worker.
            pipeline = create_pipeline()
            print("[START] Goal 2 synchronized logger", flush=True)
            print("[CONFIG] RGB 1920x1080, depth 640x360, YOLOv6 512x288", flush=True)
            print(f"[CONFIG] Camera target {SENSOR_FPS} FPS; stable logging cap {LOG_TARGET_HZ:.0f} Hz", flush=True)
            print("[CONFIG] Phone camera OFF; phone LOG controls laptop session", flush=True)
            with dai.Device(pipeline, dai.UsbSpeed.HIGH) as device:
                print(f"[DEVICE] OAK-D opened, USB={device.getUsbSpeed()}", flush=True)
                calibration = device.readCalibration()
                intrinsics = calibration.getCameraIntrinsics(
                    dai.CameraBoardSocket.CAM_A, DEPTH_WIDTH, DEPTH_HEIGHT
                )
                if worker is None:
                    worker = threading.Thread(target=worker_loop, args=(intrinsics,), daemon=True)
                    worker.start()

                rgb_queue = device.getOutputQueue("rgb_jpeg", maxSize=8, blocking=False)
                depth_queue = device.getOutputQueue("depth", maxSize=8, blocking=False)
                nn_queue = device.getOutputQueue("nn", maxSize=8, blocking=False)
                rgb_pending: dict[int, object] = {}
                nn_pending: dict[int, object] = {}
                depth_history: deque = deque(maxlen=60)
                last_enqueued_time = 0.0
                last_report = time.monotonic()

                while not stop_event.is_set():
                    drain(rgb_queue, rgb_pending)
                    drain(nn_queue, nn_pending)
                    while True:
                        depth_packet = depth_queue.tryGet()
                        if depth_packet is None:
                            break
                        depth_history.append((packet_time(depth_packet), depth_packet))
                    common = sorted(set(rgb_pending).intersection(nn_pending))

                    # Most DepthAI branches preserve sequence numbers. If a
                    # firmware/encoder path does not, fall back to the nearest
                    # device timestamp so logging does not silently stay at 0 Hz.
                    if not common and rgb_pending and nn_pending:
                        rgb_sequence = min(
                            rgb_pending,
                            key=lambda key: packet_time(rgb_pending[key]),
                        )
                        rgb_timestamp = packet_time(rgb_pending[rgb_sequence])
                        nn_sequence = min(
                            nn_pending,
                            key=lambda key: abs(packet_time(nn_pending[key]) - rgb_timestamp),
                        )
                        if abs(packet_time(nn_pending[nn_sequence]) - rgb_timestamp) <= SYNC_TOLERANCE_SECONDS:
                            nn_pending[rgb_sequence] = nn_pending.pop(nn_sequence)
                            common = [rgb_sequence]

                    for sequence in common:
                        rgb_packet = rgb_pending[sequence]
                        nn_packet = nn_pending[sequence]
                        rgb_time = packet_time(rgb_packet)
                        depth_match = find_nearest_depth(depth_history, rgb_time)
                        if depth_match is None:
                            continue
                        del rgb_pending[sequence]
                        del nn_pending[sequence]
                        if not state.is_logging():
                            continue
                        now = time.monotonic()
                        if now - last_enqueued_time < 1.0 / LOG_TARGET_HZ:
                            state.increment("dropped")
                            continue
                        last_enqueued_time = now
                        _, depth_packet = depth_match
                        rgb_bytes = rgb_packet.getData().tobytes()
                        depth_frame = depth_packet.getFrame().copy()
                        if not (rgb_bytes.startswith(b"\xff\xd8") and rgb_bytes.endswith(b"\xff\xd9")):
                            state.increment("dropped")
                            continue
                        enqueue_sample((rgb_bytes, depth_frame, nn_packet, rgb_time, sequence))

                    if len(rgb_pending) > 60:
                        for key in sorted(rgb_pending)[:-30]:
                            del rgb_pending[key]
                            state.increment("dropped")
                    if len(nn_pending) > 60:
                        for key in sorted(nn_pending)[:-30]:
                            del nn_pending[key]
                            state.increment("dropped")

                    now = time.monotonic()
                    if now - last_report >= 5.0:
                        enqueued, uploaded, dropped, elapsed = state.snapshot_counts()
                        rate = uploaded / elapsed
                        print(
                            f"[RATE] uploaded={uploaded} enqueued={enqueued} dropped={dropped} "
                            f"average={rate:.2f} Hz queue={sample_queue.qsize()}",
                            flush=True,
                        )
                        last_report = now
                    time.sleep(0.001)
        except KeyboardInterrupt:
            stop_event.set()
            return
        except Exception as error:
            print(f"[FATAL] {error}", flush=True)
            print("[RETRY] Retrying in 5 seconds", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
