#!/usr/bin/env python3
from __future__ import print_function

import argparse
import collections
import time

from robot.jetson_nano.mcqueen_edge.drive import MockDriveBackend
from robot.jetson_nano.mcqueen_edge.server import TeleopServer


class ProbeServer(TeleopServer):
    def __init__(self, *args, **kwargs):
        super(ProbeServer, self).__init__(*args, **kwargs)
        self.results = collections.Counter()
        self.packet_count = 0

    def _handle_packet(self, payload, address):
        result = super(ProbeServer, self)._handle_packet(payload, address)
        self.packet_count += 1
        self.results[result] += 1
        snap = self.drive.snapshot()
        print(
            "[KACHOW] packet={} from={}:{} result={} session={} armed={} "
            "seq={} steering={} throttle={} motor={} failsafe={}".format(
                self.packet_count,
                address[0], address[1],
                result,
                snap["session"],
                snap["session_armed"],
                snap["last_sequence"],
                snap["steering"],
                snap["throttle"],
                snap["motor_enabled"],
                snap["failsafe"],
            ),
            flush=True,
        )
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=30.0)
    args = p.parse_args()

    backend = MockDriveBackend()
    server = ProbeServer(
        backend=backend,
        bind_host="0.0.0.0",
        port=5007,
        failsafe_seconds=0.300,
    )
    server.start()

    deadline = time.time() + args.seconds
    try:
        while time.time() < deadline:
            time.sleep(0.1)
    finally:
        server.stop()
        server.join(timeout=2.0)

    print("", flush=True)
    print("===== KACHOW PROBE RESULT =====", flush=True)
    print("packets={}".format(server.packet_count), flush=True)
    print("results={}".format(dict(server.results)), flush=True)
    print("backend_calls={}".format(len(backend.calls)), flush=True)

    valid = (
        server.packet_count > 0
        and (
            server.results.get("hello", 0)
            or server.results.get("applied", 0)
            or server.results.get("estop", 0)
            or server.results.get("awaiting-neutral", 0)
        )
    )
    command_seen = (
        server.results.get("applied", 0) > 0
        or server.results.get("estop", 0) > 0
    )

    if valid and command_seen:
        print("✅ KACHOW -> JETSON VALID CONTROL PACKETS PROVEN", flush=True)
        return 0

    if valid:
        print("⚠️ KACHOW packets seen, but move controls / press E-stop next time", flush=True)
        return 3

    print("❌ NO VALID KACHOW PACKETS SEEN", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
