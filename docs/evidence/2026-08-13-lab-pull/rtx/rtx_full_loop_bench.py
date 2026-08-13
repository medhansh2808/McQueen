#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import threading
import time
import os
import socket
import collections

import websocket
import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstSdp", "1.0")
gi.require_version("GstWebRTC", "1.0")

from gi.repository import GLib, Gst, GstSdp, GstWebRTC

Gst.init(None)


MAGIC_COOKIE = 0x2112A442

def stun_public(sock, host="stun.cloudflare.com", port=3478):
    import os, socket, struct
    tid = os.urandom(12)
    req = struct.pack("!HHI12s", 1, 0, MAGIC_COOKIE, tid)
    target = (socket.gethostbyname(host), port)
    old = sock.gettimeout()
    sock.settimeout(2.0)
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
        raise RuntimeError("STUN public candidate unavailable")
    finally:
        sock.settimeout(old)



class Receiver(object):
    def __init__(self, broker, stun):
        self.broker = broker
        self.stun = stun
        self.ws = None
        self.ws_lock = threading.Lock()
        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.webrtc = None
        self.latest_meta = {}
        self.meta_lock = threading.Lock()
        self.frames = 0
        self.started = time.monotonic()
        self.last_report = self.started
        self.video_connected = False
        self.torch_ready = False
        self.torch = None
        self.np = None
        self.infer_count = 0
        self.infer_ms = []
        self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ctrl_sock.bind(("0.0.0.0", 0))
        self.ctrl_sock.settimeout(0.20)
        self.ctrl_public = stun_public(self.ctrl_sock)
        self.ctrl_peer = None
        self.ctrl_lock = threading.Lock()
        self.ctrl_stop = threading.Event()
        self.meta_lock2 = threading.Lock()
        self.meta_queue = collections.deque(maxlen=4)
        self.ctrl_seq = 0
        self.acks = 0

    def send(self, data):
        payload = json.dumps(data, separators=(",", ":"))
        with self.ws_lock:
            self.ws.send(payload)

    def connect(self):
        print("[RTX-GST] broker connecting {}".format(self.broker), flush=True)
        self.ws = websocket.create_connection(self.broker, timeout=10)
        self.ws.settimeout(None)
        print("[RTX-GST] broker connected", flush=True)
        print("[RTX-GST] CONTROL_UDP public {}:{}".format(
            self.ctrl_public[0], self.ctrl_public[1]), flush=True)

        a = threading.Thread(target=self.ctrl_announce_loop)
        a.daemon = True
        a.start()

        u = threading.Thread(target=self.ctrl_udp_loop)
        u.daemon = True
        u.start()

        t = threading.Thread(target=self.recv_loop)
        t.daemon = True
        t.start()

    def ctrl_announce_loop(self):
        while not self.ctrl_stop.is_set():
            try:
                self.send({
                    "type": "bench_udp_candidate",
                    "role": "rtx",
                    "ip": self.ctrl_public[0],
                    "port": self.ctrl_public[1],
                })
                with self.ctrl_lock:
                    peer = self.ctrl_peer
                if peer is not None:
                    try:
                        self.ctrl_sock.sendto(b"PUNCHBENCH", peer)
                    except Exception:
                        pass
            except Exception:
                pass
            self.ctrl_stop.wait(0.35)

    def ctrl_udp_loop(self):
        while not self.ctrl_stop.is_set():
            try:
                data, _ = self.ctrl_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                return

            if data.startswith(b"META_BENCH "):
                try:
                    meta = json.loads(data[11:].decode("utf-8"))
                    with self.meta_lock2:
                        self.meta_queue.append(meta)
                except Exception:
                    pass
            elif data.startswith(b"ACK_BENCH "):
                self.acks += 1

    def recv_loop(self):
        while True:
            try:
                raw = self.ws.recv()
                if raw is None:
                    raise RuntimeError("broker closed")
                data = json.loads(raw)
                GLib.idle_add(self.handle_message, data)
            except Exception as exc:
                print("[RTX-GST] broker recv ended: {}".format(exc), flush=True)
                GLib.idle_add(self.loop.quit)
                return

    def build(self):
        # Build an actual pipeline and add webrtcbin as a child.
        # Gst.parse_launch("webrtcbin name=recv") may return the webrtcbin
        # element itself, so looking it up "inside itself" returns None.
        self.pipeline = Gst.Pipeline.new("mcqueen-rtx-webrtc")
        if self.pipeline is None:
            raise RuntimeError("failed to create RTX GStreamer pipeline")

        self.webrtc = Gst.ElementFactory.make("webrtcbin", "recv")
        if self.webrtc is None:
            raise RuntimeError("failed to create webrtcbin on RTX")

        self.pipeline.add(self.webrtc)

        if self.stun:
            self.webrtc.set_property("stun-server", self.stun)
            print("[RTX-GST] STUN {}".format(self.stun), flush=True)

        # GStreamer 1.18+ webrtcbin defaults to a 200 ms jitterbuffer.
        # For remote driving we prefer freshness over perfect recovery.
        if self.webrtc.find_property("latency") is not None:
            self.webrtc.set_property("latency", 20)
            print("[RTX-GST] WEBRTC JITTERBUFFER 20 ms", flush=True)
        else:
            print("[RTX-GST] WEBRTC JITTERBUFFER property unavailable", flush=True)

        self.webrtc.connect("on-ice-candidate", self.on_ice_candidate)
        self.webrtc.connect("pad-added", self.on_incoming_stream)

        try:
            self.webrtc.connect("notify::ice-connection-state", self.on_ice_state)
        except Exception:
            pass

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[RTX-GST] PLAYING {}".format(ret), flush=True)

    def on_ice_state(self, element, pspec):
        try:
            state = element.get_property("ice-connection-state")
            print("[RTX-GST] ICE {}".format(state), flush=True)
        except Exception:
            pass

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[RTX-GST] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()

    def parse_sdp(self, text):
        result, msg = GstSdp.SDPMessage.new()
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError("SDPMessage.new failed: {}".format(result))
        result = GstSdp.sdp_message_parse_buffer(bytes(text.encode("utf-8")), msg)
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError("SDP parse failed: {}".format(result))
        return msg

    def on_answer_created(self, promise, unused1, unused2):
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value("answer")
        if answer is None:
            raise RuntimeError("create-answer returned no answer")

        p = Gst.Promise.new()
        self.webrtc.emit("set-local-description", answer, p)
        p.interrupt()

        self.send({"type": "answer", "sdp": answer.sdp.as_text()})
        print("[RTX-GST] answer sent", flush=True)

    def handle_offer(self, text):
        msg = self.parse_sdp(text)
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER, msg
        )

        p = Gst.Promise.new()
        self.webrtc.emit("set-remote-description", offer, p)
        p.interrupt()

        print("[RTX-GST] offer applied -> creating answer", flush=True)
        promise = Gst.Promise.new_with_change_func(
            self.on_answer_created, None, None
        )
        self.webrtc.emit("create-answer", None, promise)

    def handle_message(self, data):
        typ = data.get("type")
        try:
            if typ == "offer":
                print("[RTX-GST] offer received", flush=True)
                self.handle_offer(data["sdp"])

            elif typ == "ice":
                cand = data.get("candidate", "")
                if cand:
                    self.webrtc.emit(
                        "add-ice-candidate",
                        int(data.get("mline", 0)),
                        cand,
                    )

            elif typ == "bench_udp_candidate" and data.get("role") == "jetson":
                peer = (str(data["ip"]), int(data["port"]))
                with self.ctrl_lock:
                    if peer != self.ctrl_peer:
                        self.ctrl_peer = peer
                        print("[RTX-GST] CONTROL_UDP peer {}:{}".format(
                            peer[0], peer[1]), flush=True)

            elif typ == "frame_meta":
                with self.meta_lock:
                    self.latest_meta = dict(data)

            elif typ == "peer":
                print(
                    "[RTX-GST] peer {} {}".format(
                        data.get("role"), data.get("state")
                    ),
                    flush=True,
                )
        except Exception as exc:
            print(
                "[RTX-GST] message error type={}: {}".format(typ, exc),
                flush=True,
            )
        return False

    def on_ice_candidate(self, element, mline, candidate):
        if candidate:
            kind = "srflx" if " typ srflx " in (" " + candidate + " ") else ("relay" if " typ relay " in (" " + candidate + " ") else "host/other")
            print("[RTX-GST] LOCAL ICE {} {}".format(kind, candidate), flush=True)
        self.send({
            "type": "ice",
            "mline": int(mline),
            "candidate": candidate or "",
        })

    def on_incoming_stream(self, element, pad):
        if pad.direction != Gst.PadDirection.SRC:
            return

        print("[RTX-GST] incoming RTP pad {}".format(pad.get_name()), flush=True)

        decodebin = Gst.ElementFactory.make("decodebin", None)
        if decodebin is None:
            print("[RTX-GST] ERROR: cannot create decodebin", flush=True)
            return

        decodebin.connect("pad-added", self.on_decode_pad)
        self.pipeline.add(decodebin)
        decodebin.sync_state_with_parent()

        sinkpad = decodebin.get_static_pad("sink")
        result = pad.link(sinkpad)
        print("[RTX-GST] RTP -> decodebin link {}".format(result), flush=True)

    def on_decode_pad(self, decodebin, pad):
        caps = pad.get_current_caps()
        if caps is None or caps.get_size() < 1:
            return

        name = caps.get_structure(0).get_name()
        print("[RTX-GST] decoded pad caps {}".format(name), flush=True)

        if not name.startswith("video/") or self.video_connected:
            return

        self.video_connected = True

        queue = Gst.ElementFactory.make("queue", None)
        conv = Gst.ElementFactory.make("videoconvert", None)
        sink = Gst.ElementFactory.make("appsink", "sink")

        if queue is None or conv is None or sink is None:
            raise RuntimeError("cannot create video receive elements")

        sink.set_property("emit-signals", True)
        sink.set_property("sync", False)
        sink.set_property("max-buffers", 1)
        sink.set_property("drop", True)
        sink.connect("new-sample", self.on_sample)

        self.pipeline.add(queue)
        self.pipeline.add(conv)
        self.pipeline.add(sink)

        # Never allow decoded frames to queue up. If RTX momentarily falls
        # behind, throw away old frames and keep the newest one.
        queue.set_property("max-size-buffers", 1)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)
        queue.set_property("leaky", 2)  # downstream = drop oldest buffer

        queue.sync_state_with_parent()
        conv.sync_state_with_parent()
        sink.sync_state_with_parent()

        if pad.link(queue.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            raise RuntimeError("decoded video pad -> queue link failed")

        if not queue.link(conv):
            raise RuntimeError("queue -> videoconvert failed")
        if not conv.link(sink):
            raise RuntimeError("videoconvert -> appsink failed")

        print("[RTX-GST] decoded video -> appsink READY", flush=True)

    def on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR

        self.frames += 1
        now = time.monotonic()

        # Warm/initialize CUDA once.
        if not self.torch_ready:
            import torch
            import numpy as np
            self.torch = torch
            self.np = np
            self.torch_ready = True
            print(
                "[RTX-GST] PYTORCH ready cuda={} device={}".format(
                    torch.cuda.is_available(),
                    torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
                ),
                flush=True,
            )

        # Run a tiny policy calculation on every third decoded frame (~7-10Hz at
        # current observed receive rates). This is the actual processing step in
        # this benchmark.
        if self.frames % 3 == 0:
            infer_ms = None
            servo = 90.0
            pwm = 0
            try:
                buf = sample.get_buffer()
                ok, mapinfo = buf.map(Gst.MapFlags.READ)
                if ok:
                    try:
                        t0 = time.perf_counter()
                        arr = self.np.frombuffer(mapinfo.data, dtype=self.np.uint8).copy()
                        tensor = self.torch.from_numpy(arr)
                        if self.torch.cuda.is_available():
                            tensor = tensor.to("cuda")
                        tensor = tensor.float()
                        mean = float(tensor.mean().item()) / 255.0
                        servo = 90.0 + max(-5.0, min(5.0, (mean - 0.5) * 10.0))
                        pwm = 0
                        if self.torch.cuda.is_available():
                            self.torch.cuda.synchronize()
                        infer_ms = (time.perf_counter() - t0) * 1000.0
                        self.infer_ms.append(infer_ms)
                    finally:
                        buf.unmap(mapinfo)
            except Exception as exc:
                print("[RTX-GST] INFER ERROR {}".format(exc), flush=True)

            # Pair the decoded frame to a bounded FIFO of recent Jetson capture
            # metadata. Keeping only four entries prevents stale backlog; taking
            # the oldest retained entry is intentionally conservative by up to
            # roughly a few frame intervals.
            meta = None
            with self.meta_lock2:
                if self.meta_queue:
                    meta = self.meta_queue.popleft()

            with self.ctrl_lock:
                peer = self.ctrl_peer

            if meta is not None and peer is not None and infer_ms is not None:
                self.ctrl_seq += 1
                msg = {
                    "seq": self.ctrl_seq,
                    "frame_id": int(meta["frame_id"]),
                    "capture_mono_ns": int(meta["capture_mono_ns"]),
                    "infer_ms": float(infer_ms),
                    "servo_angle_deg": float(servo),
                    "motor_pwm": int(pwm),
                    "ttl_ms": 250,
                }
                try:
                    self.ctrl_sock.sendto(
                        b"CTRL_BENCH " + json.dumps(
                            msg, separators=(",", ":")
                        ).encode("utf-8"),
                        peer,
                    )
                except Exception as exc:
                    print("[RTX-GST] CONTROL UDP send error {}".format(exc), flush=True)

                if self.ctrl_seq % 10 == 0:
                    tail = self.infer_ms[-20:]
                    print(
                        "[RTX-GST] ACTION seq={} frame={} infer={:.2f}ms "
                        "avg20={:.2f}ms servo={:.1f} pwm={} acks={}".format(
                            self.ctrl_seq, meta["frame_id"], infer_ms,
                            sum(tail)/len(tail), servo, pwm, self.acks
                        ),
                        flush=True,
                    )

        # Receiver-local freshness metric.
        recv_age_ms = None
        try:
            buf = sample.get_buffer()
            if buf is not None and buf.pts != Gst.CLOCK_TIME_NONE:
                clock = self.pipeline.get_clock()
                if clock is not None:
                    running_ns = clock.get_time() - self.pipeline.get_base_time()
                    recv_age_ms = max(0.0, (running_ns - buf.pts) / 1000000.0)
        except Exception:
            pass

        if now - self.last_report >= 1.0:
            elapsed = max(now - self.started, 0.001)
            fps = self.frames / elapsed
            caps = sample.get_caps()
            age_text = "?" if recv_age_ms is None else "{:.1f}ms".format(recv_age_ms)
            print(
                "[RTX-GST] VIDEO frames={} avg_fps={:.1f} recv_age={} caps={}".format(
                    self.frames, fps, age_text, caps.to_string() if caps else "?"
                ),
                flush=True,
            )
            self.last_report = now

        return Gst.FlowReturn.OK

    def run(self):
        self.connect()
        self.build()
        try:
            self.loop.run()
        finally:
            self.ctrl_stop.set()
            if self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)
            try:
                self.ws.close()
            except Exception:
                pass
            try:
                self.ctrl_sock.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", required=True)
    p.add_argument("--stun", default="")
    args = p.parse_args()
    Receiver(args.broker, args.stun).run()


if __name__ == "__main__":
    main()
