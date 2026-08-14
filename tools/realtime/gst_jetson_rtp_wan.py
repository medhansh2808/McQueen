#!/usr/bin/env python3
"""gst_jetson_rtp_wan.py — McQueen Jetson sender: H.264 RTP over NAT-punched UDP.

Transport design (lab-verified path, 2026-08-13):
  - Camera captured via cv2.VideoCapture (the PROVEN capture path — the same
    one mcqueen-edge uses to record datasets; GStreamer v4l2src stalls on the
    Jetson's MJPEG camera). Frames are pushed into a GStreamer appsrc.
  - appsrc -> videoconvert -> nvvidconv (NVMM NV12) -> NVENC H.264 ->
    rtph264pay. RTP packets + in-band frame metadata are sent over ONE UDP
    socket that was NAT-punched using the proven stun()+broker rendezvous
    pattern from tools/realtime/direct_udp_peer.py (60/60 ACK proof,
    p50 ~43 ms). No webrtcbin/ICE — the Jetson's GStreamer 1.14.5/libnice
    0.1.14 cannot gather srflx candidates through the hotspot CGNAT.
  - Frame metadata (frame_id, capture_mono_ns) travels on the SAME socket
    immediately before that frame's RTP packets. Association is exact by
    construction (same-socket ordering), and the RTX cross-checks RTP
    timestamps.
  - Control return is received on the same socket; the Jetson computes
    receive_mono_ns - capture_mono_ns on its own monotonic clock.

Dry-run safety: zero GPIO writes. This script only captures/encodes/sends.

Usage:
  python3 gst_jetson_rtp_wan.py --broker wss://.../ws?role=jetson&session=mcqueen \
      --device /dev/v4l/by-id/... --stun stun://stun.cloudflare.com:3478
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

# 640x480: 4x less memory than 720p. The Jetson (4GB shared RAM/GPU) OOM-kills
# the process at 720p (dmesg: "Out of memory: Kill process python3").
# Inference on the RTX does not need 720p.
WIDTH, HEIGHT = 640, 480
FPS = 30
FRAME_NS = int(1e9 / FPS)


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
        self.appsrc = None
        self.frame_id = 0

        # Manual RTP packetization state. rtph264pay on this Jetson GStreamer
        # stack stamps a CONSTANT RTP timestamp on every packet (x264enc drops
        # PTS, payloader keeps the base ts) — proven by appsrc_rtp_ts_test.py
        # (distinct_rtp_ts=1, markers=90, and perfect-rtptime=true also fails).
        # rtph264depay on the RTX reassembles access units BY RTP timestamp, so
        # a constant ts merges every frame into one AU (only 1 frame decoded).
        # Fix: we packetize H.264 AUs ourselves. Each h264parse output buffer
        # is exactly one frame, so the RTP timestamp is deterministic:
        #   ts = frame_ts_base + frame_index * RTP_TS_PER_FRAME (3000 @ 90kHz).
        self.rtp_seq = 0
        self.rtp_ssrc = 0x4D515545  # "MQUE"
        self.rtp_ts = 0
        # --max-fps throttling (default 30 = send every captured frame, exactly
        # the original path). rtp_ts_step must match the SENT rate (90kHz/fps)
        # so the receiver's jitter-buffer clock math stays honest. Throttling
        # is TIME-based (push at most one frame per frame_ns) so ANY target fps
        # is achievable from the 30 fps camera (frame-skip integer steps could
        # only do 30/N, e.g. 20 was silently 15).
        self.max_fps = int(getattr(args, "max_fps", 30) or 30)
        self.rtp_ts_step = 90000 // self.max_fps
        self.frame_ns = int(1e9 / self.max_fps)   # min gap + PTS step per SENT frame
        self._last_push_ns = 0
        self.rtp_mtu = 1200

        # Frame metadata queue: (frame_id, capture_mono_ns) pushed by the cv2
        # capture thread, consumed by the rtph264pay pad probe (one per frame).
        self.capture_q = []
        self.capture_lock = threading.Lock()

        # Latency bookkeeping for the authoritative Jetson-clock measurement.
        self.latency_ms = []
        self.ctrl_count = 0
        self.sent_pkts = 0
        self.sent_meta = 0
        self.sent_bytes = 0      # Fix 3: measured achieved send rate
        self.started = time.monotonic()

        self.cap = None

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

        # Wait for the RTX candidate WITHOUT a hard timeout: both sides announce
        # continuously, so any start order works — rendezvous completes as soon
        # as both peers are up. (A 60s cap caused repeated "candidate missing"
        # failures when peers didn't overlap in time.)
        while self.peer is None and not self.stop_event.is_set():
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.05)

        if self.peer is None:
            raise RuntimeError("RTX UDP candidate missing (stopped before rendezvous)")

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
                # Rolling full-loop latency (Jetson clock): receive_mono_ns -
                # capture_mono_ns, live every 10 controls — so the run shows
                # the latency number without needing a graceful shutdown (the
                # script never sends EOS).
                vals = sorted(self.latency_ms)
                p50 = vals[len(vals) // 2] if vals else 0.0
                p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))] if vals else 0.0
                print(
                    "[JETSON-CAM] CTRL_RX n={} frame={} servo={:.1f} pwm={} "
                    "infer={:.2f}ms LAT_p50={:.1f}ms LAT_p95={:.1f}ms".format(
                        self.ctrl_count,
                        msg.get("frame_id"),
                        float(msg.get("servo_angle_deg", 0.0)),
                        int(msg.get("motor_pwm", 0)),
                        float(msg.get("infer_ms", 0.0)),
                        p50, p95,
                    ),
                    flush=True,
                )

    # ---------- cv2 capture thread (proven path, no v4l2src) -----------------

    def capture_loop(self):
        import cv2

        dev = self.args.device
        self.cap = cv2.VideoCapture(dev)
        if not self.cap.isOpened():
            print("[JETSON-CAM] CV2 OPEN FAILED for {}".format(dev), flush=True)
            self.loop.quit()
            return
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        print("[JETSON-CAM] cv2 camera open: {} ({}x{}@{}fps requested)".format(
            dev, WIDTH, HEIGHT, FPS), flush=True)

        # PTS must be based on the current monotonic clock, NOT 0: buffers
        # with PTS in the past are dropped by the pipeline clock (proven by
        # appsrc_test2.py on the Jetson: 150/150 buffers only with a real base).
        pts = mono_ns()
        while not self.stop_event.is_set():
            ok, frame = self.cap.read()
            if not ok or frame is None:
                # Camera hiccup: skip rather than crash.
                print("[JETSON-CAM] cv2 read failed, skipping frame", flush=True)
                time.sleep(0.05)
                continue

            # --max-fps throttling: TIME-based, ONLY when a lower rate is
            # requested. Default 30 fps = NO gate = push every captured frame
            # (the exact original path — a 33.3 ms gate would skip jittery
            # camera frames and silently drop below 30). Lower fps: push at
            # most once per frame_ns, the rest are read-and-dropped. Skipped
            # frames get NO capture_q entry / NO frame_id increment, keeping
            # META 1:1 with sent frames. NOTE: dropping can only reach 30/N
            # rates from a 30 fps camera (e.g. 20 is not achievable — 15 or
            # 30 only); 20 needs a camera rate change, not frame dropping.
            if self.max_fps < 30:
                now_ns = mono_ns()
                if now_ns - self._last_push_ns < self.frame_ns:
                    continue
                self._last_push_ns = now_ns

            # Stamp capture time on THIS machine's monotonic clock immediately
            # after the read — this is the true capture moment.
            capture = mono_ns()
            with self.capture_lock:
                self.capture_q.append((self.frame_id, capture))
                if len(self.capture_q) > 8:
                    self.capture_q = self.capture_q[-8:]

            if self.appsrc is not None:
                try:
                    buf = Gst.Buffer.new_allocate(None, frame.nbytes, None)
                    # buf.fill() works on old PyGObject (mapinfo.data[:] =
                    # fails: returns immutable bytes).
                    buf.fill(0, bytes(frame.tobytes()))
                    # Pipeline is do-timestamp=false, so WE must stamp the
                    # PTS. Base it on the current monotonic clock (NOT 0):
                    # buffers with PTS in the past are dropped by the pipeline
                    # clock (proven by appsrc_test2.py on the Jetson).
                    buf.pts = pts
                    buf.duration = self.frame_ns
                    ret = self.appsrc.emit("push-buffer", buf)
                    if self.frame_id % 30 == 0:
                        print(
                            "[JETSON-CAM] PUSH frame={} ret={} q={}".format(
                                self.frame_id, ret, len(self.capture_q)
                            ),
                            flush=True,
                        )
                except Exception as exc:
                    print("[JETSON-CAM] appsrc push error {!r}".format(exc), flush=True)
            pts += self.frame_ns
            self.frame_id += 1

        if self.cap is not None:
            self.cap.release()

    # ---------- GStreamer -----------------------------------------------------

    def on_rtp_probe(self, pad, info):
        # One probe per RTP packet. A new video frame starts whenever the RTP
        # timestamp changes. At the first packet of a frame we emit META, then
        # the frame's packets. Each frame consumes exactly ONE capture_q entry.
        try:
            return self._on_rtp_probe(pad, info)
        except Exception as exc:
            try:
                with open("/tmp/mcq_sender_probe_errors.log", "a") as fh:
                    fh.write("probe error: {!r}\n".format(exc))
            except Exception:
                pass
            return Gst.PadProbeReturn.OK

    def _on_rtp_probe(self, pad, info):
        # One probe per H.264 access unit (= one frame, h264parse output).
        # We do manual RTP packetization: split the AU into MTU-sized chunks,
        # stamp a deterministic per-frame RTP timestamp, set the marker bit on
        # the last chunk, and emit META (frame_id + capture_mono_ns) in-band
        # BEFORE the first chunk so association is exact by same-socket order.
        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            # Copy to a plain bytes object NOW, while the buffer is mapped.
            # Using mapinfo.data after unmap() is a use-after-free on the
            # Jetson's old GStreamer/PyGObject stack (crash right after NVENC).
            au = bytes(mapinfo.data)
        finally:
            buf.unmap(mapinfo)

        if not au:
            return Gst.PadProbeReturn.OK

        # Consume ONE capture entry for this frame and emit its META first.
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
                "rtp_ts": self.rtp_ts,
            }, separators=(",", ":")).encode("utf-8")
            try:
                self.sock.sendto(META_PREFIX + meta, self.peer)
                self.sent_meta += 1
                self.sent_bytes += len(META_PREFIX) + len(meta)
            except Exception:
                pass

        # RFC 6184 packetization: split the AU into NAL units, send small
        # NALs as single packets and large NALs as FU-A fragments. Naive
        # byte-chunking broke rtph264depay ("NAL unit type 26 not supported"
        # = chunk started mid-NAL). Marker bit on the LAST packet of the AU.
        ts = self.rtp_ts & 0xFFFFFFFF
        nals = self._split_nals(au)
        last_idx = len(nals) - 1
        for ni, nal in enumerate(nals):
            if not nal:
                continue
            if len(nal) <= self.rtp_mtu:
                marker = 1 if ni == last_idx else 0
                self._send_rtp(ts, nal, marker)
            else:
                # FU-A: FU indicator = F/NRI bits | 28, FU header carries type.
                fu_ind = (nal[0] & 0xE0) | 28
                fu_type = nal[0] & 0x1F
                body = nal[1:]
                fstart = 0
                while fstart < len(body):
                    fend = min(fstart + self.rtp_mtu - 2, len(body))
                    chunk = body[fstart:fend]
                    is_first = fstart == 0
                    is_last = fend >= len(body)
                    fu_hdr = ((0x80 if is_first else 0) |
                              (0x40 if is_last else 0) | fu_type)
                    marker = 1 if (is_last and ni == last_idx) else 0
                    self._send_rtp(ts, bytes([fu_ind, fu_hdr]) + chunk, marker)
                    fstart = fend

        if self.sent_pkts % 30 == 0:
            # Fix 3: report the MEASURED achieved send rate (kbps) — the number
            # that drives the --bitrate-kbps value for the next run (target =
            # measured capacity with headroom; loss = sent-rx gap on the RTX
            # log). Never a guess.
            elapsed = max(time.monotonic() - self.started, 0.001)
            achieved_kbps = self.sent_bytes * 8.0 / 1000.0 / elapsed
            print(
                "[JETSON-CAM] SENT pkts={} meta={} rtp_ts={} au_bytes={} "
                "achieved={:.0f}kbps peer={}:{}".format(
                    self.sent_pkts, self.sent_meta, ts, len(au),
                    achieved_kbps,
                    self.peer[0] if self.peer else "?",
                    self.peer[1] if self.peer else "?",
                ),
                flush=True,
            )

        self.rtp_ts += self.rtp_ts_step
        return Gst.PadProbeReturn.OK

    def _send_rtp(self, ts, payload, marker):
        # RTP header byte 1 = [M(bit7) | PT(7 bits)]. PT=96 -> 0x60.
        # (96 << 1) is WRONG: that sets bit 7 (the marker!) on EVERY packet,
        # which made rtph264depay flush each fragment as a complete frame and
        # the receiver forward only one packet per frame to the pipeline
        # ("waiting for start" orphans + zero decoded frames on the RTX).
        header = struct.pack(
            "!BBHII",
            0x80,
            (0x80 if marker else 0) | 96,
            self.rtp_seq & 0xFFFF,
            ts,
            self.rtp_ssrc,
        )
        try:
            self.sock.sendto(header + payload, self.peer)
            self.sent_pkts += 1
            self.sent_bytes += len(header) + len(payload)
        except Exception:
            pass
        self.rtp_seq += 1

    @staticmethod
    def _split_nals(au):
        """Split an H.264 byte-stream access unit into NAL units (with the
        NAL header byte, without start codes)."""
        nals = []
        i, n = 0, len(au)
        while i < n:
            # Find a start code (00 00 01 or 00 00 00 01).
            if au[i:i + 4] == b"\x00\x00\x00\x01":
                sc = 4
            elif au[i:i + 3] == b"\x00\x00\x01":
                sc = 3
            else:
                i += 1
                continue
            j = i + sc
            k = j
            while k < n:
                if au[k:k + 4] == b"\x00\x00\x00\x01" or \
                        au[k:k + 3] == b"\x00\x00\x01":
                    break
                k += 1
            nal = au[j:k]
            if nal:
                # Drop AUD (type 9): optional access-unit delimiter. Sending
                # it as a standalone RTP packet confused rtph264depay's FU-A
                # state machine on the RTX ("waiting for start" orphans — the
                # depay flushes on AUD in some versions, resetting mid-fragment).
                if (nal[0] & 0x1F) != 9:
                    nals.append(nal)
            i = k
        return nals

    def build(self):
        # NOTE: nvv4l2h264enc (hardware NVENC) STALLS on this Jetson with real
        # camera frames (enc_in=90, sink=6 in the isolated test) while software
        # x264enc flows everything (enc_in=90, sink=191). NVENC on the old
        # JetPack stack appears to choke on the camera's frame timestamps/
        # content. x264enc at 640x480@30 ultrafast keeps up on the Nano CPU.
        pipe_desc = (
            "appsrc name=src is-live=false format=time do-timestamp=false "
            "caps=video/x-raw,format=BGR,width={},height={},framerate={}/1 ! "
            "videoconvert ! "
            "video/x-raw,format=I420 ! "
            "x264enc tune=zerolatency bitrate={} speed-preset=ultrafast "
            "key-int-max=30 ! "
            "h264parse name=parse config-interval=-1 ! "
            "video/x-h264,stream-format=byte-stream,alignment=au ! "
            "fakesink"
        ).format(WIDTH, HEIGHT, FPS, self.args.bitrate_kbps)

        print("[JETSON-CAM] pipeline: cv2 640x480@{} -> appsrc -> x264 (SW) "
              "-> manual RTP packetization -> punched UDP (no ICE)".format(
                  self.max_fps), flush=True)
        # Fix 3: bitrate comes from measurement (--bitrate-kbps), not a guess.
        # The default 2500 exists ONLY so the unmodified run script keeps
        # working; the operator sets it from the measured achieved/loss values
        # of the previous run.
        print("[JETSON-CAM] bitrate={} kbps (Fix 3: from measurement, not guess)".format(
            self.args.bitrate_kbps), flush=True)

        self.pipeline = Gst.parse_launch(pipe_desc)
        if self.pipeline is None:
            raise RuntimeError("pipeline parse failed")

        self.appsrc = self.pipeline.get_by_name("src")

        parse = self.pipeline.get_by_name("parse")
        if parse is None:
            raise RuntimeError("h264parse not found in pipeline")
        ppad = parse.get_static_pad("src")
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

        cap_thread = threading.Thread(target=self.capture_loop)
        cap_thread.daemon = True
        cap_thread.start()

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
    # Fix 3: bitrate from measurement, not a hardcoded guess. Default 2500 is a
    # compatibility fallback so the unmodified run script keeps working; set it
    # from the measured achieved send rate / loss of the previous run.
    p.add_argument("--bitrate-kbps", type=int, default=2500,
                   help="x264 bitrate in kbps — set from measured WAN throughput/loss")
    p.add_argument("--max-fps", type=int, default=30,
                   help="send every Nth captured frame so the sent rate ≈ this fps "
                        "(default 30 = send every frame, original behavior)")
    args = p.parse_args()
    Sender(args).run()


if __name__ == "__main__":
    main()
