#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import os
import random
import socket
import struct
import threading
import time

import websocket

MAGIC_COOKIE = 0x2112A442
ATTR_MAPPED_ADDRESS = 0x0001
ATTR_XOR_MAPPED_ADDRESS = 0x0020


def mono_ns():
    return int(time.monotonic() * 1000000000)


def percentile(values, p):
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def stats_line(name, values):
    if not values:
        return "{}: NO SAMPLES".format(name)
    return (
        "{}: n={} min={:.1f}ms p50={:.1f}ms p95={:.1f}ms max={:.1f}ms avg={:.1f}ms"
        .format(
            name,
            len(values),
            min(values),
            percentile(values, 0.50),
            percentile(values, 0.95),
            max(values),
            sum(values) / float(len(values)),
        )
    )


def stun_public_addr(sock, host, port):
    trans_id = os.urandom(12)
    req = struct.pack("!HHI12s", 0x0001, 0, MAGIC_COOKIE, trans_id)

    old_timeout = sock.gettimeout()
    sock.settimeout(3.0)

    try:
        target = (socket.gethostbyname(host), port)

        last = None
        for _ in range(3):
            sock.sendto(req, target)
            try:
                data, _ = sock.recvfrom(2048)
                last = data
                break
            except socket.timeout:
                pass

        if not last or len(last) < 20:
            raise RuntimeError("no STUN response")

        msg_type, msg_len, cookie = struct.unpack("!HHI", last[:8])
        rx_tid = last[8:20]

        if cookie != MAGIC_COOKIE or rx_tid != trans_id:
            raise RuntimeError("invalid STUN response")

        off = 20
        end = min(len(last), 20 + msg_len)

        while off + 4 <= end:
            atype, alen = struct.unpack("!HH", last[off:off+4])
            val = last[off+4:off+4+alen]

            if len(val) >= 8 and atype in (ATTR_XOR_MAPPED_ADDRESS, ATTR_MAPPED_ADDRESS):
                family = val[1]
                if family != 0x01:
                    off += 4 + ((alen + 3) // 4) * 4
                    continue

                port_v = struct.unpack("!H", val[2:4])[0]
                ip_b = bytearray(val[4:8])

                if atype == ATTR_XOR_MAPPED_ADDRESS:
                    port_v ^= (MAGIC_COOKIE >> 16)
                    cookie_b = struct.pack("!I", MAGIC_COOKIE)
                    for i in range(4):
                        ip_b[i] ^= cookie_b[i]

                ip = socket.inet_ntoa(bytes(ip_b))
                return ip, port_v

            off += 4 + ((alen + 3) // 4) * 4

        raise RuntimeError("STUN response lacked IPv4 mapped address")

    finally:
        sock.settimeout(old_timeout)


class Peer(object):
    def __init__(self, args):
        self.args = args
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("0.0.0.0", 0))
        self.udp.settimeout(0.15)

        self.local_addr = self.udp.getsockname()
        self.public_addr = None
        self.peer_addr = None

        self.ws = None
        self.ws_lock = threading.Lock()
        self.peer_event = threading.Event()
        self.ws_pongs = {}
        self.ws_cond = threading.Condition()
        self.stop = threading.Event()

    def ws_send(self, obj):
        raw = json.dumps(obj, separators=(",", ":"))
        with self.ws_lock:
            self.ws.send(raw)

    def ws_loop(self):
        while not self.stop.is_set():
            try:
                raw = self.ws.recv()
                if raw is None:
                    return
                msg = json.loads(raw)
            except Exception:
                return

            typ = msg.get("type")

            if typ == "udp_candidate" and msg.get("role") != self.args.role:
                try:
                    self.peer_addr = (str(msg["ip"]), int(msg["port"]))
                    print(
                        "[{}] peer UDP candidate {}:{}"
                        .format(self.args.role.upper(), self.peer_addr[0], self.peer_addr[1]),
                        flush=True,
                    )
                    self.peer_event.set()
                except Exception:
                    pass

            elif typ == "latency_ping" and self.args.role == "rtx":
                self.ws_send({
                    "type": "latency_pong",
                    "seq": int(msg["seq"]),
                    "sent_ns": int(msg["sent_ns"]),
                })

            elif typ == "latency_pong" and self.args.role == "jetson":
                try:
                    seq = int(msg["seq"])
                    sent_ns = int(msg["sent_ns"])
                    rtt_ms = (mono_ns() - sent_ns) / 1000000.0
                    with self.ws_cond:
                        self.ws_pongs[seq] = rtt_ms
                        self.ws_cond.notify_all()
                except Exception:
                    pass

    def setup(self):
        print(
            "[{}] UDP local {}:{}"
            .format(self.args.role.upper(), self.local_addr[0], self.local_addr[1]),
            flush=True,
        )

        self.public_addr = stun_public_addr(
            self.udp, self.args.stun_host, self.args.stun_port
        )
        print(
            "[{}] STUN public {}:{}"
            .format(self.args.role.upper(), self.public_addr[0], self.public_addr[1]),
            flush=True,
        )

        print(
            "[{}] broker connecting {}"
            .format(self.args.role.upper(), self.args.broker),
            flush=True,
        )
        self.ws = websocket.create_connection(self.args.broker, timeout=10)
        self.ws.settimeout(None)
        print("[{}] broker connected".format(self.args.role.upper()), flush=True)

        th = threading.Thread(target=self.ws_loop)
        th.daemon = True
        th.start()

        # The broker is a live relay, not a message queue. If one peer
        # announces before the other is connected, that one-shot message is lost.
        # Re-announce our public UDP address until we have learned the peer's.
        deadline = time.time() + 20.0
        next_announce = 0.0

        while not self.peer_event.is_set() and time.time() < deadline:
            now = time.time()

            if now >= next_announce:
                self.ws_send({
                    "type": "udp_candidate",
                    "role": self.args.role,
                    "ip": self.public_addr[0],
                    "port": self.public_addr[1],
                })
                print(
                    "[{}] announcing UDP candidate {}:{}"
                    .format(
                        self.args.role.upper(),
                        self.public_addr[0],
                        self.public_addr[1],
                    ),
                    flush=True,
                )
                next_announce = now + 0.75

            self.peer_event.wait(0.10)

        if not self.peer_event.is_set():
            raise RuntimeError("did not receive peer UDP candidate after repeated announcements")

        # Echo our address once more now that the peer is definitely online,
        # so both directions converge even if they joined at slightly different times.
        self.ws_send({
            "type": "udp_candidate",
            "role": self.args.role,
            "ip": self.public_addr[0],
            "port": self.public_addr[1],
        })

    def udp_responder_loop(self):
        print("[RTX] direct UDP responder active", flush=True)
        deadline = time.time() + self.args.runtime

        # Keep punching outward so both NATs learn the path.
        next_punch = 0.0
        while time.time() < deadline:
            now = time.time()
            if now >= next_punch and self.peer_addr:
                try:
                    self.udp.sendto(b"PUNCH", self.peer_addr)
                except Exception:
                    pass
                next_punch = now + 0.10

            try:
                data, addr = self.udp.recvfrom(2048)
            except socket.timeout:
                continue

            if data.startswith(b"PING "):
                try:
                    self.udp.sendto(b"PONG " + data[5:], addr)
                except Exception:
                    pass

    def udp_latency_test(self):
        print("[JETSON] punching direct UDP path...", flush=True)

        # Simultaneous UDP punches for NAT traversal.
        end = time.time() + 2.0
        while time.time() < end:
            self.udp.sendto(b"PUNCH", self.peer_addr)
            try:
                self.udp.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.03)

        vals = []

        for seq in range(self.args.count):
            sent = mono_ns()
            payload = "PING {} {}".format(seq, sent).encode("ascii")
            self.udp.sendto(payload, self.peer_addr)

            deadline = time.time() + 1.0
            got = False

            while time.time() < deadline:
                try:
                    data, _ = self.udp.recvfrom(2048)
                except socket.timeout:
                    continue

                if data.startswith(b"PONG "):
                    parts = data.decode("ascii", "ignore").split()
                    if len(parts) == 3 and int(parts[1]) == seq:
                        vals.append((mono_ns() - sent) / 1000000.0)
                        got = True
                        break

            if not got:
                print("[JETSON] UDP seq={} LOST".format(seq), flush=True)

            time.sleep(self.args.interval)

        print(stats_line("DIRECT_UDP_RTT", vals), flush=True)
        return vals

    def websocket_latency_test(self):
        vals = []

        for seq in range(self.args.ws_count):
            sent = mono_ns()

            with self.ws_cond:
                self.ws_pongs.pop(seq, None)

            self.ws_send({
                "type": "latency_ping",
                "seq": seq,
                "sent_ns": sent,
            })

            deadline = time.time() + 3.0

            with self.ws_cond:
                while seq not in self.ws_pongs and time.time() < deadline:
                    self.ws_cond.wait(0.10)

                if seq in self.ws_pongs:
                    vals.append(self.ws_pongs.pop(seq))
                else:
                    print("[JETSON] WSS seq={} LOST".format(seq), flush=True)

            time.sleep(self.args.interval)

        print(stats_line("CLOUDFLARE_WS_RTT", vals), flush=True)
        return vals

    def run(self):
        self.setup()

        try:
            if self.args.role == "rtx":
                self.udp_responder_loop()
            else:
                udp_vals = self.udp_latency_test()
                ws_vals = self.websocket_latency_test()

                print("", flush=True)
                print("===== LATENCY RESULT =====", flush=True)

                if udp_vals:
                    print("✅ DIRECT UDP Jetson <-> RTX works", flush=True)
                    print(stats_line("DIRECT_UDP_RTT", udp_vals), flush=True)
                else:
                    print("❌ DIRECT UDP Jetson <-> RTX did not return packets", flush=True)

                if ws_vals:
                    print(stats_line("CLOUDFLARE_WS_RTT", ws_vals), flush=True)

                if udp_vals and percentile(udp_vals, 0.95) < 100.0:
                    print("✅ DIRECT UDP p95 is under 100 ms", flush=True)
                elif udp_vals:
                    print("⚠️ DIRECT UDP p95 is >= 100 ms", flush=True)

        finally:
            self.stop.set()
            try:
                self.ws.close()
            except Exception:
                pass
            try:
                self.udp.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--role", choices=["jetson", "rtx"], required=True)
    p.add_argument("--broker", required=True)
    p.add_argument("--stun-host", default="stun.l.google.com")
    p.add_argument("--stun-port", type=int, default=19302)
    p.add_argument("--count", type=int, default=60)
    p.add_argument("--ws-count", type=int, default=30)
    p.add_argument("--interval", type=float, default=0.05)
    p.add_argument("--runtime", type=float, default=45.0)
    args = p.parse_args()

    Peer(args).run()


if __name__ == "__main__":
    main()
