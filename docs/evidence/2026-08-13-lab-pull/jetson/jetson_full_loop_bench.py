#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import threading
import time
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



def mono_ns():
    return int(time.monotonic() * 1000000000)


class Sender(object):
    def __init__(self, broker, device, stun):
        self.broker = broker
        self.device = device
        self.stun = stun
        self.ws = None
        self.ws_lock = threading.Lock()
        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.webrtc = None
        self.frame_id = 0
        self.last_latency_print = 0
        self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ctrl_sock.bind(("0.0.0.0", 0))
        self.ctrl_sock.settimeout(0.20)
        self.ctrl_public = stun_public(self.ctrl_sock)
        self.ctrl_peer = None
        self.ctrl_lock = threading.Lock()
        self.ctrl_stop = threading.Event()
        self.full_loop_ms = []
        self.last_ctrl_seq = -1

    def send(self, data):
        payload = json.dumps(data, separators=(",", ":"))
        with self.ws_lock:
            self.ws.send(payload)

    def connect(self):
        print("[JETSON-CAM] broker connecting {}".format(self.broker), flush=True)
        self.ws = websocket.create_connection(self.broker, timeout=10)
        self.ws.settimeout(None)
        print("[JETSON-CAM] broker connected", flush=True)
        print("[JETSON-CAM] CONTROL_UDP public {}:{}".format(
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
                    "role": "jetson",
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
                data, addr = self.ctrl_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                return

            if data.startswith(b"CTRL_BENCH "):
                try:
                    msg = json.loads(data[11:].decode("utf-8"))
                    seq = int(msg.get("seq", -1))
                    capture_ns = int(msg["capture_mono_ns"])
                    servo = float(msg["servo_angle_deg"])
                    pwm = int(msg["motor_pwm"])
                    infer_ms = float(msg.get("infer_ms", 0.0))

                    # Dry-run actuator boundary: validate newest command and bounds.
                    if seq <= self.last_ctrl_seq:
                        continue
                    self.last_ctrl_seq = seq
                    if not (45.0 <= servo <= 115.0):
                        continue
                    if not (-70 <= pwm <= 100):
                        continue

                    total_ms = (mono_ns() - capture_ns) / 1000000.0
                    if total_ms < 0 or total_ms > 5000:
                        continue
                    self.full_loop_ms.append(total_ms)

                    try:
                        self.ctrl_sock.sendto(
                            ("ACK_BENCH {}".format(seq)).encode("ascii"), addr
                        )
                    except Exception:
                        pass

                    print(
                        "[JETSON-CAM] FULL_LOOP seq={} frame={} total={:.1f}ms "
                        "infer={:.2f}ms servo={:.1f} pwm={} ACCEPTED_DRYRUN".format(
                            seq, msg.get("frame_id"), total_ms, infer_ms, servo, pwm
                        ),
                        flush=True,
                    )
                except Exception as exc:
                    print("[JETSON-CAM] CTRL_BENCH parse error {}".format(exc), flush=True)

    def recv_loop(self):
        while True:
            try:
                raw = self.ws.recv()
                if raw is None:
                    raise RuntimeError("broker closed")
                data = json.loads(raw)
                GLib.idle_add(self.handle_message, data)
            except Exception as exc:
                print("[JETSON-CAM] broker recv ended: {}".format(exc), flush=True)
                GLib.idle_add(self.loop.quit)
                return

    def build(self):
        # Already-proven Jetson camera path:
        # Lenovo webcam MJPEG 1280x720@30
        # -> NVIDIA hardware MJPEG decode
        # -> NVMM NV12
        # -> NVIDIA hardware H.264 encode
        # -> RTP H.264
        # -> GStreamer webrtcbin.
        desc = (
            "webrtcbin name=sendrecv "
            "v4l2src name=vsrc device={} do-timestamp=true ! "
            "image/jpeg,width=1280,height=720,framerate=30/1 ! "
            "jpegparse ! "
            "nvv4l2decoder mjpeg=1 ! "
            "nvvidconv ! "
            "video/x-raw(memory:NVMM),format=NV12,width=640,height=360 ! "
            "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream ! "
            "nvv4l2h264enc bitrate=800000 iframeinterval=10 ! "
            "h264parse config-interval=-1 ! "
            "rtph264pay pt=96 config-interval=-1 ! "
            "application/x-rtp,media=video,encoding-name=H264,payload=96 ! "
            "sendrecv."
        ).format(self.device)

        print("[JETSON-CAM] camera {}".format(self.device), flush=True)
        print(
            "[JETSON-CAM] pipeline: Lenovo MJPEG 1280x720@30 -> NVDEC -> scale 640x360 -> NVENC H264 800kbps -> WebRTC",
            flush=True,
        )

        self.pipeline = Gst.parse_launch(desc)
        self.webrtc = self.pipeline.get_by_name("sendrecv")

        if self.webrtc is None:
            raise RuntimeError("webrtcbin missing from pipeline")

        if self.stun:
            self.webrtc.set_property("stun-server", self.stun)
            print("[JETSON-CAM] STUN {}".format(self.stun), flush=True)

        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.webrtc.connect("on-ice-candidate", self.on_ice_candidate)

        try:
            self.webrtc.connect("notify::ice-connection-state", self.on_ice_state)
        except Exception:
            pass

        vsrc = self.pipeline.get_by_name("vsrc")
        if vsrc is None:
            raise RuntimeError("v4l2src missing from pipeline")

        pad = vsrc.get_static_pad("src")
        if pad is None:
            raise RuntimeError("v4l2src src pad missing")

        pad.add_probe(Gst.PadProbeType.BUFFER, self.on_frame)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

    def on_ice_state(self, element, pspec):
        try:
            state = element.get_property("ice-connection-state")
            print("[JETSON-CAM] ICE {}".format(state), flush=True)
        except Exception:
            pass

    def on_frame(self, pad, info):
        self.frame_id += 1
        capture_ns = mono_ns()

        with self.ctrl_lock:
            peer = self.ctrl_peer

        if peer is not None:
            try:
                meta = {
                    "frame_id": self.frame_id,
                    "capture_mono_ns": capture_ns,
                }
                self.ctrl_sock.sendto(
                    b"META_BENCH " + json.dumps(meta, separators=(",", ":")).encode("utf-8"),
                    peer,
                )
            except Exception:
                pass

        return Gst.PadProbeReturn.OK

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[JETSON-CAM] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()
        elif msg.type == Gst.MessageType.EOS:
            print("[JETSON-CAM] EOS", flush=True)
            self.loop.quit()

    def on_negotiation_needed(self, element):
        print("[JETSON-CAM] negotiation needed", flush=True)
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, None, None)
        self.webrtc.emit("create-offer", None, promise)

    def on_offer_created(self, promise, unused1, unused2):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")

        if offer is None:
            raise RuntimeError("create-offer returned no offer")

        p = Gst.Promise.new()
        self.webrtc.emit("set-local-description", offer, p)
        p.interrupt()

        self.send({"type": "offer", "sdp": offer.sdp.as_text()})
        print("[JETSON-CAM] offer sent", flush=True)

    def on_ice_candidate(self, element, mline, candidate):
        if candidate:
            kind = "srflx" if " typ srflx " in (" " + candidate + " ") else ("relay" if " typ relay " in (" " + candidate + " ") else "host/other")
            print("[JETSON-CAM] LOCAL ICE {} {}".format(kind, candidate), flush=True)
        self.send({
            "type": "ice",
            "mline": int(mline),
            "candidate": candidate or "",
        })

    def parse_sdp(self, text):
        result, msg = GstSdp.SDPMessage.new()
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError("SDPMessage.new failed: {}".format(result))

        result = GstSdp.sdp_message_parse_buffer(bytes(text.encode("utf-8")), msg)
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError("SDP parse failed: {}".format(result))

        return msg

    def handle_message(self, data):
        typ = data.get("type")

        try:
            if typ == "answer":
                msg = self.parse_sdp(data["sdp"])
                answer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.ANSWER, msg
                )

                p = Gst.Promise.new()
                self.webrtc.emit("set-remote-description", answer, p)
                p.interrupt()

                print("[JETSON-CAM] answer applied", flush=True)

            elif typ == "ice":
                candidate = data.get("candidate", "")
                if candidate:
                    self.webrtc.emit(
                        "add-ice-candidate",
                        int(data.get("mline", 0)),
                        candidate,
                    )

            elif typ == "bench_udp_candidate" and data.get("role") == "rtx":
                peer = (str(data["ip"]), int(data["port"]))
                with self.ctrl_lock:
                    if peer != self.ctrl_peer:
                        self.ctrl_peer = peer
                        print("[JETSON-CAM] CONTROL_UDP peer {}:{}".format(
                            peer[0], peer[1]), flush=True)

            elif typ == "control":
                capture = int(data.get("capture_mono_ns", 0) or 0)
                if capture:
                    now = mono_ns()
                    total_ms = (now - capture) / 1000000.0

                    if now - self.last_latency_print > 500000000:
                        print(
                            "[JETSON-CAM] CONTROL frame={} CAMERA-LOOP={:.1f} ms".format(
                                data.get("frame_id"), total_ms
                            ),
                            flush=True,
                        )
                        self.last_latency_print = now

            elif typ == "peer":
                print(
                    "[JETSON-CAM] peer {} {}".format(
                        data.get("role"), data.get("state")
                    ),
                    flush=True,
                )

        except Exception as exc:
            print(
                "[JETSON-CAM] message error type={}: {}".format(typ, exc),
                flush=True,
            )

        return False

    def run(self):
        self.connect()
        self.build()

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[JETSON-CAM] PLAYING {}".format(ret), flush=True)

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
    p.add_argument("--device", required=True)
    p.add_argument("--stun", default="")
    args = p.parse_args()

    Sender(args.broker, args.device, args.stun).run()


if __name__ == "__main__":
    main()
