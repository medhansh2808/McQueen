#!/usr/bin/env python3
"""appsrc_rtp_ts_test.py — isolate whether rtph264pay emits per-frame RTP
timestamps. Pushes synthetic I420 frames with incrementing PTS into appsrc,
then counts how many distinct RTP timestamps rtph264pay produces.

Answers: is the constant-rtp_ts bug in (a) my appsrc PTS handling, or (b) the
x264enc/rtph264pay chain on this GStreamer stack?
"""
from __future__ import print_function
import time
import gi
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst
Gst.init(None)

W, H, FPS = 640, 480, 30
FRAME_NS = int(1e9 / FPS)

ts_set = set()
n_bufs = 0
markers = 0


def on_probe(pad, info):
    global n_bufs, markers
    buf = info.get_buffer()
    if buf is None:
        return Gst.PadProbeReturn.OK
    ok, m = buf.map(Gst.MapFlags.READ)
    if ok:
        import struct
        if len(m.data) >= 12:
            ts = struct.unpack("!I", m.data[8:12])[0]
            ts_set.add(ts)
            if m.data[1] & 0x80:
                markers += 1
        buf.unmap(m)
    n_bufs += 1
    return Gst.PadProbeReturn.OK


pipe_desc = (
    "appsrc name=src is-live=false format=time do-timestamp=false "
    "caps=video/x-raw,format=I420,width={},height={},framerate={}/1 ! "
    "x264enc tune=zerolatency bitrate=2500 speed-preset=ultrafast "
    "key-int-max=30 ! "
    "h264parse config-interval=-1 ! "
    "rtph264pay name=pay pt=96 config-interval=-1 perfect-rtptime=true ! "
    "fakesink"
).format(W, H, FPS)

pipe = Gst.parse_launch(pipe_desc)
appsrc = pipe.get_by_name("src")
pay = pipe.get_by_name("pay")
pay.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, on_probe)

ret = pipe.set_state(Gst.State.PLAYING)
print("PLAYING", ret)

frame = bytearray(W * H * 3 // 2)  # one I420 frame (zeros)
pts = int(time.monotonic() * 1e9)
for n in range(90):
    buf = Gst.Buffer.new_allocate(None, len(frame), None)
    buf.fill(0, bytes(frame))
    buf.pts = pts
    buf.duration = FRAME_NS
    appsrc.emit("push-buffer", buf)
    pts += FRAME_NS
    time.sleep(0.02)  # pace ~ like live capture

appsrc.emit("end-of-stream")
time.sleep(1.0)
pipe.set_state(Gst.State.NULL)

print("RESULT bufs={} distinct_rtp_ts={} markers={}".format(
    n_bufs, len(ts_set), markers))
if len(ts_set) > 1:
    print("PASS: rtp_ts changes per frame -> appsrc/appsrc PTS is the bug")
else:
    print("FAIL: rtp_ts constant even with synthetic input -> x264/rtph264pay chain")
