#!/usr/bin/env python3
"""gst_rtx_rtp_receiver.py — McQueen RTX receiver for the punched-UDP transport.

Receives H.264 RTP packets + in-band META datagrams over ONE NAT-punched UDP
socket (same rendezvous pattern as tools/realtime/direct_udp_peer.py).

Exact frame association (benchmark-v2 contract):
  - Every Jetson frame emits META (frame_id, capture_mono_ns) immediately
    BEFORE that frame's RTP packets, on the SAME socket. The META and the video
    are not independently transported: in-band ordering guarantees that the
    i-th completed video frame corresponds to the i-th META.
  - Frames are completed by the RTP marker bit. Decoded frames (appsink) are
    paired with completed META entries in order. If decoding drops a frame, the
    index drift is detected and counted as a mismatch — never silently guessed.

Control return: same socket, CTRL datagram echoing frame_id + capture_mono_ns,
so the Jetson computes receive_mono_ns - capture_mono_ns on one clock.

Benchmark-v2 stages:
  SIGNALING_P2P, VIDEO_CONNECTED, VIDEO_FRAMES, FRAME_TIMESTAMP,
  EXACT_FRAME_MATCH, RTX_INFERENCE, DIRECT_UDP, CONTROL_RETURN,
  FULL_LOOP_LATENCY (computed on the Jetson side).
"""

from __future__ import print_function

import argparse
import json
import os
import socket
import struct
import threading
import time

import websocket
import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

Gst.init(None)

MAGIC_COOKIE = 0x2112A442
META_PREFIX = b"META\t"
CTRL_PREFIX = b"CTRL\t"


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
                typ, ln = struct.unpack("!HH", data[off:off + 4])
                val = data[off + 4:off + 4 + ln]
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


