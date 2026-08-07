"""UDP teleoperation server compatible with the existing Android controller."""

import socket
import threading
import time

from .drive import DriveController, MockDriveBackend
from .protocol import make_status, parse_phone_packet


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def steering_to_angle(steering):
    """Preserve the previous UNO-Q status mapping used by the Android UI."""
    steering = -clamp(int(steering), -1000, 1000)

    if steering < 0:
        return 45 + ((steering + 1000) * (80 - 45)) // 1000

    return 80 + (steering * (115 - 80)) // 1000


class TeleopServer(threading.Thread):
    """Phone UDP server.

    Default port 5007 matches the existing Android app. A custom port can be
    supplied for laptop self-tests.
    """

    def __init__(
        self,
        backend=None,
        bind_host="0.0.0.0",
        port=5007,
        failsafe_seconds=0.300,
        status_hz=15.0,
    ):
        super().__init__(name="mcqueen-teleop", daemon=True)

        self.backend = backend if backend is not None else MockDriveBackend()
        self.drive = DriveController(
            self.backend,
            failsafe_seconds=failsafe_seconds,
        )

        self.bind_host = str(bind_host)
        self.port = int(port)
        self.status_interval = 1.0 / float(status_hz)

        self.stop_event = threading.Event()
        self.sock = None

        self.phone_address = None
        self.echo_timestamp_ms = 0
        self.last_status_send = 0.0

    def stop(self):
        self.stop_event.set()

        sock = self.sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _handle_packet(self, payload, address):
        packet = parse_phone_packet(payload)
        if packet is None:
            return "invalid"

        self.phone_address = address
        self.echo_timestamp_ms = int(packet["timestamp_ms"])

        return self.drive.handle_packet(packet)

    def _send_status(self, now):
        if self.phone_address is None:
            return

        if not self.drive.session:
            return

        if now - self.last_status_send < self.status_interval:
            return

        self.last_status_send = now

        state = self.drive.snapshot()

        status = make_status(
            session=state["session"],
            sequence=state["last_sequence"],
            echo_timestamp_ms=self.echo_timestamp_ms,
            commanded_steering=state["steering"],
            actual_servo_angle=steering_to_angle(state["steering"]),
            commanded_throttle=state["throttle"],
            actual_throttle=state["throttle"],
            failsafe=state["failsafe"],
            source="JETSON",
            rssi=-1,
        )

        try:
            self.sock.sendto(status.encode("ascii"), self.phone_address)
        except OSError:
            pass

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock = sock

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.bind_host, self.port))

        # If port=0 was requested for a self-test, expose the assigned port.
        self.port = int(sock.getsockname()[1])
        sock.settimeout(0.02)

        while not self.stop_event.is_set():
            try:
                payload, address = sock.recvfrom(2048)
                self._handle_packet(payload, address)
            except socket.timeout:
                pass
            except OSError:
                if not self.stop_event.is_set():
                    raise
                break

            now = time.monotonic()
            self.drive.enforce_failsafe(now=now)
            self._send_status(now)

        self.drive.emergency_stop("server shutdown")
        try:
            sock.close()
        except OSError:
            pass


def main():
    server = TeleopServer()
    server.start()

    print(
        "McQueen Jetson-compatible UDP teleop server "
        "listening on 0.0.0.0:{}".format(server.port),
        flush=True,
    )

    try:
        while server.is_alive():
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.join(timeout=2.0)


if __name__ == "__main__":
    main()
