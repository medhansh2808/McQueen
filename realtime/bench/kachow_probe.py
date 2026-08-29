#!/usr/bin/env python3
from __future__ import print_function

import argparse
import collections
import time

from edge.drive import MockDriveBackend
from edge.server import TeleopServer


def throttle_to_pwm(raw_throttle, enabled):
    """Recorder-exact label math: motor_pwm = round(clamp(throttle,-1000,1000)*255/1000).

    Inlined (identical to recorder.throttle_to_pwm) so the probe stays
    importable without the recorder's cv2/record_row dependency chain.
    """
    if not enabled:
        return 0
    clamped = max(-1000, min(1000, int(raw_throttle)))
    return int(round(clamped * 255.0 / 1000.0))


class ProbeServer(TeleopServer):
    def __init__(self, *args, **kwargs):
        super(ProbeServer, self).__init__(*args, **kwargs)
        self.results = collections.Counter()
        self.packet_count = 0
        self.throttle_vals = []  # raw phone throttle per applied packet
        self.steering_vals = []  # raw phone steering per applied packet

    def _handle_packet(self, payload, address):
        result = super(ProbeServer, self)._handle_packet(payload, address)
        self.packet_count += 1
        self.results[result] += 1
        snap = self.drive.snapshot()
        motor_pwm = throttle_to_pwm(snap["throttle"], snap["motor_enabled"])
        if result == "applied":
            self.throttle_vals.append(snap["throttle"])
            self.steering_vals.append(snap["steering"])
        print(
            "[KACHOW] packet={} from={}:{} result={} session={} armed={} "
            "seq={} steering={} throttle={} pwm={} failsafe={}".format(
                self.packet_count,
                address[0], address[1],
                result,
                snap["session"],
                snap["session_armed"],
                snap["last_sequence"],
                snap["steering"],
                snap["throttle"],
                motor_pwm,
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

    # ---- Q1: motor-PWM label path health ----------------------------------
    # Same math as the recorder: motor_pwm = round(clamp(throttle,-1000,1000)*255/1000)
    # when motor_enabled. A dead label path = dataset useless for training.
    applied_throttles = server.throttle_vals
    applied_steerings = server.steering_vals
    non_zero = [t for t in applied_throttles if t != 0]
    pwms = [throttle_to_pwm(t, True) for t in applied_throttles]
    fwd = [p for p in pwms if p > 0]
    rev = [p for p in pwms if p < 0]
    print(
        "LABEL_PATH throttle n={} nonzero={} min={} max={} distinct={}".format(
            len(applied_throttles),
            len(non_zero),
            min(applied_throttles) if applied_throttles else 0,
            max(applied_throttles) if applied_throttles else 0,
            len(set(applied_throttles)),
        ),
        flush=True,
    )
    print(
        "LABEL_PATH motor_pwm n={} forward={} reverse={} pwm_min={} pwm_max={}".format(
            len(pwms),
            len(fwd),
            len(rev),
            min(pwms) if pwms else 0,
            max(pwms) if pwms else 0,
        ),
        flush=True,
    )
    if applied_steerings:
        print(
            "LABEL_PATH steering n={} min={} max={} extremes={}".format(
                len(applied_steerings),
                min(applied_steerings),
                max(applied_steerings),
                (min(applied_steerings) <= -900 and max(applied_steerings) >= 900),
            ),
            flush=True,
        )

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
    pwm_path_ok = bool(non_zero and fwd and rev)

    if valid and command_seen:
        print("✅ KACHOW -> JETSON VALID CONTROL PACKETS PROVEN", flush=True)
        if pwm_path_ok:
            print("✅ MOTOR_PWM LABEL PATH OK (forward + reverse, non-zero)", flush=True)
            return 0
        print(
            "⚠️  CONTROL OK but PWM label path UNPROVEN: drive forward AND reverse "
            "(nonzero throttle) with the phone next time",
            flush=True,
        )
        return 3

    if valid:
        print("⚠️ KACHOW packets seen, but move controls / press E-stop next time", flush=True)
        return 3

    print("❌ NO VALID KACHOW PACKETS SEEN", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
