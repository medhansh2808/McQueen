#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import threading
import time

import websocket
import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstSdp", "1.0")
gi.require_version("GstWebRTC", "1.0")

from gi.repository import GLib, Gst, GstSdp, GstWebRTC

Gst.init(None)


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

    def send(self, data):
        payload = json.dumps(data, separators=(",", ":"))
        with self.ws_lock:
            self.ws.send(payload)

    def connect(self):
        print("[JETSON-CAM] broker connecting {}".format(self.broker), flush=True)
        self.ws = websocket.create_connection(self.broker, timeout=10)
        self.ws.settimeout(None)
        print("[JETSON-CAM] broker connected", flush=True)

        t = threading.Thread(target=self.recv_loop)
        t.daemon = True
        t.start()

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

        # Metadata is intentionally lightweight and sent every second frame.
        # This timestamp is on the Jetson, so echoed return latency is valid.
        if self.frame_id % 2 == 0:
            try:
                self.send({
                    "type": "frame_meta",
                    "frame_id": self.frame_id,
                    "capture_mono_ns": mono_ns(),
                    "source": "lenovo-camera",
                    "width": 640,
                    "height": 360,
                    "fps": 30,
                    "codec": "h264",
                })
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
            if self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)

            try:
                self.ws.close()
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
