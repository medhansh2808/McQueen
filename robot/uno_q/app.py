#!/usr/bin/env python3
"""McQueen phone teleoperation and simple RGB-only dataset recorder.

One process owns the UNO Q runtime:
- UDP 5007: phone controls
- HTTP 8080: phone LOG start/stop and status
- OAK-D: RGB capture only
- Dataset: 1280x720 JPEG + applied servo angle + applied motor PWM at 10 Hz
"""
from __future__ import annotations

import json
import math
import signal
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import depthai as dai
from arduino.app_utils import Bridge
from recorder import EpisodeWriter


PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_ROOT = PROJECT_ROOT / "datasets"

UDP_BIND = "0.0.0.0"
UDP_PORT = 5007
HTTP_BIND = "0.0.0.0"
HTTP_PORT = 8080
FAILSAFE_SECONDS = 0.300

SOURCE_FPS = 30
SAVE_HZ = 10
SAVE_INTERVAL = 1.0 / SAVE_HZ
RGB_WIDTH = 1280
RGB_HEIGHT = 720
JPEG_QUALITY = 85

MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024
MAX_CAMERA_STALE_SECONDS = 1.0
MIN_EPISODE_SECONDS = 1.0
DEFAULT_TASK = "Imitate expert driving"


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


class BridgeClient:
    """Serializes RouterBridge calls made by different runtime threads."""

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


class RuntimeState:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.bridge = BridgeClient()
        self.control = ControlState()
        self.control_lock = threading.Lock()
        self.episode = EpisodeWriter(
            dataset_root=DATASET_ROOT,
            default_task=DEFAULT_TASK,
            min_free_bytes=MIN_FREE_BYTES,
            min_episode_seconds=MIN_EPISODE_SECONDS,
            fps=SAVE_HZ,
            rgb_width=RGB_WIDTH,
            rgb_height=RGB_HEIGHT,
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
        parts = [
            part.strip()
            for part in payload.decode("utf-8", errors="replace").strip().split(",")
        ]

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
                f"{state.steering_command},"
                f"{self.steering_to_angle(state.steering_command)},"
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

    def send_json(
        self,
        status_code: int,
        extra: Optional[dict[str, object]] = None,
    ) -> None:
        camera_ready, camera_age = STATE.camera_status()
        payload: dict[str, object] = {
            "ok": status_code < 400,
            "success": status_code < 400,
            "camera_ready": (
                camera_ready and camera_age <= MAX_CAMERA_STALE_SECONDS
            ),
            "camera_age_s": (
                None if math.isinf(camera_age) else round(camera_age, 3)
            ),
            "rgb_width": RGB_WIDTH,
            "rgb_height": RGB_HEIGHT,
            "recording_fps": SAVE_HZ,
            **STATE.episode.status(),
        }

        if extra:
            payload.update(extra)

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET,POST,PUT,PATCH,DELETE,OPTIONS",
        )
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


def create_pipeline() -> dai.Pipeline:
    pipeline = dai.Pipeline()

    color = pipeline.create(dai.node.ColorCamera)
    color.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    color.setResolution(dai.ColorCameraProperties.SensorResolution.THE_4_K)
    color.setFps(SOURCE_FPS)
    color.setIspScale(1, 3)

    try:
        color.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
    except Exception as error:
        print(f"[CAMERA] RGB rotation warning: {error}", flush=True)

    resize = pipeline.create(dai.node.ImageManip)
    resize.initialConfig.setResizeThumbnail(RGB_WIDTH, RGB_HEIGHT)
    resize.initialConfig.setFrameType(dai.RawImgFrame.Type.NV12)
    resize.setMaxOutputFrameSize(RGB_WIDTH * RGB_HEIGHT * 3 // 2)
    resize.inputImage.setBlocking(False)
    resize.inputImage.setQueueSize(1)
    color.isp.link(resize.inputImage)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(
        SOURCE_FPS,
        dai.VideoEncoderProperties.Profile.MJPEG,
    )

    try:
        encoder.setQuality(JPEG_QUALITY)
    except Exception:
        pass

    resize.out.link(encoder.input)

    rgb_out = pipeline.create(dai.node.XLinkOut)
    rgb_out.setStreamName("rgb")
    encoder.bitstream.link(rgb_out.input)

    return pipeline


def run_camera_once() -> None:
    pipeline = create_pipeline()
    print("[CAMERA] Opening OAK-D in forced USB2 mode (RGB only)", flush=True)

    with dai.Device(pipeline, dai.UsbSpeed.HIGH) as device:
        print(f"[CAMERA] Ready, USB={device.getUsbSpeed()}", flush=True)
        rgb_queue = device.getOutputQueue("rgb", maxSize=2, blocking=False)

        latest_rgb: Optional[bytes] = None
        rgb_generation = 0
        last_saved_generation = -1
        last_save = 0.0
        saved_this_session = 0
        STATE.set_camera_ready(True)

        while not STATE.stop_event.is_set():
            while True:
                packet = rgb_queue.tryGet()

                if packet is None:
                    break

                data = packet.getData().tobytes()

                if data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
                    latest_rgb = data
                    rgb_generation += 1
                    STATE.touch_camera()

            camera_ready, camera_age = STATE.camera_status()

            if (
                STATE.episode.active
                and (not camera_ready or camera_age > MAX_CAMERA_STALE_SECONDS)
            ):
                STATE.episode.stop("camera data stale for more than 1 second")

            now = time.monotonic()

            if (
                STATE.episode.active
                and now - last_save >= SAVE_INTERVAL
                and latest_rgb is not None
                and rgb_generation > last_saved_generation
            ):
                last_save = now

                try:
                    motor_pwm = clamp(
                        int(STATE.bridge.call("get_motor_pwm")),
                        -255,
                        255,
                    )
                    servo_angle = clamp(
                        int(STATE.bridge.call("get_servo_angle")),
                        0,
                        180,
                    )

                    if STATE.episode.save(
                        clean_jpeg=latest_rgb,
                        motor_pwm=motor_pwm,
                        servo_angle=servo_angle,
                    ):
                        last_saved_generation = rgb_generation
                        saved_this_session += 1

                        if (
                            saved_this_session <= 3
                            or saved_this_session % SAVE_HZ == 0
                        ):
                            print(
                                f"[SAMPLE] count={saved_this_session} "
                                f"pwm={motor_pwm} servo={servo_angle}",
                                flush=True,
                            )
                except Exception as error:
                    print(
                        f"[SAMPLE] Failed: "
                        f"{type(error).__name__}: {error}",
                        flush=True,
                    )

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

            print(
                f"[CAMERA] {type(error).__name__}: {error}; retrying in 5s",
                flush=True,
            )
            STATE.stop_event.wait(5.0)


def main() -> int:
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    print("[START] McQueen RGB-only runtime", flush=True)
    print(
        f"[CONFIG] phone UDP={UDP_PORT}, LOG HTTP={HTTP_PORT}, "
        f"recording={SAVE_HZ} Hz",
        flush=True,
    )
    print(
        f"[CONFIG] RGB={RGB_WIDTH}x{RGB_HEIGHT}, "
        "depth=disabled, YOLO=disabled, preview=disabled",
        flush=True,
    )

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
