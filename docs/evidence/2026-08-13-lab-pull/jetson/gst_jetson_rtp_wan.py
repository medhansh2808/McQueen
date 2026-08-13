#!/usr/bin/env python3
"""gst_jetson_rtp_wan.py — McQueen Jetson sender: H.264 RTP over NAT-punched UDP.

Transport design (lab-verified path, 2026-08-13):
  - Camera -> NVENC H.264 -> rtph264pay (GStreamer 1.14 on Jetson, no srflx
    needed because we do NOT use webrtcbin/ICE at all).
  - RTP packets + in-band frame metadata are sent over ONE UDP socket that was
    NAT-punched using the proven stun()+broker rendezvous pattern from
    tools/realtime/direct_udp_peer.py (60/60 ACK proof, p50 ~43 ms).
  - Frame metadata (frame_id, capture_mono_ns) travels on the SAME socket
    immediately before that frame's RTP packets. Association is exact by
    construction (same-socket ordering), and the RTX cross-checks RTP timestamps.
  - Control return is received on the same socket; the Jetson computes
    receive_mono_ns - capture_mono_ns on its own monotonic clock.

Dry-run safety: zero GPIO writes. This script only captures/encodes/sends.

Usage:
  python3 gst_jetson_rtp_wan.py --broker wss://.../ws?role=jetson&session=mcqueen \
      --device /dev/v4l/by-id/... --stun stun://stun.l.google.com:19302
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


class Sender(object):
    def __init__(self, args):
        self.args = args
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(0.15)
        self.pub = stun(self.sock, args.stun_host, args.stun_port)

        self.ws = websocket.create_connection(args.broker, timeout=10)
        self.ws.settimeout(None)

        self.peer = None
        self.peer_event = threading.Event()
        self.stop_event = threading.Event()

        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.frame_id = 0
        self.last_rtp_ts = None

        # Frame metadata queue: (frame_id, capture_mono_ns) pushed by the
        # v4l2src pad probe, consumed by the rtph264pay pad probe (one per frame).
        self.capture_q = []
        self.capture_lock = threading.Lock()

        # Latency bookkeeping for the authoritative Jetson-clock measurement.
        self.latency_ms = []
        self.ctrl_count = 0
        self.stage = {}
        self.sent_pkts = 0
        self.sent_meta = 0

    # ---------- broker / rendezvous (proven pattern from direct_udp_peer.py) --

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
                and msg.get("role") == "rtx"
            ):
                peer = (str(msg["ip"]), int(msg["port"]))
                if peer != self.peer:
                    self.peer = peer
                    print(
                        "[JETSON-CAM] PEER_CANDIDATE {}:{}".format(peer[0], peer[1]),
                        flush=True,
                    )
                self.peer_event.set()

    def announce_loop(self):
        # Announce our UDP endpoint continuously for the whole run. Both sides
        # must keep announcing so a late-starting peer still learns the address.
        while not self.stop_event.is_set():
            try:
                self._send_ws({
                    "type": "control_udp_candidate_v2",
                    "role": "jetson",
                    "ip": self.pub[0],
                    "port": self.pub[1],
                })
            except Exception:
                pass
            self.stop_event.wait(0.35)

    def rendezvous(self):
        print(
            "[JETSON-CAM] PUBLIC {}:{}".format(self.pub[0], self.pub[1]), flush=True
        )
        a = threading.Thread(target=self.announce_loop)
        a.daemon = True
        a.start()

        # Wait for the RTX candidate (up to 60 s), draining punch packets.
        deadline = time.time() + 60.0
        while time.time() < deadline:
            if self.peer is not None:
                break
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.05)

        if self.peer is None:
            raise RuntimeError("RTX UDP candidate missing after repeated announcements")

        # Symmetric punch burst at the learned peer.
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

        print("[JETSON-CAM] DIRECT_UDP_READY peer={}:{}".format(
            self.peer[0], self.peer[1]), flush=True)

    # ---------- control receive loop (same socket) ---------------------------

    def ctrl_loop(self):
        while not self.stop_event.is_set():
            try:
                data, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                return

            if not data.startswith(CTRL_PREFIX):
                continue
            try:
                msg = json.loads(data[len(CTRL_PREFIX):].decode("utf-8"))
            except Exception:
                continue

            capture = int(msg.get("capture_mono_ns", 0) or 0)
            now = mono_ns()
            self.ctrl_count += 1
            if capture:
                self.latency_ms.append((now - capture) / 1000000.0)

            if self.ctrl_count % 10 == 0:
                print(
                    "[JETSON-CAM] CTRL_RX n={} frame={} servo={:.1f} pwm={} "
                    "infer={:.2f}ms".format(
                        self.ctrl_count,
                        msg.get("frame_id"),
                        float(msg.get("servo_angle_deg", 0.0)),
                        int(msg.get("motor_pwm", 0)),
                        float(msg.get("infer_ms", 0.0)),
                    ),
                    flush=True,
                )

    # ---------- GStreamer -----------------------------------------------------

    def on_capture_probe(self, pad, info):
        # Stamped at the v4l2src output: this is the true capture time.
        with self.capture_lock:
            self.capture_q.append((self.frame_id, mono_ns()))
            # Bounded queue: if the encoder lags, drop the oldest capture
            # stamps rather than drifting indefinitely.
            if len(self.capture_q) > 8:
                self.capture_q = self.capture_q[-8:]
        self.frame_id += 1
        return Gst.PadProbeReturn.OK

    def on_rtp_probe(self, pad, info):
        # One probe per RTP packet. A new video frame starts whenever the RTP
        # timestamp changes. At the first packet of a frame we emit META, then
        # the frame's packets. Each frame consumes exactly ONE capture_q entry.
        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            payload = mapinfo.data
            if len(payload) < 12:
                return Gst.PadProbeReturn.OK
            rtp_ts = struct.unpack("!I", payload[8:12])[0]
            marker = bool(payload[1] & 0x80)
            pts_ns = buf.pts if buf.pts != Gst.CLOCK_TIME_NONE else 0
        finally:
            buf.unmap(mapinfo)

        if rtp_ts != self.last_rtp_ts:
            # New frame: consume the next capture entry and emit its META
            # in-band BEFORE the first RTP packet of this frame.
            self.last_rtp_ts = rtp_ts
            frame_id = None
            capture = None
            with self.capture_lock:
                if self.capture_q:
                    frame_id, capture = self.capture_q[0]
                    self.capture_q = self.capture_q[1:]
            if frame_id is not None:
                meta = json.dumps({
                    "frame_id": frame_id,
                    "capture_mono_ns": capture,
                    "rtp_pts_ns": pts_ns,
                }, separators=(",", ":")).encode("utf-8")
                try:
                    self.sock.sendto(META_PREFIX + meta, self.peer)
                    self.sent_meta += 1
                except Exception:
                    pass

        # Send the RTP packet on the same socket (in-band after its META).
        try:
            self.sock.sendto(payload, self.peer)
            self.sent_pkts += 1
            if self.sent_pkts % 30 == 0:
                print(
                    "[JETSON-CAM] SENT pkts={} meta={} peer={}:{}".format(
                        self.sent_pkts, self.sent_meta,
                        self.peer[0] if self.peer else "?",
                        self.peer[1] if self.peer else "?",
                    ),
                    flush=True,
                )
        except Exception:
            pass

        return Gst.PadProbeReturn.OK

    def build(self):
        desc = (
            "webrtcbin name=sendrecv "  # placeholder, replaced below
        )
        del desc
        pipe_desc = (
            "v4l2src name=vsrc device={} do-timestamp=true ! "
            "image/jpeg,width=1280,height=720,framerate=30/1 ! "
            "jpegparse ! "
            "nvv4l2decoder mjpeg=1 ! "
            "nvvidconv ! "
            "video/x-raw(memory:NVMM),format=NV12 ! "
            "queue max-size-buffers=2 leaky=downstream ! "
            "nvv4l2h264enc bitrate=2500000 iframeinterval=15 ! "
            "h264parse config-interval=-1 ! "
            "rtph264pay name=pay pt=96 config-interval=-1 ! "
            "fakesink"
        ).format(self.args.device)

        print("[JETSON-CAM] camera {}".format(self.args.device), flush=True)
        print(
            "[JETSON-CAM] pipeline: MJPEG 1280x720@30 -> NVDEC -> NVENC H264 "
            "-> RTP -> punched UDP (no ICE)",
            flush=True,
        )

        self.pipeline = Gst.parse_launch(pipe_desc)
        if self.pipeline is None:
            raise RuntimeError("pipeline parse failed")

        vsrc = self.pipeline.get_by_name("vsrc")
        pad = vsrc.get_static_pad("src")
        pad.add_probe(Gst.PadProbeType.BUFFER, self.on_capture_probe)

        pay = self.pipeline.get_by_name("pay")
        if pay is None:
            raise RuntimeError("rtph264pay not found in pipeline")
        ppad = pay.get_static_pad("src")
        ppad.add_probe(Gst.PadProbeType.BUFFER, self.on_rtp_probe)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[JETSON-CAM] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()
        elif msg.type == Gst.MessageType.EOS:
            print("[JETSON-CAM] EOS", flush=True)
            self.loop.quit()

    def run(self):
        t = threading.Thread(target=self._ws_loop)
        t.daemon = True
        t.start()
        c = threading.Thread(target=self.ctrl_loop)
        c.daemon = True
        c.start()

        self.rendezvous()
        self.build()

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[JETSON-CAM] PLAYING {}".format(ret), flush=True)

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

            vals = sorted(self.latency_ms)
            if vals:
                p50 = vals[len(vals) // 2]
                p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
                print(
                    "[JETSON-CAM] FULL_LOOP_LATENCY n={} min={:.1f}ms p50={:.1f}ms "
                    "p95={:.1f}ms max={:.1f}ms".format(
                        len(vals), vals[0], p50, p95, vals[-1]
                    ),
                    flush=True,
                )
            else:
                print("[JETSON-CAM] FULL_LOOP_LATENCY n=0 NO_CONTROL_RETURNS", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--stun-host", default="stun.cloudflare.com")
    p.add_argument("--stun-port", type=int, default=3478)
    args = p.parse_args()
    Sender(args).run()


if __name__ == "__main__":
    main()