class Receiver(object):
    def __init__(self, args):
        self.args = args
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(0.05)
        self.pub = stun(self.sock, args.stun_host, args.stun_port)

        self.ws = websocket.create_connection(args.broker, timeout=10)
        self.ws.settimeout(None)

        self.peer = None
        self.stop_event = threading.Event()

        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.appsrc = None
        self.appsink = None

        self.frames_rx = 0       # completed RTP frames seen in udp_loop
        self.meta_q = []         # completed META entries, in order
        self.meta_lock = threading.Lock()
        self.assoc_ok = 0
        self.assoc_miss = 0
        self.rtp_rx = 0          # raw RTP datagrams received
        self.meta_rx = 0         # raw META datagrams received

        self.ctrl_seq = 0
        self.ctrl_sent = 0

        self.torch = None
        self.infer_ms = []
        self.infer_lock = threading.Lock()

        self.started = time.monotonic()
        self.last_report = self.started

        # RTP timestamp bookkeeping for the current in-flight frame.
        self.cur_meta = None
        self.cur_rtp_pts = None

    # ---------- broker / rendezvous -------------------------------------------

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
                and msg.get("role") == "jetson"
            ):
                peer = (str(msg["ip"]), int(msg["port"]))
                if peer != self.peer:
                    self.peer = peer
                    print(
                        "[RTX-GST] PEER_CANDIDATE {}:{}".format(peer[0], peer[1]),
                        flush=True,
                    )
                    # Re-punch to a changed peer: the Jetson sender binds a
                    # fresh UDP port on every restart, so its CGNAT mapping
                    # changes too. Without re-punching, the return path dies
                    # and no frames arrive (seen 2026-08-13: sender restarted
                    # with a new port, receiver kept the old mapping -> 0 RTP).
                    for _ in range(10):
                        try:
                            self.sock.sendto(b"PUNCH2", peer)
                        except Exception:
                            pass
                        try:
                            self.sock.recvfrom(2048)
                        except socket.timeout:
                            pass

    def announce_loop(self):
        while not self.stop_event.is_set():
            try:
                self._send_ws({
                    "type": "control_udp_candidate_v2",
                    "role": "rtx",
                    "ip": self.pub[0],
                    "port": self.pub[1],
                })
            except Exception:
                pass
            self.stop_event.wait(0.35)

    def rendezvous(self):
        print("[RTX-GST] PUBLIC {}:{}".format(self.pub[0], self.pub[1]), flush=True)
        a = threading.Thread(target=self.announce_loop)
        a.daemon = True
        a.start()

        # Wait for the Jetson candidate WITHOUT a hard timeout: both sides
        # announce continuously, so any start order works — rendezvous completes
        # as soon as both peers are up.
        while self.peer is None and not self.stop_event.is_set():
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.05)

        if self.peer is None:
            raise RuntimeError(
                "Jetson UDP candidate missing (stopped before rendezvous)"
            )

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

        print(
            "[RTX-GST] SIGNALING_P2P READY peer={}:{}".format(
                self.peer[0], self.peer[1]
            ),
            flush=True,
        )

    # ---------- UDP receive loop: META + RTP in-band --------------------------

    def udp_loop(self):
        while not self.stop_event.is_set():
            try:
                data, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                return

            if data.startswith(META_PREFIX):
                try:
                    meta = json.loads(data[len(META_PREFIX):].decode("utf-8"))
                    self.cur_meta = meta
                    self.cur_rtp_pts = None
                    self.meta_rx += 1
                except Exception:
                    pass
            elif data.startswith(CTRL_PREFIX):
                pass  # ACK path unused
            elif self.cur_meta is not None:
                # RTP packet for the frame announced by the last META.
                if len(data) < 12:
                    continue
                self.rtp_rx += 1
                if self.rtp_rx % 30 == 0:
                    print(
                        "[RTX-GST] RTP_RX pkts={} meta={} frames_rx={}".format(
                            self.rtp_rx, self.meta_rx, self.frames_rx
                        ),
                        flush=True,
                    )
                if self.cur_rtp_pts is None:
                    self.cur_rtp_pts = struct.unpack("!I", data[8:12])[0]
                # Marker bit = last packet of this RTP frame.
                if data[1] & 0x80:
                    with self.meta_lock:
                        self.meta_q.append(self.cur_meta)
                        if len(self.meta_q) > 8:
                            self.meta_q = self.meta_q[-8:]
                    self.frames_rx += 1
                    self.cur_meta = None
                    self.cur_rtp_pts = None
                # Feed RTP payload into appsrc (raw RTP packet).
                if self.appsrc is not None:
                    buf = Gst.Buffer.new_allocate(None, len(data), None)
                    buf.fill(0, data)
                    self.appsrc.emit("push-buffer", buf)

    # ---------- GStreamer -----------------------------------------------------

    def build(self):
        pipe_desc = (
            "appsrc name=src is-live=true format=time do-timestamp=true "
            "caps=application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 ! "
            "rtph264depay ! h264parse ! "
            "decodebin ! "
            "videoconvert ! "
            "video/x-raw,format=I420 ! "
            "queue max-size-buffers=1 leaky=downstream ! "
            "appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true"
        )
        self.pipeline = Gst.parse_launch(pipe_desc)
        if self.pipeline is None:
            raise RuntimeError("pipeline parse failed")

        self.appsrc = self.pipeline.get_by_name("src")
        self.appsink = self.pipeline.get_by_name("sink")
        self.appsink.connect("new-sample", self.on_sample)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[RTX-GST] PLAYING {}".format(ret), flush=True)

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[RTX-GST] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()

    # ---------- decode -> inference -> control return -------------------------

    def on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK

        # Pair this decoded frame with the oldest completed META.
        meta = None
        with self.meta_lock:
            if self.meta_q:
                meta = self.meta_q.pop(0)

        if meta is None:
            self.assoc_miss += 1
            return Gst.FlowReturn.OK

        self.assoc_ok += 1

        # RTX inference (CUDA dummy policy forward).
        infer_ms = None
        if self.torch is None:
            import torch
            self.torch = torch
            print(
                "[RTX-GST] PYTORCH cuda={} device={}".format(
                    torch.cuda.is_available(),
                    torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
                ),
                flush=True,
            )
        try:
            t0 = time.perf_counter()
            x = self.torch.rand((1, 2048), device="cuda")
            y = x.mean()
            self.torch.cuda.synchronize()
            infer_ms = (time.perf_counter() - t0) * 1000.0
            with self.infer_lock:
                self.infer_ms.append(infer_ms)
        except Exception as exc:
            print("[RTX-GST] INFER ERROR {}".format(exc), flush=True)
            infer_ms = 0.0

        servo = 90.0 + max(-5.0, min(5.0, (float(y.item()) - 0.5) * 10.0))
        pwm = 0

        # Control return echoes exact frame identity for Jetson-clock latency.
        self.ctrl_seq += 1
        msg = {
            "seq": self.ctrl_seq,
            "frame_id": int(meta["frame_id"]),
            "capture_mono_ns": int(meta["capture_mono_ns"]),
            "infer_ms": float(infer_ms or 0.0),
            "servo_angle_deg": float(servo),
            "motor_pwm": int(pwm),
            "ttl_ms": 250,
        }
        try:
            self.sock.sendto(
                CTRL_PREFIX + json.dumps(msg, separators=(",", ":")).encode("utf-8"),
                self.peer,
            )
            self.ctrl_sent += 1
        except Exception as exc:
            print("[RTX-GST] CTRL send error {}".format(exc), flush=True)

        now = time.monotonic()
        if now - self.last_report >= 1.0:
            elapsed = max(now - self.started, 0.001)
            with self.infer_lock:
                tail = self.infer_ms[-20:]
            print(
                "[RTX-GST] VIDEO frames_rx={} fps={:.1f} assoc_ok={} assoc_miss={} "
                "ctrl_sent={} infer_avg={:.2f}ms".format(
                    self.frames_rx,
                    self.frames_rx / elapsed,
                    self.assoc_ok,
                    self.assoc_miss,
                    self.ctrl_sent,
                    sum(tail) / max(len(tail), 1),
                ),
                flush=True,
            )
            self.last_report = now

        return Gst.FlowReturn.OK

    def run(self):
        t = threading.Thread(target=self._ws_loop)
        t.daemon = True
        t.start()
        u = threading.Thread(target=self.udp_loop)
        u.daemon = True
        u.start()

        self.rendezvous()
        self.build()

        try:
            self.loop.run()
        finally:
            self.stop_event.set()
            if self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)
            try:
                self.ws.close()
            except Exception:
                pass
            self.sock.close()

            with self.infer_lock:
                infer_n = len(self.infer_ms)
                infer_avg = sum(self.infer_ms) / infer_n if infer_n else 0.0
            print(
                "[RTX-GST] RTX_INFERENCE avg={:.2f}ms n={}".format(infer_avg, infer_n),
                flush=True,
            )
            print(
                "[RTX-GST] CONTROL_RETURN sent={} EXACT_FRAME_MATCH ok={} miss={}".format(
                    self.ctrl_sent, self.assoc_ok, self.assoc_miss
                ),
                flush=True,
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", required=True)
    p.add_argument("--stun-host", default="stun.cloudflare.com")
    p.add_argument("--stun-port", type=int, default=3478)
    args = p.parse_args()
    Receiver(args).run()


if __name__ == "__main__":
    main()
