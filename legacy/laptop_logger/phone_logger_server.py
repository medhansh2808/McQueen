#!/usr/bin/env python3

import csv
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO, Optional

HTTP_PORT = 8080
DATASET_ROOT = Path.home() / "KachowDatasets"
MAX_SAMPLE_BYTES = 8 * 1024 * 1024


class LoggerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = False
        self.session_dir: Optional[Path] = None
        self.rgb_dir: Optional[Path] = None
        self.depth_dir: Optional[Path] = None
        self.detections_dir: Optional[Path] = None
        self.csv_file: Optional[IO[str]] = None
        self.writer = None
        self.sample_number = 0

    def _new_session_dir(self) -> Path:
        DATASET_ROOT.mkdir(parents=True, exist_ok=True)
        base = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        candidate = DATASET_ROOT / base
        suffix = 1
        while candidate.exists():
            candidate = DATASET_ROOT / f"{base}_{suffix}"
            suffix += 1
        candidate.mkdir(parents=True)
        return candidate

    def start(self) -> None:
        with self.lock:
            if self.active:
                print(f"[LOG ALREADY ACTIVE] {self.session_dir}", flush=True)
                return

            session_dir = self._new_session_dir()
            rgb_dir = session_dir / "rgb"
            depth_dir = session_dir / "depth"
            detections_dir = session_dir / "detections"
            rgb_dir.mkdir()
            depth_dir.mkdir()
            detections_dir.mkdir()

            csv_path = session_dir / "controls.csv"
            csv_file = csv_path.open("w", newline="", buffering=1)
            writer = csv.writer(csv_file)
            writer.writerow([
                "timestamp",
                "motor_pwm_sent",
                "servo_angle_sent",
                "rgb_frame",
                "depth_frame",
                "detections_file",
            ])
            csv_file.flush()

            metadata = {
                "started_at": datetime.now().isoformat(timespec="milliseconds"),
                "rgb_resolution": [1920, 1080],
                "depth_resolution": [640, 360],
                "model": "yolov6nr1_coco_512x288",
                "phone_camera": False,
                "phone_log_controls_session": True,
            }
            (session_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )

            self.active = True
            self.session_dir = session_dir
            self.rgb_dir = rgb_dir
            self.depth_dir = depth_dir
            self.detections_dir = detections_dir
            self.csv_file = csv_file
            self.writer = writer
            self.sample_number = 0
            print(f"[LOG STARTED] {session_dir}", flush=True)

    def stop(self) -> None:
        with self.lock:
            if not self.active:
                return
            session_dir = self.session_dir
            if self.csv_file is not None:
                self.csv_file.flush()
                self.csv_file.close()

            self.active = False
            self.session_dir = None
            self.rgb_dir = None
            self.depth_dir = None
            self.detections_dir = None
            self.csv_file = None
            self.writer = None
            self.sample_number = 0
            print(f"[LOG STOPPED] {session_dir}", flush=True)

    def save_sample(
        self,
        rgb_jpeg: bytes,
        depth_png: bytes,
        detections: dict,
        motor_pwm: int,
        servo_angle: int,
    ) -> tuple[bool, dict]:
        with self.lock:
            if (
                not self.active
                or self.rgb_dir is None
                or self.depth_dir is None
                or self.detections_dir is None
                or self.writer is None
                or self.csv_file is None
            ):
                return False, {"error": "logging is not active"}

            self.sample_number += 1
            stem = f"sample_{self.sample_number:06d}"
            rgb_rel = f"rgb/{stem}.jpg"
            depth_rel = f"depth/{stem}.png"
            detections_rel = f"detections/{stem}.json"

            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            detections = dict(detections)
            detections["sample_id"] = stem
            detections["laptop_timestamp"] = timestamp
            detections["motor_pwm_sent"] = motor_pwm
            detections["servo_angle_sent"] = servo_angle

            (self.rgb_dir / f"{stem}.jpg").write_bytes(rgb_jpeg)
            (self.depth_dir / f"{stem}.png").write_bytes(depth_png)
            (self.detections_dir / f"{stem}.json").write_text(
                json.dumps(detections, indent=2), encoding="utf-8"
            )

            self.writer.writerow([
                timestamp,
                motor_pwm,
                servo_angle,
                rgb_rel,
                depth_rel,
                detections_rel,
            ])
            self.csv_file.flush()

            detection_count = len(detections.get("detections", []))
            print(
                f"[SAMPLE] {stem} time={timestamp} pwm={motor_pwm} "
                f"servo={servo_angle} detections={detection_count}",
                flush=True,
            )
            return True, {
                "sample_id": stem,
                "rgb_frame": rgb_rel,
                "depth_frame": depth_rel,
                "detections_file": detections_rel,
            }


