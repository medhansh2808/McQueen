#!/usr/bin/env python3

import cv2
import json
import queue
import select
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JETSON_IP = "192.168.55.1"
PORT = 5007

CAMERA_DEVICE = 0
RECORD_FPS = 10
TASK = "Imitate expert driving"
HTTP_PORT = 8080

# ---------- Actuator mapping ----------

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def steering_to_servo_angle(raw_steering):
    # Must exactly match the current Jetson mapping.
    steering = -clamp(int(raw_steering), -1000, 1000)

    if steering < 0:
        return 45 + ((steering + 1000) * (90 - 45)) // 1000

    return 90 + (steering * (115 - 90)) // 1000

def throttle_to_pwm(raw_throttle, enabled):
    if not enabled:
        return 0

    throttle = clamp(int(raw_throttle), -1000, 1000)
    return int(round(throttle * 255.0 / 1000.0))

# ---------- Camera ----------

subprocess.run([
    "v4l2-ctl", "-d", "/dev/video0",
    "--set-ctrl=power_line_frequency=1",
    "--set-ctrl=auto_exposure=1",
    "--set-ctrl=exposure_time_absolute=200",
    "--set-ctrl=gain=0",
    "--set-ctrl=backlight_compensation=0",
], check=False)

cap = cv2.VideoCapture(CAMERA_DEVICE, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    raise RuntimeError("Could not open /dev/video0")

camera_lock = threading.Lock()
latest_frame = None
latest_frame_timestamp = None
shutdown = threading.Event()

def camera_worker():
    global latest_frame, latest_frame_timestamp

    while not shutdown.is_set():
        ok, frame = cap.read()

        if ok:
            with camera_lock:
                latest_frame = frame
                latest_frame_timestamp = time.time()

camera_thread = threading.Thread(target=camera_worker, daemon=True)
camera_thread.start()

# ---------- Network ----------

phone_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
phone_sock.bind(("0.0.0.0", PORT))

jetson_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
jetson_sock.connect((JETSON_IP, PORT))

phone_addr = None

raw_steering = 0
raw_throttle = 0
motor_enabled = False

servo_angle = 90
motor_pwm = 0

# ---------- Session ----------

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
session_dir = Path("data/spool") / ("session_" + stamp)
session_dir.mkdir(parents=True, exist_ok=True)

episode_index = 0
recording = False
frames_file = None
episode_dir = None
frame_index = 0
next_save_time = None
last_camera_timestamp = None

commands = queue.Queue()

def command_worker():
    while not shutdown.is_set():
        try:
            command = input(
                "\n[r] start episode   [s] stop episode   [q] quit\n> "
            ).strip().lower()
        except EOFError:
            command = "q"

        commands.put(command)

        if command == "q":
            return

if sys.stdin.isatty():
    threading.Thread(target=command_worker, daemon=True).start()
    print("Terminal controls enabled: r / s / q")
else:
    print("HEADLESS MODE: phone LOG controls episodes")

def write_metadata(status):
    metadata = {
        "schema_version": "mcqueen-rgb-spool-v1",
        "status": status,
        "task": TASK,
        "frame_count": frame_index,
        "recording_fps": RECORD_FPS,
        "camera": {
            "device": "/dev/video0",
            "width": 1280,
            "height": 720,
        },
        "action": {
            "servo_angle_center_deg": 90,
            "servo_angle_range_deg": [45, 115],
            "motor_pwm_range": [-255, 255],
        },
    }

    with (episode_dir / "episode.json").open("w") as f:
        json.dump(metadata, f, indent=2)

def start_episode():
    global recording
    global frames_file
    global episode_dir
    global frame_index
    global next_save_time
    global last_camera_timestamp

    if recording:
        print("Already recording.")
        return

    episode_dir = session_dir / ("episode_%06d" % episode_index)
    rgb_dir = episode_dir / "rgb"
    rgb_dir.mkdir(parents=True, exist_ok=True)

    frame_index = 0
    last_camera_timestamp = None

    frames_file = (episode_dir / "frames.jsonl").open(
        "w", buffering=1
    )

    write_metadata("recording")

    recording = True
    next_save_time = time.monotonic()

    print()
    print("========================================")
    print("RECORDING:", episode_dir.name)
    print("========================================")

def stop_episode(status="completed"):
    global recording
    global frames_file
    global episode_index

    if not recording:
        print("No episode currently recording.")
        return

    recording = False

    if frames_file:
        frames_file.close()
        frames_file = None

    write_metadata(status)

    print()
    print("========================================")
    print("EPISODE SAVED")
    print("Frames :", frame_index)
    print("Path   :", episode_dir)
    print("Status :", status)
    print("========================================")

    episode_index += 1


# ---------- Phone LOG HTTP control ----------

class LogControlHandler(BaseHTTPRequestHandler):

    def log_message(self, format_string, *args):
        return

    def send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/status"):
            self.send_json(
                200,
                {
                    "ok": True,
                    "logging": recording,
                    "recording": recording,
                    "session": session_dir.name,
                    "episode": (
                        episode_dir.name
                        if episode_dir is not None
                        else ""
                    ),
                    "frame_index": frame_index,
                },
            )
            return

        self.send_json(404, {"ok": False, "detail": "not found"})

    def do_POST(self):
        if self.path == "/api/log/start":
            action = "r"
        elif self.path == "/api/log/stop":
            action = "s"
        else:
            self.send_json(
                404,
                {"ok": False, "detail": "unknown endpoint"},
            )
            return

        request = {
            "action": action,
            "event": threading.Event(),
            "result": None,
        }

        commands.put(request)

        if not request["event"].wait(timeout=3.0):
            self.send_json(
                504,
                {"ok": False, "detail": "recorder timeout"},
            )
            return

        self.send_json(200, request["result"])


try:
    http_server = ThreadingHTTPServer(
        ("0.0.0.0", HTTP_PORT),
        LogControlHandler,
    )
except OSError as error:
    raise RuntimeError(
        "Could not start HTTP logger on port %d: %s"
        % (HTTP_PORT, error)
    )

http_thread = threading.Thread(
    target=http_server.serve_forever,
    daemon=True,
)
http_thread.start()


print()
print("========================================")
print(" McQueen Dataset Recorder")
print("========================================")
print("Phone control     : 192.168.0.134:5007")
print("Phone LOG         : http://192.168.0.134:8080")
print("Jetson            : 192.168.55.1:5007")
print("Camera            : /dev/video0")
print("Recording         : 1280x720 @ 10 FPS")
print("Servo labels      : 45..115 deg, center 90")
print("Motor labels      : -255..255")
print("Session           :", session_dir)
print("========================================")

try:
    while True:
        # Terminal commands
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                break

            if isinstance(command, dict):
                action = command["action"]

                if action == "r":
                    if recording:
                        detail = "episode already recording"
                    else:
                        start_episode()
                        detail = "episode started"

                elif action == "s":
                    if recording:
                        stop_episode("completed")
                        detail = "episode stopped"
                    else:
                        detail = "no episode recording"

                else:
                    detail = "unknown action"

                command["result"] = {
                    "ok": True,
                    "detail": detail,
                    "logging": recording,
                    "recording": recording,
                    "session": session_dir.name,
                }
                command["event"].set()

            elif command == "r":
                start_episode()

            elif command == "s":
                stop_episode("completed")

            elif command == "q":
                if recording:
                    stop_episode("completed")
                raise KeyboardInterrupt

        # Phone <-> Jetson proxy
        readable, _, _ = select.select(
            [phone_sock, jetson_sock], [], [], 0.005
        )

        for sock in readable:
            if sock is phone_sock:
                data, addr = phone_sock.recvfrom(4096)
                phone_addr = addr

                jetson_sock.send(data)

                text = data.decode("utf-8", errors="ignore").strip()

                if text.startswith("C,"):
                    parts = text.split(",")

                    if len(parts) >= 8:
                        try:
                            raw_steering = int(parts[5])
                            raw_throttle = int(parts[6])
                            motor_enabled = bool(int(parts[7]))

                            servo_angle = steering_to_servo_angle(
                                raw_steering
                            )

                            motor_pwm = throttle_to_pwm(
                                raw_throttle,
                                motor_enabled
                            )

                        except ValueError:
                            pass

                elif text.startswith("E,"):
                    raw_steering = 0
                    raw_throttle = 0
                    motor_enabled = False
                    servo_angle = 90
                    motor_pwm = 0

            elif sock is jetson_sock:
                try:
                    data = jetson_sock.recv(4096)
                except ConnectionRefusedError:
                    continue

                if phone_addr is not None:
                    phone_sock.sendto(data, phone_addr)

        # Save at 10 FPS
        if recording and time.monotonic() >= next_save_time:
            next_save_time += 1.0 / RECORD_FPS

            with camera_lock:
                if latest_frame is None:
                    continue

                frame = latest_frame.copy()
                frame_timestamp = latest_frame_timestamp

            # Never save the same camera frame twice.
            if (
                last_camera_timestamp is not None
                and frame_timestamp <= last_camera_timestamp
            ):
                continue

            last_camera_timestamp = frame_timestamp

            filename = "frame_%06d.jpg" % frame_index
            relative_path = "rgb/" + filename
            output_path = episode_dir / relative_path

            if not cv2.imwrite(
                str(output_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 90],
            ):
                raise RuntimeError(
                    "Failed to save frame: %s" % output_path
                )

            row = {
                "timestamp": int(frame_timestamp * 1000),
                "timestamp_s": frame_timestamp,
                "frame_index": frame_index,

                "observation.images.front_rgb": relative_path,

                "action.servo_angle": servo_angle,
                "action.motor_pwm": motor_pwm,

                "task": TASK,

                "mcqueen.raw.steering_command": raw_steering,
                "mcqueen.raw.throttle_command": raw_throttle,
                "mcqueen.raw.motor_enabled": motor_enabled,
            }

            frames_file.write(json.dumps(row) + "\n")

            print(
                "frame=%05d | servo=%3d | pwm=%4d"
                % (
                    frame_index,
                    servo_angle,
                    motor_pwm,
                )
            )

            frame_index += 1

except KeyboardInterrupt:
    print("\nRecorder stopping...")

finally:
    if recording:
        stop_episode("interrupted")

    shutdown.set()

    http_server.shutdown()
    http_server.server_close()
    http_thread.join(timeout=2)

    camera_thread.join(timeout=2)

    cap.release()
    phone_sock.close()
    jetson_sock.close()

    print("Session saved:", session_dir)
