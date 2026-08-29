#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import os
import socket
import struct
import threading
import time
import websocket

MAGIC_COOKIE = 0x2112A442

def mono_ns():
    return int(time.monotonic() * 1000000000)

def stun(sock, host, port):
    tid = os.urandom(12)
    req = struct.pack("!HHI12s", 1, 0, MAGIC_COOKIE, tid)
    target = (socket.gethostbyname(host), port)
    old = sock.gettimeout()
    sock.settimeout(3.0)
    try:
        for _ in range(4):
            sock.sendto(req, target)
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if len(data) < 20 or data[8:20] != tid:
                continue
            mlen = struct.unpack("!H", data[2:4])[0]
            off, end = 20, min(len(data), 20 + mlen)
            while off + 4 <= end:
                typ, ln = struct.unpack("!HH", data[off:off+4])
                val = data[off+4:off+4+ln]
                if typ in (0x20, 0x01) and len(val) >= 8 and val[1] == 1:
                    p = struct.unpack("!H", val[2:4])[0]
                    ip = bytearray(val[4:8])
                    if typ == 0x20:
                        p ^= (MAGIC_COOKIE >> 16)
                        cookie = struct.pack("!I", MAGIC_COOKIE)
                        for i in range(4):
                            ip[i] ^= cookie[i]
                    return socket.inet_ntoa(bytes(ip)), p
                off += 4 + ((ln + 3) // 4) * 4
        raise RuntimeError("STUN public candidate not received")
    finally:
        sock.settimeout(old)

class Peer(object):
    def __init__(self, args):
        self.args = args
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(0.15)
        self.pub = stun(self.sock, args.stun_host, args.stun_port)

        self.ws = websocket.create_connection(args.broker, timeout=10)
        self.ws.settimeout(None)

        self.peer = None
        self.stop_event = threading.Event()
        self.peer_event = threading.Event()

        t = threading.Thread(target=self._ws_loop)
        t.daemon = True
        t.start()

    def _send_ws(self, obj):
        self.ws.send(json.dumps(obj, separators=(",", ":")))

    def _ws_loop(self):
        while not self.stop_event.is_set():
            try:
                raw = self.ws.recv()
                if not raw:
                    return
                msg = json.loads(raw)
            except Exception:
                return

            if (
                msg.get("type") == "control_udp_candidate_v2"
                and msg.get("role") != self.args.role
            ):
                peer = (str(msg["ip"]), int(msg["port"]))
                if peer != self.peer:
                    self.peer = peer
                    print(
                        "[{}] PEER_CANDIDATE {}:{}".format(
                            self.args.role.upper(), peer[0], peer[1]
                        ),
                        flush=True,
                    )
                self.peer_event.set()

    def rendezvous(self):
        role = self.args.role.upper()
        print("[{}] PUBLIC {}:{}".format(role, self.pub[0], self.pub[1]), flush=True)

        # IMPORTANT: keep announcing for the full window EVEN AFTER learning the
        # other side. This removes the one-sided relay race from the previous run.
        deadline = time.time() + 8.0
        next_announce = 0.0
        while time.time() < deadline:
            now = time.time()
            if now >= next_announce:
                self._send_ws({
                    "type": "control_udp_candidate_v2",
                    "role": self.args.role,
                    "ip": self.pub[0],
                    "port": self.pub[1],
                })
                next_announce = now + 0.35

            if self.peer is not None:
                try:
                    self.sock.sendto(b"PUNCH2", self.peer)
                except Exception:
                    pass

            # Drain punch packets but do not block long.
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.02)

        if self.peer is None:
            raise RuntimeError("peer UDP candidate missing after repeated announcements")

        # Final symmetric punch burst.
        for _ in range(30):
            try:
                self.sock.sendto(b"PUNCH2", self.peer)
            except Exception:
                pass
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.02)

        print("[{}] DIRECT_UDP_READY".format(role), flush=True)

    def run_jetson(self):
        print("[JETSON] DRY-RUN ONLY — ZERO GPIO WRITES", flush=True)
        got = 0
        deadline = time.time() + 12.0

        while time.time() < deadline and got < 60:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue

            if not data.startswith(b"CTRL2 "):
                continue

            try:
                msg = json.loads(data[6:].decode("utf-8"))
                seq = int(msg["seq"])
                servo = float(msg["servo"])
                pwm = int(msg["pwm"])
                sent_ns = int(msg["sent_ns"])
            except Exception:
                continue

            got += 1
            self.sock.sendto(
                ("ACK2 {} {}".format(seq, sent_ns)).encode("ascii"),
                addr,
            )

            if got % 15 == 0:
                print(
                    "[JETSON] CONTROL_RX count={} servo={:.1f} pwm={}".format(
                        got, servo, pwm
                    ),
                    flush=True,
                )

        print("[JETSON] CONTROL_RX_TOTAL {}".format(got), flush=True)
        if got < 30:
            raise RuntimeError("too few direct control packets")

    def run_rtx(self):
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device != "cuda":
            raise RuntimeError("RTX CUDA unavailable")

        print("[RTX] PYTORCH_CUDA {}".format(torch.cuda.get_device_name(0)), flush=True)

        acks = {}
        rx_stop = threading.Event()

        def rx_loop():
            while not rx_stop.is_set():
                try:
                    data, _ = self.sock.recvfrom(4096)
                except socket.timeout:
                    continue

                if not data.startswith(b"ACK2 "):
                    continue
                try:
                    _, seq, sent_ns = data.decode("ascii").split()
                    acks[int(seq)] = (mono_ns() - int(sent_ns)) / 1000000.0
                except Exception:
                    pass

        t = threading.Thread(target=rx_loop)
        t.daemon = True
        t.start()

        infer_times = []

        # 60 control ticks at 25 Hz. Lost packets are intentionally not resent.
        for seq in range(60):
            t0 = time.perf_counter()

            # Small CUDA operation stands in for policy forward pass.
            x = torch.rand((1, 2048), device="cuda")
            y = x.mean()
            torch.cuda.synchronize()

            infer_ms = (time.perf_counter() - t0) * 1000.0
            infer_times.append(infer_ms)

            servo = 90.0 + max(-5.0, min(5.0, (float(y.item()) - 0.5) * 10.0))
            pwm = 0

            msg = {
                "seq": seq,
                "sent_ns": mono_ns(),
                "servo": servo,
                "pwm": pwm,
                "ttl_ms": 250,
                "infer_ms": infer_ms,
            }

            self.sock.sendto(
                b"CTRL2 " + json.dumps(msg, separators=(",", ":")).encode("utf-8"),
                self.peer,
            )
            time.sleep(0.04)

        time.sleep(1.5)
        rx_stop.set()

        vals = sorted(acks.values())
        print("[RTX] CONTROL_ACKS {}/60".format(len(vals)), flush=True)
        print(
            "[RTX] CUDA_DUMMY_INFER avg={:.2f}ms max={:.2f}ms".format(
                sum(infer_times) / len(infer_times), max(infer_times)
            ),
            flush=True,
        )

        if vals:
            p50 = vals[len(vals)//2]
            p95 = vals[min(len(vals)-1, int(len(vals)*0.95))]
            print(
                "[RTX] DIRECT_CONTROL_RTT min={:.1f}ms p50={:.1f}ms "
                "p95={:.1f}ms max={:.1f}ms".format(
                    min(vals), p50, p95, max(vals)
                ),
                flush=True,
            )

        if len(vals) < 30:
            raise RuntimeError("direct control ACK path failed")

    def run(self):
        try:
            self.rendezvous()
            if self.args.role == "jetson":
                self.run_jetson()
            else:
                self.run_rtx()
        finally:
            self.stop_event.set()
            try:
                self.ws.close()
            except Exception:
                pass
            self.sock.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--role", required=True, choices=["jetson", "rtx"])
    p.add_argument("--broker", required=True)
    p.add_argument("--stun-host", default="stun.cloudflare.com")
    p.add_argument("--stun-port", type=int, default=3478)
    args = p.parse_args()
    Peer(args).run()

if __name__ == "__main__":
    main()
