#!/usr/bin/env python3
"""test_rtp_packetization.py — offline unit test of the fixed Jetson sender's
manual H.264/RTP packetization (gst_jetson_rtp_wan.py).

Runs on the laptop with NO GStreamer pipeline, NO camera, NO Jetson/RTX
hardware: `websocket` is stubbed so the sender module imports (gi/Gst ARE
present on the laptop), and the pure packetization path
(_on_rtp_probe / _split_nals / _send_rtp) is exercised against a loopback
UDP socket. This locks in the exact 2026-08-13 lab defect fixes:

  F1: rtp_ts advances by rtp_ts_step every frame (the `% 30 < n` NameError
      froze it at 0 -> every frame sent with ts=0 -> rtph264depay merged all
      frames into one AU).
  F3: AUD NALs (type 9) are dropped; FU-A fragments carry S=1 on the first /
      E=1 on the last fragment; the RTP marker bit is set ONLY on the last
      packet of a frame (old sender set marker on EVERY packet -> depay
      flushed each fragment as a complete frame -> "waiting for start").
  #9: exactly ONE capture_q entry is consumed per frame; META precedes that
      frame's RTP packets on the same socket (exact in-band association).
"""

import json
import socket
import struct
import sys
import threading
import time
import types

# --- stub websocket so the sender module imports on the laptop ---------------
_ws = types.ModuleType("websocket")
_ws.create_connection = lambda *a, **k: None
sys.modules["websocket"] = _ws

from gst_jetson_rtp_wan import Sender, META_PREFIX, Gst  # noqa: E402

MTU = 1200
TS_STEP = 3000  # 90000/30
SSRC = 0x4D515545


def make_sender():
    """Build a Sender instance without __init__ (no STUN/broker/camera)."""
    s = object.__new__(Sender)
    s.args = None
    s.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sock.bind(("127.0.0.1", 0))
    s.peer = None
    s.rtp_seq = 0
    s.rtp_ssrc = SSRC
    s.rtp_ts = 0
    s.rtp_ts_step = TS_STEP
    s.rtp_mtu = MTU
    s.capture_q = []
    s.capture_lock = threading.Lock()
    s.sent_pkts = 0
    s.sent_meta = 0
    s.sent_bytes = 0
    s.started = time.monotonic()
    return s


def run_au(s, au):
    """Feed one h264parse AU through the committed sender's packetization
    entry point (_on_rtp_probe, the pad-probe handler) with a real
    Gst.Buffer so the offline tests exercise the exact deployed code path."""
    buf = Gst.Buffer.new_allocate(None, len(au), None)
    buf.fill(0, au)
    s._on_rtp_probe(None, types.SimpleNamespace(get_buffer=lambda: buf))


def make_recv():
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    r.bind(("127.0.0.1", 0))
    r.settimeout(0.3)
    return r


def drain(recv):
    pkts = []
    while True:
        try:
            data, _ = recv.recvfrom(4096)
            pkts.append(data)
        except socket.timeout:
            return pkts


def nal(ntype, payload):
    return bytes([0x60 | (ntype & 0x1F)]) + payload  # NRI=3, type=ntype


def make_au(nals_with_sc):
    """Join [(nal_bytes, start_code_len)] into one byte-stream AU."""
    out = b""
    for n, sc in nals_with_sc:
        out += (b"\x00\x00\x00\x01" if sc == 4 else b"\x00\x00\x01") + n
    return out


def parse_rtp(pkt):
    assert len(pkt) >= 12, "short RTP packet"
    v, b1, seq, ts, ssrc = struct.unpack("!BBHII", pkt[:12])
    assert v == 0x80, "RTP version/header flags wrong: %#x" % v
    return {
        "marker": bool(b1 & 0x80),
        "pt": b1 & 0x7F,
        "seq": seq,
        "ts": ts,
        "ssrc": ssrc,
    }


