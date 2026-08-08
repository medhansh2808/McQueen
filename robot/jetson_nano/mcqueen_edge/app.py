"""Single-process McQueen Jetson edge application."""

import argparse
import time

from .drive import MockDriveBackend
from .http_server import McQueenHTTPServer, RuntimeState
from .server import TeleopServer


class EdgeApp:
    def __init__(
        self,
        backend=None,
        udp_host="0.0.0.0",
        udp_port=5007,
        http_host="0.0.0.0",
        http_port=8080,
        failsafe_seconds=0.300,
    ):
        self.backend = backend if backend is not None else MockDriveBackend()
        self.runtime_state = RuntimeState()

        self.teleop = TeleopServer(
            backend=self.backend,
            bind_host=udp_host,
            port=udp_port,
            failsafe_seconds=failsafe_seconds,
        )

        self.http = McQueenHTTPServer(
            runtime_state=self.runtime_state,
            bind_host=http_host,
            port=http_port,
        )

    def start(self, timeout=2.0):
        self.teleop.start()
        self.http.start()

        deadline = time.time() + float(timeout)

        while time.time() < deadline:
            udp_ready = False

            sock = self.teleop.sock
            if sock is not None:
                try:
                    udp_ready = int(sock.getsockname()[1]) != 0
                except OSError:
                    udp_ready = False

            http_ready = self.http.httpd is not None

            if udp_ready and http_ready:
                return

            time.sleep(0.01)

        self.stop()
        raise RuntimeError("McQueen edge app failed to start")

    def stop(self):
        self.http.stop()
        self.teleop.stop()

        if self.http.is_alive():
            self.http.join(timeout=2.0)

        if self.teleop.is_alive():
            self.teleop.join(timeout=2.0)

        close_backend = getattr(self.backend, "close", None)
        if callable(close_backend):
            close_backend()

    @property
    def udp_port(self):
        return self.teleop.port

    @property
    def http_port(self):
        return self.http.port


def build_backend(args):
    if not args.jetson:
        return MockDriveBackend()

    from .jetson_gpio import JetsonDriveBackend

    missing = []
    if args.servo_left_us is None:
        missing.append("--servo-left-us")
    if args.servo_center_us is None:
        missing.append("--servo-center-us")
    if args.servo_right_us is None:
        missing.append("--servo-right-us")

    if missing:
        raise ValueError(
            "Jetson mode requires measured servo calibration: {}".format(
                ", ".join(missing)
            )
        )

    return JetsonDriveBackend(
        servo_left_us=args.servo_left_us,
        servo_center_us=args.servo_center_us,
        servo_right_us=args.servo_right_us,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="McQueen Jetson edge app")
    parser.add_argument(
        "--jetson",
        action="store_true",
        help="use real Jetson GPIO/PWM instead of the safe mock backend",
    )
    parser.add_argument("--servo-left-us", type=int)
    parser.add_argument("--servo-center-us", type=int)
    parser.add_argument("--servo-right-us", type=int)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        backend = build_backend(args)
    except (ValueError, RuntimeError) as exc:
        print("ERROR: {}".format(exc), flush=True)
        return 2

    app = EdgeApp(backend=backend)
    app.start()

    mode = "JETSON GPIO" if args.jetson else "MOCK"
    print("McQueen edge app started ({})".format(mode), flush=True)
    print("UDP  : 0.0.0.0:{}".format(app.udp_port), flush=True)
    print("HTTP : http://0.0.0.0:{}".format(app.http_port), flush=True)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        print("McQueen edge app stopped", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
