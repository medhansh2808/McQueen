#!/usr/bin/env python3
"""measure_true_path_rtt.py — UDP round-trip probe over McQueen's TRUE WAN path.

Measures the real Jetson -> lab public IP -> listener round trip (the path the
punched-UDP transport actually takes), independent of WebRTC/STUN machinery:

    Jetson (probe) --> NAT/CGNAT --> lab router public IP (port-forwarded)
        --> listener machine at lab (RTX or lab laptop) --> echo back.

Usage (lab, interactive ssh / two terminals):
    listen:  python3 measure_true_path_rtt.py --role listen --port 5955
             (run on the machine that owns the port-forward on 14.139.108.62)
    probe:   python3 measure_true_path_rtt.py --role probe \
                 --host 14.139.108.62 --port 5955 --count 100 --out rtt.csv

Output contains ONLY durations/percentiles/loss — never clock timestamps
(no-timestamps rule, AGENTS.md C).

This file is NEW and standalone: it does not touch run_rtp_wan_test.sh or any
deployed copy. Requires explicit human authorization to run (network probe).
"""

from __future__ import print_function

import argparse
import socket
import struct
import time

MAGIC = b"MCQR"
HEADER = struct.Struct("<4sQQ")  # magic, seq, client_mono_ns


def listen(port, verbose):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    print("[RTT-LISTEN] bound 0.0.0.0:{} (echo-mode)".format(port), flush=True)
    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) < HEADER.size:
            continue
        magic, seq, _ = HEADER.unpack(data[:HEADER.size])
        if magic != MAGIC:
            continue
        if verbose:
            print("[RTT-LISTEN] seq={} bytes={}".format(seq, len(data)), flush=True)
        sock.sendto(data, addr)


def _mono_ns():
    # Jetson Nano ships Python 3.6 (no time.monotonic_ns); keep 3.6-compatible.
    return int(time.monotonic() * 1e9)


def probe(host, port, count, interval, timeout, out_path, verbose=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    payload = b"\x00" * 32  # fixed 32B body; total packet = 48B
    rtts = []  # ms per received echo (in probe order)
    lost = 0
    for seq in range(count):
        mono = _mono_ns()
        sock.sendto(HEADER.pack(MAGIC, seq, mono) + payload, (host, port))
        try:
            data, _ = sock.recvfrom(2048)
            recv_ns = _mono_ns()
        except socket.timeout:
            lost += 1
            continue
        if len(data) != HEADER.size + len(payload):
            lost += 1
            continue
        magic, echo_seq, echo_ns = HEADER.unpack(data[:HEADER.size])
        if magic != MAGIC or echo_seq != seq:
            lost += 1
            continue
        # Round trip measured on the CLIENT monotonic clock; the server's
        # elapsed handling is irrelevant for RTT (no clock timestamps kept).
        rtt_ms = (recv_ns - mono) / 1e6
        rtts.append(rtt_ms)
        if verbose:
            print("[RTT-PROBE] seq={}/{} rtt={:.2f}ms".format(seq + 1, count, rtt_ms), flush=True)
        if interval > 0:
            time.sleep(interval)

    sent = count
    received = len(rtts)
    loss = 100.0 * (sent - received) / sent if sent else 0.0
    print("[RTT-PROBE] host={}:{} sent={} received={} loss={:.1f}%".format(
        host, port, sent, received, loss), flush=True)
    if rtts:
        rtts_sorted = sorted(rtts)
        avg = sum(rtts) / len(rtts)
        p95 = rtts_sorted[int(0.95 * (len(rtts_sorted) - 1))]
        jitter = sum(
            abs(b - a) for a, b in zip(rtts, rtts[1:])
        ) / max(len(rtts) - 1, 1)
        print("[RTT-PROBE] min={:.2f}ms avg={:.2f}ms p95={:.2f}ms max={:.2f}ms jitter={:.2f}ms".format(
            rtts_sorted[0], avg, p95, rtts_sorted[-1], jitter), flush=True)
    if out_path:
        with open(out_path, "w") as f:
            f.write("seq,rtt_ms\n")
            for i, r in enumerate(rtts):
                f.write("{},{:.3f}\n".format(i, r))
        print("[RTT-PROBE] per-probe RTTs written to {}".format(out_path), flush=True)
    return loss


def main():
    p = argparse.ArgumentParser(description="true-path UDP RTT probe (McQueen)")
    p.add_argument("--role", required=True, choices=["listen", "probe"])
    p.add_argument("--host", default="127.0.0.1", help="probe target (lab public IP)")
    p.add_argument("--port", type=int, default=5955)
    p.add_argument("--count", type=int, default=100, help="probes (probe role)")
    p.add_argument("--interval", type=float, default=0.1, help="seconds between probes")
    p.add_argument("--timeout", type=float, default=2.0, help="recv timeout seconds")
    p.add_argument("--out", default=None, help="write per-probe RTTs to this CSV")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.role == "listen":
        listen(args.port, args.verbose)
    else:
        probe(args.host, args.port, args.count, args.interval, args.timeout, args.out, args.verbose)


if __name__ == "__main__":
    main()