# --------------------------------------------------------------------------
# 1. _split_nals: start codes handled, AUD dropped, NAL type preserved
# --------------------------------------------------------------------------
def test_split_nals():
    sps = nal(7, b"\xAA" * 10)
    pps = nal(8, b"\xBB" * 5)
    aud = nal(9, b"\x10")
    idr = nal(5, b"\xCC" * 50)
    au = make_au([(sps, 4), (pps, 3), (aud, 4), (idr, 3)])
    nals = Sender._split_nals(au)
    types = [n[0] & 0x1F for n in nals]
    assert types == [7, 8, 5], "AUD not dropped / types wrong: %r" % types
    for n in nals:
        assert not n.startswith(b"\x00\x00\x01") and not n.startswith(b"\x00\x00\x00\x01"), \
            "start code leaked into NAL"
    print("PASS test_split_nals: SPS/PPS/IDR kept, AUD dropped, no start codes")


# --------------------------------------------------------------------------
# 2. Single small frame: META first, marker on only packet, ts advances
# --------------------------------------------------------------------------
def test_single_small_frame():
    s = make_sender()
    r = make_recv()
    s.peer = r.getsockname()
    s.capture_q = [(0, 123456)]
    idr = nal(5, b"\xCC" * 100)  # 101 bytes <= MTU -> single packet
    run_au(s, make_au([(idr, 4)]))

    pkts = drain(r)
    assert len(pkts) == 2, "expected META + 1 RTP, got %d" % len(pkts)
    assert pkts[0].startswith(META_PREFIX), "META must precede RTP"
    meta = json.loads(pkts[0][len(META_PREFIX):])
    assert meta["frame_id"] == 0 and meta["capture_mono_ns"] == 123456
    assert meta["rtp_ts"] == 0

    h = parse_rtp(pkts[1])
    assert h["marker"] is True, "marker must be set on the only packet of a frame"
    assert h["pt"] == 96
    assert h["ts"] == 0
    assert h["seq"] == 0
    assert h["ssrc"] == SSRC

    assert s.rtp_ts == TS_STEP, "rtp_ts must advance by one frame step (F1)"
    assert s.sent_meta == 1 and s.sent_pkts == 1
    assert s.capture_q == [], "exactly one capture entry consumed per frame"
    print("PASS test_single_small_frame: META first, marker correct, rtp_ts += %d" % TS_STEP)


# --------------------------------------------------------------------------
# 3. Large NAL -> FU-A: S=1 first, E=1 last, marker only on last fragment
# --------------------------------------------------------------------------
def test_fu_a_fragmentation():
    s = make_sender()
    r = make_recv()
    s.peer = r.getsockname()
    s.capture_q = [(0, 1)]
    big_idr = nal(5, b"\xDD" * 3000)  # 3001 bytes -> 3 FU-A fragments
    run_au(s, make_au([(big_idr, 4)]))

    pkts = drain(r)
    rtps = [p for p in pkts if not p.startswith(META_PREFIX)]
    assert len(rtps) == 3, "expected 3 FU-A fragments, got %d" % len(rtps)

    for i, p in enumerate(rtps):
        h = parse_rtp(p)
        assert h["ts"] == 0, "all fragments of a frame share one RTP ts"
        assert h["seq"] == i, "RTP seq must increment per packet"
        assert h["ssrc"] == SSRC
        fu_ind, fu_hdr = p[12], p[13]
        assert (fu_ind & 0x1F) == 28, "FU-A indicator type 28 required"
        assert (fu_hdr & 0x1F) == 5, "FU header must carry NAL type 5"
        s_bit = bool(fu_hdr & 0x80)
        e_bit = bool(fu_hdr & 0x40)
        assert s_bit == (i == 0), "S=1 only on first fragment"
        assert e_bit == (i == 2), "E=1 only on last fragment"
        marker = h["marker"]
        assert marker == (i == 2), "marker bit only on the LAST packet (F3)"
        assert h["pt"] == 96

    assert s.rtp_ts == TS_STEP
    print("PASS test_fu_a_fragmentation: 3 fragments, S/E bits + marker only on last")


