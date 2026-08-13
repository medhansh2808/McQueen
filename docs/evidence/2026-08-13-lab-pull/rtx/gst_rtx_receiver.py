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


class Receiver(object):
    def __init__(self, broker):
        self.broker = broker
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

    def send(self, data):
        payload = json.dumps(data, separators=(",", ":"))
        with self.ws_lock:
            self.ws.send(payload)

    def connect(self):
        print("[RTX-GST] broker connecting {}".format(self.broker), flush=True)
        self.ws = websocket.create_connection(self.broker, timeout=10)
        self.ws.settimeout(None)
        print("[RTX-GST] broker connected", flush=True)
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

        if now - self.last_report >= 1.0:
            elapsed = max(now - self.started, 0.001)
            fps = self.frames / elapsed
            caps = sample.get_caps()
            print(
                "[RTX-GST] VIDEO frames={} avg_fps={:.1f} caps={}".format(
                    self.frames, fps, caps.to_string() if caps else "?"
                ),
                flush=True,
            )
            self.last_report = now

        if self.frames % 5 == 0:
            with self.meta_lock:
                meta = dict(self.latest_meta)

            if meta.get("capture_mono_ns"):
                self.send({
                    "type": "control",
                    "frame_id": meta.get("frame_id"),
                    "capture_mono_ns": meta.get("capture_mono_ns"),
                    "servo_angle_deg": 90.0,
                    "motor_pwm": 0,
                    "source": "gst-upstream-test",
                })

        return Gst.FlowReturn.OK

    def run(self):
        self.connect()
        self.build()
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
    Receiver(args.broker).run()


if __name__ == "__main__":
    main()
