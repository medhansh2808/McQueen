#!/usr/bin/env python3
"""gst_rtx_rtp_receiver.py — McQueen RTX receiver for the punched-UDP transport.

Receives H.264 RTP packets + in-band META datagrams over ONE NAT-punched UDP
socket (same rendezvous pattern as tools/realtime/direct_udp_peer.py).

Exact frame association (benchmark-v2 contract):
  - Every Jetson frame emits META (frame_id, capture_mono_ns) immediately
    BEFORE that frame's RTP packets, on the SAME socket. The META and the video
    are not independently transported: in-band ordering guarantees that the
    i-th completed video frame corresponds to the i-th META.
  - Frames are completed by the RTP marker bit. Decoded frames (appsink) are
    paired with completed META entries in order. If decoding drops a frame, the
    index drift is detected and counted as a mismatch — never silently guessed.

Control return: same socket, CTRL datagram echoing frame_id + capture_mono_ns,
so the Jetson computes receive_mono_ns - capture_mono_ns on one clock.

Benchmark-v2 stages:
  SIGNALING_P2P, VIDEO_CONNECTED, VIDEO_FRAMES, FRAME_TIMESTAMP,
  EXACT_FRAME_MATCH, RTX_INFERENCE, DIRECT_UDP, CONTROL_RETURN,
  FULL_LOOP_LATENCY (computed on the Jetson side).
"""

from __future__ import print_function

import argparse
import json
import sys
from pathlib import Path
import os
import queue
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

# Decoded-frame geometry for the RTX-side save test (matches the Jetson sender).
W, H = 640, 480


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


