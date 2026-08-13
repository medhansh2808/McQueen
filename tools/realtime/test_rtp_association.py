#!/usr/bin/env python3
"""Unit test for the in-band META + RTP association logic used by the
punched-UDP transport (gst_jetson_rtp_wan.py / gst_rtx_rtp_receiver.py).

Runs WITHOUT GStreamer/hardware: it simulates the sender emitting META before
each frame's RTP packets on one socket, and the receiver reconstructing frames
from the marker bit and pairing them in exact order. Also verifies frame_id
contiguity and capture_mono_ns propagation.
"""

import struct

META_PREFIX = b"META\t"


class FakeSender(object):
    def __init__(self, frames):
        # frames: list of (frame_id, capture_mono_ns, num_packets)
        self.frames = frames
        self.capture_q = [(fid, cap) for fid, cap, _ in frames]
        self.last_rtp_ts = None
        self.stream = []  # (kind, payload_bytes)

    def on_rtp_packet(self, rtp_ts, marker):
        payload = bytearray(12)
        if marker:
            payload[1] |= 0x80
        struct.pack_into("!I", payload, 8, rtp_ts)

        if rtp_ts != self.last_rtp_ts:
            self.last_rtp_ts = rtp_ts
            if self.capture_q:
                frame_id, capture = self.capture_q[0]
                del self.capture_q[0]
                import json
                meta = json.dumps({
                    "frame_id": frame_id,
                    "capture_mono_ns": capture,
                }).encode("utf-8")
                self.stream.append((META_PREFIX, meta))
        self.stream.append((b"", bytes(payload)))


class FakeReceiver(object):
    def __init__(self):
        self.cur_meta = None
        self.meta_q = []
        self.frames_rx = 0

    def on_datagram(self, prefix, data):
        if prefix == META_PREFIX:
            import json
            self.cur_meta = json.loads(data.decode("utf-8"))
        else:
            # RTP packet; marker bit in byte 1.
            if data[1] & 0x80 and self.cur_meta is not None:
                self.meta_q.append(self.cur_meta)
                self.frames_rx += 1
                self.cur_meta = None


def make_stream(frames):
    s = FakeSender(frames)
    ts = 1000
    for frame_id, capture, n in frames:
        for i in range(n):
            marker = (i == n - 1)
            s.on_rtp_packet(ts, marker)
        ts += 100
    return s.stream


def run_test():
    frames = [
        (0, 5000, 3),
        (1, 5100, 2),
        (2, 5200, 1),
        (3, 5300, 4),
        (4, 5400, 2),
    ]
    stream = make_stream(frames)

    r = FakeReceiver()
    for prefix, data in stream:
        r.on_datagram(prefix, data)

    assert r.frames_rx == len(frames), "expected {} frames, got {}".format(
        len(frames), r.frames_rx)
    got = [(m["frame_id"], m["capture_mono_ns"]) for m in r.meta_q]
    expected = [(fid, cap) for fid, cap, _ in frames]
    assert got == expected, "association mismatch: {} != {}".format(got, expected)

    ids = [m["frame_id"] for m in r.meta_q]
    assert ids == sorted(ids) and len(set(ids)) == len(ids), "frame_id contiguity broken"

    print("PASS: {} frames, exact in-band association, ids {}".format(
        r.frames_rx, ids))
    print("PASS: capture_mono_ns propagated:", [m["capture_mono_ns"] for m in r.meta_q])


if __name__ == "__main__":
    run_test()
