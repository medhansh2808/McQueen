#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import queue
import sys
import threading
import time

import websocket
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstSdp', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GLib, Gst, GstSdp, GstWebRTC

Gst.init(None)


def mono_ns():
    return int(time.monotonic() * 1000000000)


class JetsonPeer(object):
    def __init__(self, args):
        self.args = args
        self.loop = GLib.MainLoop()
        self.ws = None
        self.ws_lock = threading.Lock()
        self.meta_q = queue.Queue(maxsize=120)
        self.frame_id = 0
        self.last_latency_print = 0
        self.pipeline = None
        self.webrtc = None

    def send(self, payload):
        text = json.dumps(payload, separators=(',', ':'))
        with self.ws_lock:
            if self.ws is not None:
                self.ws.send(text)

    def meta_sender(self):
        while True:
            item = self.meta_q.get()
            if item is None:
                return
            try:
                self.send(item)
            except Exception as exc:
                print('[JETSON] frame_meta send failed: {}'.format(exc), flush=True)

    def recv_loop(self):
        while True:
            try:
                raw = self.ws.recv()
                if raw is None:
                    raise RuntimeError('broker closed')
                data = json.loads(raw)
                GLib.idle_add(self.handle_message, data)
            except Exception as exc:
                print('[JETSON] broker receive ended: {}'.format(exc), flush=True)
                GLib.idle_add(self.loop.quit)
                return

    def connect_broker(self):
        print('[JETSON] connecting broker {}'.format(self.args.broker), flush=True)
        self.ws = websocket.create_connection(self.args.broker, timeout=10)
        # timeout=10 is useful only for initial connect.  After connection,
        # recv() must block indefinitely or the peer exits after 10 seconds.
        self.ws.settimeout(None)
        print('[JETSON] broker connected', flush=True)
        threading.Thread(target=self.recv_loop, daemon=True).start()
        threading.Thread(target=self.meta_sender, daemon=True).start()

    def build_pipeline(self):
        cam = self.args.camera
        if self.args.codec == 'h264':
            encoder = (
                'nvv4l2h264enc bitrate={bitrate} iframeinterval={iframe} ! '
                'h264parse config-interval=-1 ! '
                'rtph264pay name=pay config-interval=-1 pt=96'
            ).format(bitrate=self.args.bitrate, iframe=self.args.iframe)
        else:
            encoder = (
                'nvv4l2vp8enc bitrate={bitrate} ! '
                'rtpvp8pay name=pay pt=96'
            ).format(bitrate=self.args.bitrate)

        # GStreamer 1.14 webrtcbin uses a REQUEST sink pad.
        # Build the RTP chain separately, then explicitly link pay -> sink_%u.
        desc = (
            'webrtcbin name=webrtc '
            'v4l2src name=cam device={cam} ! '
            'image/jpeg,width={w},height={h},framerate={fps}/1 ! '
            'jpegparse ! nvv4l2decoder mjpeg=1 ! nvvidconv ! '
            'video/x-raw(memory:NVMM),format=NV12 ! '
            '{encoder}'
        ).format(cam=cam, w=self.args.width, h=self.args.height, fps=self.args.fps, encoder=encoder)

        print('[JETSON] pipeline codec={} {}x{}@{} bitrate={}'.format(self.args.codec, self.args.width, self.args.height, self.args.fps, self.args.bitrate), flush=True)
        self.pipeline = Gst.parse_launch(desc)
        self.webrtc = self.pipeline.get_by_name('webrtc')
        pay = self.pipeline.get_by_name('pay')

        if self.webrtc is None or pay is None:
            raise RuntimeError('failed to create webrtc/pay elements')

        webrtc_sink = self.webrtc.get_request_pad('sink_%u')
        if webrtc_sink is None:
            raise RuntimeError('webrtcbin did not provide sink_%u request pad')

        pay_src = pay.get_static_pad('src')
        if pay_src is None:
            raise RuntimeError('RTP payloader has no src pad')

        link_result = pay_src.link(webrtc_sink)
        if link_result != Gst.PadLinkReturn.OK:
            raise RuntimeError('pay -> webrtc link failed: {}'.format(link_result))

        print('[JETSON] RTP -> webrtc linked on {}'.format(
            webrtc_sink.get_name()), flush=True)
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)

        if self.args.stun:
            self.webrtc.set_property('stun-server', self.args.stun)
        if self.args.turn:
            self.webrtc.set_property('turn-server', self.args.turn)

        cam_el = self.pipeline.get_by_name('cam')
        srcpad = cam_el.get_static_pad('src')
        srcpad.add_probe(Gst.PadProbeType.BUFFER, self.on_camera_buffer)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_bus_message)

    def on_camera_buffer(self, pad, info):
        self.frame_id += 1
        payload = {
            'type': 'frame_meta',
            'frame_id': self.frame_id,
            'capture_mono_ns': mono_ns(),
            'width': self.args.width,
            'height': self.args.height,
            'source_fps': self.args.fps,
        }
        try:
            self.meta_q.put_nowait(payload)
        except queue.Full:
            try:
                self.meta_q.get_nowait()
                self.meta_q.put_nowait(payload)
            except Exception:
                pass
        return Gst.PadProbeReturn.OK

    def on_bus_message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            print('[JETSON] GST ERROR: {} {}'.format(err, dbg), flush=True)
            self.loop.quit()
        elif message.type == Gst.MessageType.EOS:
            print('[JETSON] GST EOS', flush=True)
            self.loop.quit()

    def on_negotiation_needed(self, element):
        print('[JETSON] negotiation needed -> creating offer', flush=True)
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, None, None)
        self.webrtc.emit('create-offer', None, promise)

    def on_offer_created(self, promise, _user_data, _unused):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        self.webrtc.emit('set-local-description', offer, Gst.Promise.new())
        self.send({'type': 'offer', 'sdp': offer.sdp.as_text()})
        print('[JETSON] offer sent', flush=True)

    def on_ice_candidate(self, element, mlineindex, candidate):
        self.send({'type': 'ice', 'mline': int(mlineindex), 'candidate': candidate or ''})

    def parse_sdp(self, text):
        # Python GI on the Jetson's GStreamer 1.14 stack exposes the
        # older 2-argument wrapper: parse_buffer(bytes, SDPMessage).
        result, msg = GstSdp.SDPMessage.new()
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError('SDPMessage.new failed: {}'.format(result))
        data = bytes(text.encode('utf-8'))
        result = GstSdp.sdp_message_parse_buffer(data, msg)
        if result != GstSdp.SDPResult.OK:
            raise RuntimeError('SDP parse failed: {}'.format(result))
        return msg

    def handle_message(self, data):
        typ = data.get('type')
        try:
            if typ == 'answer':
                sdpmsg = self.parse_sdp(data['sdp'])
                answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
                self.webrtc.emit('set-remote-description', answer, Gst.Promise.new())
                print('[JETSON] answer applied', flush=True)
            elif typ == 'ice':
                candidate = data.get('candidate', '')
                if candidate:
                    # Be defensive with peers which send only the candidate
                    # body.  GStreamer expects "candidate:..." here.
                    if not candidate.startswith('candidate:'):
                        candidate = 'candidate:' + candidate
                    print('[JETSON] add ICE mline={} {}'.format(
                        int(data.get('mline', 0)),
                        candidate[:80]
                    ), flush=True)
                    self.webrtc.emit(
                        'add-ice-candidate',
                        int(data.get('mline', 0)),
                        candidate
                    )
            elif typ == 'control':
                capture_ns = int(data.get('capture_mono_ns', 0) or 0)
                now_ns = mono_ns()
                if capture_ns:
                    total_ms = (now_ns - capture_ns) / 1e6
                    if now_ns - self.last_latency_print > 500000000:
                        print('[JETSON] control frame={} servo={} pwm={} FULL capture->RTX->return={:.1f} ms'.format(
                            data.get('frame_id'), data.get('servo_angle_deg'), data.get('motor_pwm'), total_ms), flush=True)
                        self.last_latency_print = now_ns
                else:
                    print('[JETSON] control {}'.format(data), flush=True)
            elif typ == 'peer':
                print('[JETSON] peer {} {}'.format(data.get('role'), data.get('state')), flush=True)
        except Exception as exc:
            print('[JETSON] message handling error type={}: {}'.format(typ, exc), flush=True)
        return False

    def run(self):
        self.connect_broker()
        self.build_pipeline()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print('[JETSON] pipeline PLAYING result={}'.format(ret), flush=True)
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            if self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)
            try:
                self.meta_q.put_nowait(None)
            except Exception:
                pass
            with self.ws_lock:
                if self.ws is not None:
                    try:
                        self.ws.close()
                    except Exception:
                        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--broker', required=True, help='ws://HOST:PORT/ws?role=jetson&session=mcqueen')
    p.add_argument('--camera', default='/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Lenovo_FHD_Webcam_Audio_SN0001-video-index0')
    p.add_argument('--codec', choices=['h264', 'vp8'], default='h264')
    p.add_argument('--width', type=int, default=1280)
    p.add_argument('--height', type=int, default=720)
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--bitrate', type=int, default=2500000)
    p.add_argument('--iframe', type=int, default=15)
    p.add_argument('--stun', default='')
    p.add_argument('--turn', default='')
    args = p.parse_args()
    JetsonPeer(args).run()


if __name__ == '__main__':
    main()