state = LoggerState()


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        return

    def read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_SAMPLE_BYTES:
            raise ValueError(f"invalid body length: {length}")
        return self.rfile.read(length) if length else b""

    def send_json(self, status_code: int = 200, extra: Optional[dict] = None) -> None:
        payload = {
            "ok": status_code < 400,
            "success": status_code < 400,
            "logging": state.active,
            "recording": state.active,
            "session": str(state.session_dir) if state.session_dir else "",
        }
        if extra:
            payload.update(extra)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-RGB-Length,X-Depth-Length,X-JSON-Length,X-Motor-PWM,X-Servo-Angle")
        self.end_headers()
        self.wfile.write(body)

    def handle_sample(self) -> None:
        try:
            rgb_length = int(self.headers.get("X-RGB-Length", "0"))
            depth_length = int(self.headers.get("X-Depth-Length", "0"))
            json_length = int(self.headers.get("X-JSON-Length", "0"))
            motor_pwm = int(self.headers.get("X-Motor-PWM", "0"))
            servo_angle = int(self.headers.get("X-Servo-Angle", "80"))
            body = self.read_body()
        except (ValueError, OSError) as error:
            self.send_json(400, {"error": str(error)})
            return

        if min(rgb_length, depth_length, json_length) <= 0:
            self.send_json(400, {"error": "missing payload lengths"})
            return
        if rgb_length + depth_length + json_length != len(body):
            self.send_json(400, {"error": "payload length mismatch"})
            return

        rgb_end = rgb_length
        depth_end = rgb_end + depth_length
        rgb_jpeg = body[:rgb_end]
        depth_png = body[rgb_end:depth_end]
        json_bytes = body[depth_end:]

        if not (rgb_jpeg.startswith(b"\xff\xd8") and rgb_jpeg.endswith(b"\xff\xd9")):
            self.send_json(400, {"error": "invalid JPEG"})
            return
        if not depth_png.startswith(b"\x89PNG\r\n\x1a\n"):
            self.send_json(400, {"error": "invalid depth PNG"})
            return
        try:
            detections = json.loads(json_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": f"invalid detections JSON: {error}"})
            return

        motor_pwm = max(-255, min(255, motor_pwm))
        servo_angle = max(0, min(180, servo_angle))
        saved, result = state.save_sample(
            rgb_jpeg, depth_png, detections, motor_pwm, servo_angle
        )
        self.send_json(200 if saved else 409, result)

    def handle_log_control(self) -> None:
        try:
            body = self.read_body()
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        body_text = body.decode("utf-8", errors="replace")
        combined = f"{self.command} {self.path} {body_text}".lower()

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

        print(f"[PHONE] {self.command} {self.path} body={body_text!r}", flush=True)
        if stop_request:
            state.stop()
        elif start_request:
            state.start()
        elif self.command in ("POST", "PUT", "PATCH"):
            state.start()
        self.send_json()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/status", "/health"):
            self.send_json()
        else:
            self.handle_log_control()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/sample":
            self.handle_sample()
        else:
            self.handle_log_control()

    def do_PUT(self):
        self.handle_log_control()

    def do_PATCH(self):
        self.handle_log_control()

    def do_DELETE(self):
        self.handle_log_control()

    def do_OPTIONS(self):
        self.send_json()


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), RequestHandler)
    print(f"[READY] McQueen dataset logger on 0.0.0.0:{HTTP_PORT}", flush=True)
    print("[READY] Phone LOG controls sessions", flush=True)
    print("[READY] UNO Q samples accepted at POST /sample", flush=True)
    try:
        server.serve_forever()
    finally:
        state.stop()
        server.server_close()


if __name__ == "__main__":
    main()
