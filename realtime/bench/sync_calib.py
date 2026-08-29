#!/usr/bin/env python3
"""sync_calib.py - one-shot NTP-style clock offset between Jetson and RTX.

Runs over the SAME direct-UDP path the video uses (no broker, no signaling):
  - RTX  side: bare socket, STUNs to print its public, echoes every datagram
               with (t2=recv_mono_ns, t3=send_mono_ns) stamped on the RTX clock.
  - Jetson side: STUNs to print its public, punches a NAT mapping to the RTX
               public, sends N probe packets, computes t4, and prints the
               clock offset  o = median((t2 - t1) + (t3 - t4)) / 2
               (NTP formula; offset = RTX_clock - Jetson_clock).

Usage:
  RTX:   python3 sync_calib.py --role rtx --stun-host stun.cloudflare.com --stun-port 3478
  Jetson: python3 sync_calib.py --role jetson --peer <RTX_PUBLIC_IP:PORT> \
           --stun-host stun.cloudflare.com --stun-port 3478
"""
import argparse
import socket
import statistics
import struct
import sys
import time

STUN_MAGIC = 0x2112A442


def mono_ns():
    return time.monotonic_ns()


def stun(sock, host, port):
    tid = b"SYNCCALIB12345678"
    req = struct.pack(">HHI", 0x0001, 0, STUN_MAGIC) + tid
    for _ in range(3):
        try:
            sock.sendto(req, (host, port))
        except OSError:
            pass
        sock.settimeout(1.0)
        try:
            data, _ = sock.recvfrom(2048)
            if len(data) >= 20 and data[4:8] == struct.pack(">I", STUN_MAGIC):
                n_attrs = struct.unpack(">H", data[2:4])[0]
                off = 20
                for _ in range(n_attrs):
                    if off + 4 > len(data):
                        break
                    atype, alen = struct.unpack(">HH", data[off:off + 4])
                    if atype == 0x0020:  # XOR-MAPPED-ADDRESS
                        family = data[off + 4 + 1]
                        if family == 1:
                            ip = socket.inet_ntoa(data[off + 8:off + 12])
                            port = struct.unpack(">H", data[off + 6:off + 8])[0] ^ 0x2112
                            return ip, port
                        elif family == 2:
                            ip = socket.inet_ntop(socket.AF_INET6, bytes(
                                b ^ c for b, c in zip(data[off + 8:off + 24], b"\x21\x12\xa4\x42" * 4)))
                            port = struct.unpack(">H", data[off + 6:off + 8])[0] ^ 0x2112
                            return ip, port
                    off += 4 + alen
                    if atype == 0x0020:
                        off += 4 - (alen % 4)  # pad to 4
        except socket.timeout:
            continue
    return None


def run_rtx(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    pub = stun(sock, args.stun_host, args.stun_port)
    if not pub:
        print("[CALIB] STUN FAILED", flush=True)
        sys.exit(2)
    print("[CALIB] RTX PUBLIC {}:{}".format(*pub), flush=True)
    print("[CALIB] RTX echoing for {}s (no peer needed)".format(args.window), flush=True)
    sock.settimeout(0.5)
    deadline = mono_ns() + args.window * 1_000_000_000
    n = 0
    while mono_ns() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        t2 = mono_ns()
        if data[:4] == b"SYN1":
            t3 = mono_ns()
            sock.sendto(b"SYN2" + struct.pack(">QQ", t2, t3), addr)
            n += 1
        elif data[:4] == b"KEEP":
            pass  # keepalive: just keeps the mapping alive
    print("[CALIB] RTX echoed {} probes, done".format(n), flush=True)


def run_jetson(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    pub = stun(sock, args.stun_host, args.stun_port)
    if not pub:
        print("[CALIB] STUN FAILED", flush=True)
        sys.exit(2)
    print("[CALIB] JETSON PUBLIC {}:{}".format(*pub), flush=True)
    peer = args.peer.split(":")
    peer = (peer[0], int(peer[1]))
    print("[CALIB] JETSON peer {}".format(peer), flush=True)

    deadline = mono_ns() + args.window * 1_000_000_000
    samples = []
    keepalive_t = 0.0
    sock.settimeout(1.0)
    while mono_ns() < deadline:
        now = time.time()
        if now - keepalive_t > 0.5:
            sock.sendto(b"KEEPcalib", peer)
            keepalive_t = now
        if len(samples) < args.samples:
            t1 = mono_ns()
            sock.sendto(b"SYN1" + struct.pack(">Q", t1), peer)
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        if data[:4] == b"SYN2":
            t4 = mono_ns()
            t2, t3 = struct.unpack(">QQ", data[4:20])
            o = ((t2 - t1) + (t3 - t4)) / 2
            rtt = (t4 - t1) - (t3 - t2)
            samples.append((o, rtt))
            print("[CALIB] sample {} offset={:.6f}ms rtt={:.1f}ms".format(
                len(samples), o / 1e6, rtt / 1e6), flush=True)
        if len(samples) >= args.samples:
            break
    if len(samples) < 5:
        print("[CALIB] FAILED: only {} samples (check punch)".format(len(samples)), flush=True)
        sys.exit(3)
    offs = [s[0] for s in samples]
    rtts = [s[1] for s in samples]
    o = statistics.median(offs)
    print("[CALIB] OFFSET_RTX_MINUS_JETSON_NS = {}".format(int(o)), flush=True)
    print("[CALIB] OFFSET_RTX_MINUS_JETSON_MS = {:.3f}".format(o / 1e6), flush=True)
    print("[CALIB] RTT p50={:.1f}ms p95={:.1f}ms n={}".format(
        statistics.median(rtts) / 1e6, sorted(rtts)[int(0.95 * len(rtts))] / 1e6, len(rtts)), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["jetson", "rtx"], required=True)
    ap.add_argument("--peer", default=None, help="IP:PORT of the other side's public")
    ap.add_argument("--stun-host", default="stun.cloudflare.com")
    ap.add_argument("--stun-port", type=int, default=3478)
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--window", type=int, default=45)
    args = ap.parse_args()
    if args.role == "rtx":
        run_rtx(args)
    else:
        run_jetson(args)


if __name__ == "__main__":
    main()
