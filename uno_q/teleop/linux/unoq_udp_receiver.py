#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import socket
import sys
import time
from dataclasses import dataclass
from typing import Optional

from arduino.app_utils import Bridge


@dataclass
class ClientState:
    address: Optional[tuple[str, int]] = None
    session: str = ""
    session_armed: bool = False
    last_sequence: int = -1
    echo_timestamp_ms: int = 0
    commanded_steering: int = 0
    commanded_throttle: int = 0
    motor_enabled: bool = False
    last_command_monotonic: float = 0.0
    failsafe: bool = True


class McQueenReceiver:
    def __init__(
        self,
        bind_ip: str,
        port: int,
        expected_token: str,
        failsafe_seconds: float,
    ) -> None:
        self.bind_ip = bind_ip
        self.port = port
        self.expected_token = expected_token
        self.failsafe_seconds = failsafe_seconds
        self.state = ClientState()
        self.running = True
        self.last_status_send = 0.0
        self.last_logger_send = 0.0
        self.logger_address = ("192.168.4.2", 5008)
        self.logger_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        self.last_printed_command: Optional[tuple[int, int, bool]] = None
        self.bridge_ready = False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind_ip, port))
        self.sock.settimeout(0.02)

    @staticmethod
    def clamp(value: int, minimum: int = -1000, maximum: int = 1000) -> int:
        return max(minimum, min(maximum, value))

    def bridge_call(self, method: str, *args: object) -> object:
        try:
            result = Bridge.call(method, *args)
            self.bridge_ready = True
            return result
        except Exception as exc:
            self.bridge_ready = False
            raise RuntimeError(
                f"Bridge call '{method}' failed: {exc}"
            ) from exc

    def wait_for_bridge(self) -> None:
        print("[BRIDGE] Waiting for MCU sketch RPC method 'ping'...", flush=True)

        while self.running:
            try:
                result = self.bridge_call("ping")
                print(f"[BRIDGE] MCU ready, ping={result}", flush=True)
                self.bridge_call("estop")
                return
            except Exception as exc:
                print(f"[BRIDGE] Not ready yet: {exc}", flush=True)
                time.sleep(1.0)

    def stop_mcu(self, reason: str) -> None:
        self.state.commanded_steering = 0
        self.state.commanded_throttle = 0
        self.state.motor_enabled = False
        self.state.failsafe = True

        try:
            self.bridge_call("estop")
        except Exception as exc:
            print(f"[BRIDGE] ESTOP failed during {reason}: {exc}", flush=True)

    def send_drive(
        self,
        steering: int,
        throttle: int,
        motor_enabled: bool,
    ) -> None:
        effective_enabled = motor_enabled or throttle != 0

        self.bridge_call(
            "set_drive",
            steering,
            throttle,
            1 if effective_enabled else 0,
        )

        command = (steering, throttle, effective_enabled)

        if command != self.last_printed_command:
            print(
                f"[DRIVE] steer={steering:5d} "
                f"throttle={throttle:5d} "
                f"enabled={int(effective_enabled)}",
                flush=True,
            )
            self.last_printed_command = command

    def accept_token(self, token: str) -> bool:
        return not self.expected_token or token == self.expected_token

    def parse_common(
        self,
        parts: list[str],
    ) -> Optional[tuple[str, str, int, int]]:
        if len(parts) < 5:
            return None

        token = parts[1].strip()
        session = parts[2].strip()

        if not self.accept_token(token):
            return None

        try:
            sequence = int(parts[3])
            timestamp_ms = int(parts[4])
        except ValueError:
            return None

        return token, session, sequence, timestamp_ms

    def process_packet(
        self,
        payload: bytes,
        address: tuple[str, int],
    ) -> None:
        line = payload.decode("utf-8", errors="replace").strip()

        if not line:
            return

        parts = [part.strip() for part in line.split(",")]
        packet_type = parts[0][:1] if parts else ""

        common = self.parse_common(parts)

        if common is None:
            return

        _, session, sequence, timestamp_ms = common

        if session != self.state.session:
            self.state.session = session
            self.state.session_armed = False
            self.state.last_sequence = -1

        if sequence <= self.state.last_sequence:
            return

        self.state.address = address
        self.state.last_sequence = sequence
        self.state.echo_timestamp_ms = timestamp_ms

        if packet_type == "H":
            return

        if packet_type == "E":
            self.state.session_armed = False
            self.stop_mcu("phone ESTOP")
            print("[PHONE] ESTOP received", flush=True)
            return

        if packet_type != "C" or len(parts) != 8:
            return

        try:
            steering = self.clamp(int(parts[5]))
            throttle = self.clamp(int(parts[6]))
            motor_enabled = int(parts[7]) != 0
        except ValueError:
            return

        if not self.state.session_armed:
            if steering == 0 and throttle == 0:
                self.state.session_armed = True
                print(
                    f"[PHONE] Session armed: {session}",
                    flush=True,
                )
            else:
                return

        try:
            self.send_drive(
                steering,
                throttle,
                motor_enabled,
            )
        except Exception as exc:
            print(f"[BRIDGE] Drive command failed: {exc}", flush=True)
            self.stop_mcu("bridge failure")
            return

        self.state.commanded_steering = steering
        self.state.commanded_throttle = throttle
        self.state.motor_enabled = motor_enabled or throttle != 0
        self.state.last_command_monotonic = time.monotonic()
        self.state.failsafe = False

    @staticmethod
    def steering_to_angle(steering: int) -> int:
        # Matches the MCU mapping, including reversed steering.
        reversed_steering = -steering
        angle = 55 + ((reversed_steering + 1000) * (125 - 55)) // 2000
        return max(55, min(125, angle))

    def send_status(self, now: float) -> None:
        if self.state.address is None or not self.state.session:
            return

        if now - self.last_status_send < 0.067:
            return

        self.last_status_send = now

        status = (
            f"S,{self.state.session},"
            f"{self.state.last_sequence},"
            f"{self.state.echo_timestamp_ms},"
            f"{self.state.commanded_steering},"
            f"{self.steering_to_angle(self.state.commanded_steering)},"
            f"{self.state.commanded_throttle},"
            f"{self.state.commanded_throttle},"
            f"{1 if self.state.failsafe else 0},"
            f"{'WIFI' if not self.state.failsafe else 'NONE'},"
            f"-1\n"
        )

        try:
            self.sock.sendto(
                status.encode("utf-8"),
                self.state.address,
            )
        except OSError:
            pass

    def send_logger_snapshot(self, now: float) -> None:
        # One synchronized control snapshot every 200 ms = 5 Hz.
        if now - self.last_logger_send < 0.2:
            return

        self.last_logger_send = now

        try:
            servo_angle = int(
                self.bridge_call("get_servo_angle")
            )

            motor_pwm = int(
                self.bridge_call("get_motor_pwm")
            )

            payload = {
                "type": "control_snapshot",
                "timestamp_ms": time.time_ns() // 1_000_000,
                "servo_angle_sent": servo_angle,
                "motor_pwm_sent": motor_pwm,
                "camera_frame": "",
            }

            self.logger_socket.sendto(
                json.dumps(payload).encode("utf-8"),
                self.logger_address,
            )

        except Exception:
            # Laptop may be disconnected; car control must continue.
            pass

    def enforce_failsafe(self, now: float) -> None:
        if self.state.last_command_monotonic == 0:
            return

        if (
            now - self.state.last_command_monotonic
            <= self.failsafe_seconds
        ):
            return

        if not self.state.failsafe:
            print("[FAILSAFE] Phone command timeout; stopping car", flush=True)
            self.stop_mcu("phone timeout")

    def run(self) -> None:
        self.wait_for_bridge()

        print(
            f"[UDP] Listening on {self.bind_ip}:{self.port}",
            flush=True,
        )
        print(
            "[UDP] Expected phone format: "
            "C,token,session,sequence,timestamp,steering,throttle,motor_enabled",
            flush=True,
        )

        while self.running:
            try:
                payload, address = self.sock.recvfrom(2048)
                self.process_packet(payload, address)
            except socket.timeout:
                pass
            except OSError as exc:
                if self.running:
                    print(f"[UDP] Socket error: {exc}", flush=True)

            now = time.monotonic()
            self.enforce_failsafe(now)
            self.send_status(now)
            self.send_logger_snapshot(now)

        self.stop_mcu("receiver shutdown")
        self.sock.close()
        self.logger_socket.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kachow phone UDP to UNO Q RouterBridge teleop receiver"
    )
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5007)
    parser.add_argument(
        "--token",
        default="",
        help="Optional exact control token. Empty accepts any non-empty token.",
    )
    parser.add_argument(
        "--failsafe-ms",
        type=int,
        default=300,
    )
    args = parser.parse_args()

    receiver = McQueenReceiver(
        bind_ip=args.bind,
        port=args.port,
        expected_token=args.token,
        failsafe_seconds=max(0.1, args.failsafe_ms / 1000.0),
    )

    def handle_signal(signum: int, frame: object) -> None:
        del signum, frame
        receiver.running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        receiver.run()
    except KeyboardInterrupt:
        receiver.running = False
        receiver.stop_mcu("keyboard interrupt")
    except Exception as exc:
        print(f"[FATAL] {type(exc).__name__}: {exc}", file=sys.stderr)
        receiver.stop_mcu("fatal error")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
