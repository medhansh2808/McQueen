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
    def __init__(self, broker):
        self.broker = broker
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
        print("[JETSON-GST] broker connecting {}".format(self.broker), flush=True)
        self.ws = websocket.create_connection(self.broker, timeout=10)
        self.ws.settimeout(None)
        print("[JETSON-GST] broker connected", flush=True)
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
                print("[JETSON-GST] broker recv ended: {}".format(exc), flush=True)
                GLib.idle_add(self.loop.quit)
                return

    def build(self):
        # This follows the established GStreamer 1.14-era sendrecv demo structure.
        # No camera is required: use a live generated test pattern.
        desc = (
            "webrtcbin name=sendrecv "
            "videotestsrc name=vsrc is-live=true pattern=ball ! "
            "video/x-raw,width=640,height=360,framerate=20/1 ! "
            "videoconvert ! queue ! "
            "vp8enc deadline=1 ! "
            "rtpvp8pay pt=97 ! queue ! "
            "application/x-rtp,media=video,encoding-name=VP8,payload=97 ! "
            "sendrecv."
        )

        print("[JETSON-GST] pipeline: videotestsrc -> VP8 -> webrtcbin", flush=True)
        self.pipeline = Gst.parse_launch(desc)
        self.webrtc = self.pipeline.get_by_name("sendrecv")

        if self.webrtc is None:
            raise RuntimeError("webrtcbin missing from pipeline")

        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.webrtc.connect("on-ice-candidate", self.on_ice_candidate)

        try:
            self.webrtc.connect("notify::ice-connection-state", self.on_ice_state)
        except Exception:
            pass

        vsrc = self.pipeline.get_by_name("vsrc")
        pad = vsrc.get_static_pad("src")
        pad.add_probe(Gst.PadProbeType.BUFFER, self.on_frame)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

    def on_ice_state(self, element, pspec):
        try:
            state = element.get_property("ice-connection-state")
            print("[JETSON-GST] ICE {}".format(state), flush=True)
        except Exception:
            pass

    def on_frame(self, pad, info):
        self.frame_id += 1
        if self.frame_id % 2 == 0:
            try:
                self.send({
                    "type": "frame_meta",
                    "frame_id": self.frame_id,
                    "capture_mono_ns": mono_ns(),
                    "source": "videotestsrc",
                    "width": 640,
                    "height": 360,
                    "fps": 20,
                })
            except Exception:
                pass
        return Gst.PadProbeReturn.OK

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[JETSON-GST] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()
        elif msg.type == Gst.MessageType.EOS:
            print("[JETSON-GST] EOS", flush=True)
            self.loop.quit()

    def on_negotiation_needed(self, element):
        print("[JETSON-GST] negotiation needed", flush=True)
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
        print("[JETSON-GST] offer sent", flush=True)

    def on_ice_candidate(self, element, mline, candidate):
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
                print("[JETSON-GST] answer applied", flush=True)

            elif typ == "ice":
                cand = data.get("candidate", "")
                if cand:
                    self.webrtc.emit(
                        "add-ice-candidate",
                        int(data.get("mline", 0)),
                        cand,
                    )

            elif typ == "control":
                capture = int(data.get("capture_mono_ns", 0) or 0)
                if capture:
                    now = mono_ns()
                    total_ms = (now - capture) / 1000000.0
                    if now - self.last_latency_print > 500000000:
                        print(
                            "[JETSON-GST] CONTROL frame={} TEST-LOOP={:.1f} ms".format(
                                data.get("frame_id"), total_ms
                            ),
                            flush=True,
                        )
                        self.last_latency_print = now

            elif typ == "peer":
                print(
                    "[JETSON-GST] peer {} {}".format(
                        data.get("role"), data.get("state")
                    ),
                    flush=True,
                )
        except Exception as exc:
            print(
                "[JETSON-GST] message error type={}: {}".format(typ, exc),
                flush=True,
            )
        return False

    def run(self):
        self.connect()
        self.build()

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[JETSON-GST] PLAYING {}".format(ret), flush=True)

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
    args = p.parse_args()
    Sender(args.broker).run()


if __name__ == "__main__":
    main()