class Receiver(object):
    def __init__(self, args):
        self.args = args
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.media_port = int(getattr(args, "media_port", 0) or 0)
        self.sock.bind(("0.0.0.0", self.media_port))
        self.sock.settimeout(0.05)
        ann_ip = getattr(args, "announce_ip", None)
        if ann_ip:
            # LAN-direct mode (e.g. Jetson<->RTX ethernet cable): announce the
            # known cable IP instead of the STUN public mapping, so the punch
            # stays on the room-local link (~0.3ms RTT) and never hairpins.
            self.pub = (ann_ip, self.sock.getsockname()[1])
            print("[RTX-GST] ANNOUNCE override {}:{} (LAN-direct)".format(*self.pub),
                  flush=True)
        else:
            self.pub = stun(self.sock, args.stun_host, args.stun_port)

        self.ws = websocket.create_connection(args.broker, timeout=10)
        self.ws.settimeout(None)

        self.peer = None
        # Reflector target: the source address of the Jetson's RTP packets.
        # On a double-NAT LAN (Jetson behind a phone-hotspot that is itself a
        # client of the RTX's wifi) the Jetson's STUN-public endpoint is
        # unreachable (hairpin), but its RTP arrives from the hotspot's LAN
        # address — so we send controls back there. Set continuously from the
        # media stream; falls back to self.peer if no RTP seen yet.
        self.ctrl_dst = None
        self.stop_event = threading.Event()

        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.appsrc = None
        self.appsink = None

        self.frames_rx = 0       # completed RTP frames seen in udp_loop
        self.meta_q = []         # completed META entries, in order
        self.meta_lock = threading.Lock()
        self.assoc_ok = 0
        self.assoc_miss = 0
        self.rtp_rx = 0          # raw RTP datagrams received
        self.meta_rx = 0         # raw META datagrams received

        self.ctrl_seq = 0
        self.ctrl_sent = 0

        self.torch = None
        self.infer_ms = []
        self.infer_lock = threading.Lock()

        self.started = time.monotonic()
        self.last_report = self.started

        # Opt-in RTX-side frame saving (--save-frames DIR): decoded JPEG frames
        # + meta.csv via an async writer so disk I/O never blocks the control
        # path. Default None = current behavior, no saving, zero overhead.
        self.save_dir = getattr(args, "save_frames", None)
        self.save_queue = None
        self.save_thread = None
        self.save_csv = None
        self.saves = 0
        self.save_dropped = 0
        self.save_ms = []
        self.save_stop = threading.Event()

        # RTP timestamp bookkeeping for the current in-flight frame.
        self.cur_meta = None
        self.cur_rtp_pts = None

    # ---------- broker / rendezvous -------------------------------------------

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
                and msg.get("role") == "jetson"
            ):
                peer = (str(msg["ip"]), int(msg["port"]))
                if peer != self.peer:
                    self.peer = peer
                    print(
                        "[RTX-GST] PEER_CANDIDATE {}:{}".format(peer[0], peer[1]),
                        flush=True,
                    )
                    # Re-punch to a changed peer: the Jetson sender binds a
                    # fresh UDP port on every restart, so its CGNAT mapping
                    # changes too. Without re-punching, the return path dies
                    # and no frames arrive (seen 2026-08-13: sender restarted
                    # with a new port, receiver kept the old mapping -> 0 RTP).
                    for _ in range(10):
                        try:
                            self.sock.sendto(b"PUNCH2", peer)
                        except Exception:
                            pass
                        try:
                            self.sock.recvfrom(2048)
                        except socket.timeout:
                            pass

    def announce_loop(self):
        while not self.stop_event.is_set():
            try:
                self._send_ws({
                    "type": "control_udp_candidate_v2",
                    "role": "rtx",
                    "ip": self.pub[0],
                    "port": self.pub[1],
                })
            except Exception:
                pass
            self.stop_event.wait(0.35)

    def rendezvous(self):
        print("[RTX-GST] PUBLIC {}:{}".format(self.pub[0], self.pub[1]), flush=True)
        a = threading.Thread(target=self.announce_loop)
        a.daemon = True
        a.start()

        # Wait for the Jetson candidate WITHOUT a hard timeout: both sides
        # announce continuously, so any start order works — rendezvous completes
        # as soon as both peers are up.
        while self.peer is None and not self.stop_event.is_set():
            try:
                self.sock.recvfrom(2048)
            except socket.timeout:
                pass
            time.sleep(0.05)

        if self.peer is None:
            raise RuntimeError(
                "Jetson UDP candidate missing (stopped before rendezvous)"
            )

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

        print(
            "[RTX-GST] SIGNALING_P2P READY peer={}:{}".format(
                self.peer[0], self.peer[1]
            ),
            flush=True,
        )

    # ---------- UDP receive loop: META + RTP in-band --------------------------

    def udp_loop(self):
        while not self.stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                return
            # Reflector: remember the Jetson's reachable (NAT-mapped) address
            # from the media stream so controls return to it directly.
            self.ctrl_dst = addr

            if data.startswith(META_PREFIX):
                try:
                    meta = json.loads(data[len(META_PREFIX):].decode("utf-8"))
                    self.cur_meta = meta
                    self.cur_rtp_pts = None
                    self.meta_rx += 1
                except Exception:
                    pass
            elif len(data) >= 12 and (data[0] & 0xC0) == 0x80:
                # RTP packet (version 2 header). Delivery is NEVER gated on META
                # presence (Fix 1): a lost META datagram must not drop this
                # frame's RTP packets. META is only association metadata; a
                # frame that completes with cur_meta=None is counted as
                # assoc_miss downstream (honest miss), never as a delivery
                # block.
                self.rtp_rx += 1
                if self.rtp_rx % 30 == 0:
                    print(
                        "[RTX-GST] RTP_RX pkts={} meta={} frames_rx={}".format(
                            self.rtp_rx, self.meta_rx, self.frames_rx
                        ),
                        flush=True,
                    )
                if self.cur_rtp_pts is None:
                    self.cur_rtp_pts = struct.unpack("!I", data[8:12])[0]
                # Marker bit = last packet of this RTP frame.
                if data[1] & 0x80:
                    with self.meta_lock:
                        # May be None (lost META) — keep the 1:1 placeholder so
                        # in-order pairing with decoded frames never drifts.
                        self.meta_q.append(self.cur_meta)
                        if len(self.meta_q) > 8:
                            self.meta_q = self.meta_q[-8:]
                    self.frames_rx += 1
                    self.cur_meta = None
                    self.cur_rtp_pts = None
                # Feed RTP payload into appsrc (raw RTP packet) — always,
                # regardless of association state.
                if self.appsrc is not None:
                    buf = Gst.Buffer.new_allocate(None, len(data), None)
                    buf.fill(0, data)
                    self.appsrc.emit("push-buffer", buf)

    # ---------- GStreamer -----------------------------------------------------

    def build(self):
        # Fix 2: bounded jitter buffer. latency is the strict budget (50 ms
        # by default; the 25 ms variant was tested 2026-08-14 — loss ~0 on
        # the current link so a tighter buffer was tried for lower latency).
        # drop-on-latency discards packets past their deadline instead of
        # delaying the stream (GStreamer 1.20: drop-on-latency replaces the
        # removed drop-on-late — verified live on the RTX venv, 1.20.3).
        # NO retransmission/rtx: do-retransmission stays False by default
        # (a late frame is useless — drop it).
        jbuf = "rtpjitterbuffer latency={} drop-on-latency=true ! ".format(
            getattr(self.args, "jitter_ms", 50))
        pipe_desc = (
            "appsrc name=src is-live=true format=time do-timestamp=true "
            "caps=application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 ! "
            + jbuf +
            "rtph264depay ! h264parse ! "
            # CPU decode (avdec_h264): this test must not depend on the GPU —
            # the 4090 may be busy with other work (e.g. ViReL train.py), which
            # starved NVDEC to ~1 fps and stalled the pipeline. 640x480@30 is
            # trivial for the RTX CPU. Real GPU inference is a separate L1 step.
            "avdec_h264 ! "
            "videoconvert ! "
            "video/x-raw,format=I420 ! "
            "queue max-size-buffers=1 leaky=downstream ! "
            "appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true"
        )
        self.policy = None
        if getattr(self.args, "policy_endpoint", None):
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from rtx_policy_v1 import PolicyEndpointPolicy
            self.policy = PolicyEndpointPolicy(self.args.policy_endpoint)
            print("[RTX-GST] POLICY via endpoint {}".format(
                self.args.policy_endpoint), flush=True)
        elif getattr(self.args, "policy_ckpt", None):
            sys.path.insert(0, "/home/kartik/McQueenWork/McQueen/tools/realtime")
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from rtx_policy_v1 import CorridorPolicyV1
            self.policy = CorridorPolicyV1(
                ckpt_path=self.args.policy_ckpt,
                onnx_path=self.args.policy_onnx,
                device=self.args.policy_device,
            )
            print("[RTX-GST] POLICY v1 loaded on {}".format(self.policy.device), flush=True)

        self.pipeline = Gst.parse_launch(pipe_desc)
        if self.pipeline is None:
            raise RuntimeError("pipeline parse failed")

        self.appsrc = self.pipeline.get_by_name("src")
        self.appsink = self.pipeline.get_by_name("sink")
        self.appsink.connect("new-sample", self.on_sample)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("[RTX-GST] PLAYING {}".format(ret), flush=True)

    def on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("[RTX-GST] GST ERROR: {} {}".format(err, dbg), flush=True)
            self.loop.quit()

    # ---------- decode -> inference -> control return -------------------------

    def on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK

        # Pair this decoded frame with the oldest completed META.
        meta = None
        with self.meta_lock:
            if self.meta_q:
                meta = self.meta_q.pop(0)

        if meta is None:
            self.assoc_miss += 1
            return Gst.FlowReturn.OK

        self.assoc_ok += 1

        # Opt-in RTX-side frame saving: write the decoded JPEG (the exact frame
        # the pipeline decoded) + CSV line, async. Only frames with a META (exact
        # frame_id) are saved. If the bounded queue is full, SAVES are dropped
        # (counted) — never frames, never delivery.
        if self.save_dir is not None:
            self._enqueue_save(sample, int(meta["frame_id"]),
                               int(meta["capture_mono_ns"]), mono_ns())

        # RTX inference — CPU dummy policy forward. This test runs the pipeline
        # without touching the GPU (the 4090 may be 100% busy with other work,
        # e.g. ViReL train.py, which starved the old CUDA dummy to ~1 fps and
        # stalled the pipeline). Real GPU inference is a separate L1 step and
        # runs only when the GPU is free and the user approves.
        infer_ms = None
        servo = 90.0
        pwm = 0
        if self.policy is not None:
            import numpy as np
            try:
                b = sample.get_buffer()
                ok, m = b.map(Gst.MapFlags.READ)
                if not ok:
                    return Gst.FlowReturn.OK
                try:
                    i420 = bytes(m.data)
                finally:
                    b.unmap(m)
                if not getattr(self, "policy_worker_on", False):
                    self.policy.start_worker()
                    self.policy_worker_on = True
                    print("[RTX-GST] POLICY worker started", flush=True)
                self.policy.submit_frame(
                    np.frombuffer(i420, dtype=np.uint8).reshape((-1, W)))
                out = self.policy.latest()
                infer_ms = float(out.get("infer_ms", 0.0))
                if infer_ms > 0:
                    with self.infer_lock:
                        self.infer_ms.append(infer_ms)
                servo = out["servo_angle_deg"]
                pwm = out["motor_pwm"]
            except Exception as exc:
                print("[RTX-GST] POLICY ERROR {}".format(exc), flush=True)
        else:
            if self.torch is None:
                import torch
                self.torch = torch
                print("[RTX-GST] PYTORCH device=cpu (CPU dummy)", flush=True)
            try:
                t0 = time.perf_counter()
                y = self.torch.rand((1, 2048), device="cpu").mean()
                infer_ms = (time.perf_counter() - t0) * 1000.0
                with self.infer_lock:
                    self.infer_ms.append(infer_ms)
            except Exception as exc:
                print("[RTX-GST] INFER ERROR {}".format(exc), flush=True)
                infer_ms = 0.0
            servo = 90.0 + max(-5.0, min(5.0, (float(y.item()) - 0.5) * 10.0))
            pwm = 0

        # Control return echoes exact frame identity for Jetson-clock latency.
        self.ctrl_seq += 1
        msg = {
            "seq": self.ctrl_seq,
            "frame_id": int(meta["frame_id"]),
            "capture_mono_ns": int(meta["capture_mono_ns"]),
            "infer_ms": float(infer_ms or 0.0),
            "servo_angle_deg": float(servo),
            "motor_pwm": int(pwm),
            "ttl_ms": 250,
        }
        try:
            self.sock.sendto(
                CTRL_PREFIX + json.dumps(msg, separators=(",", ":")).encode("utf-8"),
                self.ctrl_dst or self.peer,
            )
            self.ctrl_sent += 1
        except Exception as exc:
            print("[RTX-GST] CTRL send error {}".format(exc), flush=True)

        now = time.monotonic()
        if now - self.last_report >= 1.0:
            elapsed = max(now - self.started, 0.001)
            with self.infer_lock:
                tail = self.infer_ms[-20:]
            print(
                "[RTX-GST] VIDEO frames_rx={} fps={:.1f} assoc_ok={} assoc_miss={} "
                "ctrl_sent={} infer_avg={:.2f}ms".format(
                    self.frames_rx,
                    self.frames_rx / elapsed,
                    self.assoc_ok,
                    self.assoc_miss,
                    self.ctrl_sent,
                    sum(tail) / max(len(tail), 1),
                ),
                flush=True,
            )
            self.last_report = now

        return Gst.FlowReturn.OK

    # ---------- RTX-side frame saving (--save-frames, async writer) -----------

    def _start_saving(self):
        os.makedirs(self.save_dir, exist_ok=True)
        self.save_csv = open(
            os.path.join(self.save_dir, "meta.csv"), "a", buffering=1)
        self.save_csv.write("frame_id,capture_mono_ns,recv_mono_ns,save_mono_ns\n")
        self.save_queue = queue.Queue(maxsize=256)
        self.saves = 0
        self.save_dropped = 0
        self.save_ms = []
        self.save_stop = threading.Event()
        t = threading.Thread(target=self._save_worker)
        t.daemon = True
        t.start()
        self.save_thread = t
        print("[RTX-GST] SAVE frames -> {} (JPEG + meta.csv, async writer)".format(
            self.save_dir), flush=True)

    def _enqueue_save(self, sample, frame_id, capture_mono_ns, recv_mono_ns):
        try:
            import cv2
            import numpy as np
            b = sample.get_buffer()
            ok, m = b.map(Gst.MapFlags.READ)
            if not ok:
                return
            try:
                i420 = bytes(m.data)
            finally:
                b.unmap(m)
            img = np.frombuffer(i420, dtype=np.uint8).reshape((H * 3 // 2, W))
            bgr = cv2.cvtColor(img, cv2.COLOR_YUV2BGR_I420)
            okc, enc = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not okc:
                return
            try:
                self.save_queue.put_nowait(
                    (enc.tobytes(), frame_id, capture_mono_ns, recv_mono_ns))
            except queue.Full:
                self.save_dropped += 1
        except Exception as exc:
            print("[RTX-GST] SAVE encode error {!r}".format(exc), flush=True)

    def _save_worker(self):
        while not self.save_stop.is_set():
            try:
                payload = self.save_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if payload is None:
                break
            jpg, frame_id, capture_mono_ns, recv_mono_ns = payload
            try:
                with open(os.path.join(self.save_dir,
                                       "frame_{}.jpg".format(frame_id)), "wb") as fh:
                    fh.write(jpg)
                save_mono_ns = mono_ns()
                self.save_csv.write("{},{},{},{}\n".format(
                    frame_id, capture_mono_ns, recv_mono_ns, save_mono_ns))
                self.save_ms.append(save_mono_ns - recv_mono_ns)
                if len(self.save_ms) > 500:
                    self.save_ms = self.save_ms[-500:]
                self.saves += 1
                if self.saves % 100 == 0:
                    tail = sorted(self.save_ms)
                    p50 = tail[len(tail) // 2]
                    p95 = tail[min(len(tail) - 1, int(len(tail) * 0.95))]
                    print("[RTX-GST] SAVED n={} dropped={} recv2save_p50={:.2f}ms "
                          "recv2save_p95={:.2f}ms".format(
                              self.saves, self.save_dropped, p50 / 1e6, p95 / 1e6),
                          flush=True)
            except Exception as exc:
                print("[RTX-GST] SAVE write error {!r}".format(exc), flush=True)

    def _stop_saving(self):
        if self.save_dir is None:
            return
        self.save_stop.set()
        try:
            self.save_queue.put_nowait(None)
        except Exception:
            pass
        try:
            if self.save_thread is not None:
                self.save_thread.join(timeout=3)
        except Exception:
            pass
        try:
            self.save_csv.close()
        except Exception:
            pass
        tail = sorted(self.save_ms)
        if tail:
            p50 = tail[len(tail) // 2]
            p95 = tail[min(len(tail) - 1, int(len(tail) * 0.95))]
            print("[RTX-GST] SAVE FINAL n={} dropped={} recv2save_p50={:.2f}ms "
                  "p95={:.2f}ms".format(
                      self.saves, self.save_dropped, p50 / 1e6, p95 / 1e6),
                  flush=True)

    def run(self):
        t = threading.Thread(target=self._ws_loop)
        t.daemon = True
        t.start()
        u = threading.Thread(target=self.udp_loop)
        u.daemon = True
        u.start()

        self.rendezvous()
        if self.save_dir is not None:
            self._start_saving()
        self.build()

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
            self._stop_saving()

            with self.infer_lock:
                infer_n = len(self.infer_ms)
                infer_avg = sum(self.infer_ms) / infer_n if infer_n else 0.0
            print(
                "[RTX-GST] RTX_INFERENCE avg={:.2f}ms n={}".format(infer_avg, infer_n),
                flush=True,
            )
            print(
                "[RTX-GST] CONTROL_RETURN sent={} EXACT_FRAME_MATCH ok={} miss={}".format(
                    self.ctrl_sent, self.assoc_ok, self.assoc_miss
                ),
                flush=True,
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", required=True)
    p.add_argument("--stun-host", default="stun.cloudflare.com")
    p.add_argument("--stun-port", type=int, default=3478)
    p.add_argument("--announce-ip", default=None,
                   help="LAN-direct mode: announce this IP instead of the STUN "
                        "public mapping (pair with --media-port)")
    p.add_argument("--media-port", type=int, default=0,
                   help="fix the UDP media port (0 = ephemeral); required with "
                        "--announce-ip for deterministic cable runs")
    p.add_argument("--save-frames", default=None,
                   help="RTX-side recording test: save decoded frames as JPEG + "
                        "meta.csv (frame_id,capture_mono_ns,recv_mono_ns,save_mono_ns) "
                        "into DIR via an async writer (default: no saving)")
    p.add_argument("--policy-ckpt", default=None,
                   help="enable v1 corridor policy (real_head_v1.pt)")
    p.add_argument("--policy-endpoint", default=None,
                   help="host:port of an isolated GPU policy_worker.py (takes "
                        "precedence over --policy-ckpt; keeps CUDA out of this "
                        "process — 2026-08-22 segfault)")
    p.add_argument("--policy-onnx", default="/home/junior/mcqueen/models/big_driving_supercombo.onnx")
    p.add_argument("--policy-device", default=None, help="cuda/cpu (auto if unset)")
    p.add_argument("--jitter-ms", type=int, default=50,
                   help="rtpjitterbuffer latency budget in ms (50 default; 25 tested "
                        "2026-08-14 — never raise above 50 per user constraint)")
    args = p.parse_args()
    if args.policy_ckpt and "big_driving_supercombo.onnx" not in args.policy_onnx:
        raise SystemExit(
            "ERROR: --policy-onnx must point at big_driving_supercombo.onnx — the "
            "policy trunk loader maps it to big_driving_supercombo_ks.onnx (ORT-fixed "
            "graph). Wrong file here caused the 2026-08-22 stationary-car failure."
        )
    Receiver(args).run()


if __name__ == "__main__":
    main()