# --------------------------------------------------------------------------
# 4. Multi-frame: per-frame ts, one META per frame, exact ordering
# --------------------------------------------------------------------------
def test_multi_frame_sequence():
    s = make_sender()
    r = make_recv()
    s.peer = r.getsockname()
    s.capture_q = [(fid, 1000 + fid) for fid in range(3)]
    small = make_au([(nal(5, b"\xCC" * 100), 4)])
    big = make_au([(nal(5, b"\xDD" * 3000), 4)])

    run_au(s, small)   # frame 0: 1 pkt
    run_au(s, big)     # frame 1: 3 pkts (FU-A)
    run_au(s, small)   # frame 2: 1 pkt

    pkts = drain(r)
    metas = [p for p in pkts if p.startswith(META_PREFIX)]
    rtps = [p for p in pkts if not p.startswith(META_PREFIX)]
    assert len(metas) == 3, "one META per frame expected (got %d)" % len(metas)
    assert len(rtps) == 5, "expected 1+3+1 RTP packets, got %d" % len(rtps)

    ids = [json.loads(m[len(META_PREFIX):])["frame_id"] for m in metas]
    assert ids == [0, 1, 2], "META frame_id order broken: %r" % ids

    # META must be sent before its frame's packets (same-socket ordering).
    # Rebuild the stream index by scanning the drain order.
    order = []
    for p in pkts:
        if p.startswith(META_PREFIX):
            order.append(("META", json.loads(p[len(META_PREFIX):])["frame_id"]))
        else:
            order.append(("RTP", parse_rtp(p)["ts"]))
    # frame 0: META then ts 0 packet(s); frame 1: META then ts 3000 x3; ...
    expected = [
        ("META", 0), ("RTP", 0),
        ("META", 1), ("RTP", 3000), ("RTP", 3000), ("RTP", 3000),
        ("META", 2), ("RTP", 6000),
    ]
    assert order == expected, "stream order mismatch:\n got %r\n exp %r" % (order, expected)

    # marker pattern across the whole stream: only on last packet of each frame
    marker_seq = [parse_rtp(p)["marker"] for p in rtps]
    assert marker_seq == [True, False, False, True, True], marker_seq

    assert s.rtp_ts == 3 * TS_STEP, "rtp_ts must advance every frame (F1)"
    assert s.sent_meta == 3 and s.sent_pkts == 5
    assert s.capture_q == []
    print("PASS test_multi_frame_sequence: per-frame ts 0/3000/6000, META order exact, "
          "marker pattern correct")


# --------------------------------------------------------------------------
# 5. F1 regression guard: 100 frames must never raise, ts always advances
# --------------------------------------------------------------------------
def test_f1_regression_guard():
    s = make_sender()
    r = make_recv()
    s.peer = r.getsockname()
    s.capture_q = [(i, 2000 + i) for i in range(120)]
    for i in range(100):
        au = make_au([(nal(1, b"\xEE" * (100 + (i % 3) * 2000)), 4)])  # mix small/ big
        run_au(s, au)  # must never raise (NameError class = F1)
        drain(r)  # keep the loopback socket buffer from overflowing
    assert s.rtp_ts == 100 * TS_STEP, "rtp_ts must advance every frame (F1)"
    assert s.sent_meta == 100, "one META per frame expected"
    assert s.sent_pkts > 100
    print("PASS test_f1_regression_guard: 100 frames, no exception, rtp_ts advanced "
          "every frame (sent_pkts=%d meta=%d)" % (s.sent_pkts, s.sent_meta))


if __name__ == "__main__":
    test_split_nals()
    test_single_small_frame()
    test_fu_a_fragmentation()
    test_multi_frame_sequence()
    test_f1_regression_guard()
    print("\nALL PACKETIZATION TESTS PASS")
