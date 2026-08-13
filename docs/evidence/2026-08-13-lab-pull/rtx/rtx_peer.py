#!/usr/bin/env python3
import argparse
import asyncio
import json
import time
from collections import deque

import aiohttp
import logging
import aiortc.rtcdtlstransport as aiortc_dtls
import aiortc.rtcicetransport as aiortc_ice
from OpenSSL import SSL
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.sdp import candidate_from_sdp


def gst14_compat_answer_sdp(sdp):
    out = []
    sha256_seen = False
    for line in sdp.splitlines():
        low = line.lower()
        if low.startswith('a=fingerprint:'):
            if low.startswith('a=fingerprint:sha-256 '):
                if sha256_seen:
                    continue
                sha256_seen = True
                out.append(line)
            else:
                continue
        else:
            out.append(line)
    return '\r\n'.join(out) + '\r\n'


def strip_candidates(sdp):
    out = []
    for line in sdp.splitlines():
        if line.startswith('a=candidate:') or line == 'a=end-of-candidates':
            continue
        out.append(line)
    return '\r\n'.join(out) + '\r\n'


def candidate_messages_from_sdp(sdp):
    messages = []
    mline = -1
    for line in sdp.splitlines():
        if line.startswith('m='):
            mline += 1
        elif line.startswith('a=candidate:'):
            # GStreamer webrtcbin expects the WebRTC candidate string
            # including the leading "candidate:" token.
            messages.append({
                'type': 'ice',
                'mline': max(mline, 0),
                'candidate': line[len('a='):]
            })
    return messages


def build_ice_servers(args):
    servers = []
    if args.stun:
        servers.append(RTCIceServer(urls=args.stun))
    if args.turn:
        servers.append(RTCIceServer(urls=args.turn, username=args.turn_user or None, credential=args.turn_pass or None))
    return servers


def install_gst14_rsa_cipher_compat():
    original = aiortc_dtls.RTCCertificate._create_ssl_context

    if getattr(original, '_mcqueen_gst14_rsa_compat', False):
        return

    def compat_create_ssl_context(self, srtp_profiles):
        ctx = original(self, srtp_profiles)
        ctx.set_cipher_list(b"HIGH:!CAMELLIA:!aNULL")
        return ctx

    compat_create_ssl_context._mcqueen_gst14_rsa_compat = True
    aiortc_dtls.RTCCertificate._create_ssl_context = compat_create_ssl_context

def install_dtls_alert_logging():
    original_recv = aiortc_ice.RTCIceTransport._recv

    if getattr(original_recv, "_mcqueen_dtls_alert_logging", False):
        return

    alert_names = {
        0: "close_notify",
        10: "unexpected_message",
        20: "bad_record_mac",
        21: "decryption_failed",
        22: "record_overflow",
        40: "handshake_failure",
        42: "bad_certificate",
        43: "unsupported_certificate",
        44: "certificate_revoked",
        45: "certificate_expired",
        46: "certificate_unknown",
        47: "illegal_parameter",
        48: "unknown_ca",
        49: "access_denied",
        50: "decode_error",
        51: "decrypt_error",
        70: "protocol_version",
        71: "insufficient_security",
        80: "user_canceled",
        100: "no_renegotiation",
        110: "unsupported_extension",
    }

    async def logged_recv(self):
        data = await original_recv(self)
        if len(data) >= 15 and data[0] == 21:
            level = data[13]
            desc = data[14]
            print(
                "[RTX] DTLS ALERT level={} desc={} ({}) raw={}".format(
                    level,
                    desc,
                    alert_names.get(desc, "unknown"),
                    data.hex(),
                ),
                flush=True,
            )
        return data

    logged_recv._mcqueen_dtls_alert_logging = True
    aiortc_ice.RTCIceTransport._recv = logged_recv


async def run(args):
    install_dtls_alert_logging()
    aiortc_dtls.SRTP_PROFILES[:] = [aiortc_dtls.SRTP_AES128_CM_SHA1_80]

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
    logging.getLogger('aiortc.rtcdtlstransport').setLevel(logging.DEBUG)
    logging.getLogger('aiortc.rtcpeerconnection').setLevel(logging.INFO)
    logging.getLogger('aioice.ice').setLevel(logging.INFO)

    print('[RTX] GST14 compatibility: exact aiortc-1.5 DTLS policy', flush=True)
    pc = RTCPeerConnection(RTCConfiguration(iceServers=build_ice_servers(args)))
    meta_queue = asyncio.Queue(maxsize=120)
    frame_count = 0
    latency_samples = deque(maxlen=300)

    async with aiohttp.ClientSession() as session:
        ws = await session.ws_connect(args.broker, heartbeat=15.0)
        print('[RTX] broker connected {}'.format(args.broker), flush=True)

        async def send(payload):
            await ws.send_str(json.dumps(payload, separators=(',', ':')))

        @pc.on('connectionstatechange')
        async def on_connectionstatechange():
            print('[RTX] WebRTC state={}'.format(pc.connectionState), flush=True)

        @pc.on('iceconnectionstatechange')
        async def on_ice_state():
            print('[RTX] ICE state={}'.format(pc.iceConnectionState), flush=True)

        @pc.on('track')
        def on_track(track):
            print('[RTX] track kind={}'.format(track.kind), flush=True)
            if track.kind != 'video':
                return

            async def consume_video():
                nonlocal frame_count
                last_report = time.monotonic()
                period_count = 0
                while True:
                    frame = await track.recv()
                    rx_ns = time.monotonic_ns()
                    frame_count += 1
                    period_count += 1
                    meta = None
                    try:
                        meta = meta_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                    if meta is not None:
                        capture_ns = int(meta.get('capture_mono_ns', 0))
                        frame_id = int(meta.get('frame_id', frame_count))
                        one_way_ms = (rx_ns - capture_ns) / 1e6 if capture_ns else None
                        if one_way_ms is not None:
                            latency_samples.append(one_way_ms)
                        await send({
                            'type': 'control',
                            'frame_id': frame_id,
                            'capture_mono_ns': capture_ns,
                            'rtx_rx_mono_ns': rx_ns,
                            'servo_angle_deg': 90.0,
                            'motor_pwm': 0,
                            'inference_ms': 0.0,
                            'model_id': 'dummy-v0',
                        })

                    now = time.monotonic()
                    if now - last_report >= 2.0:
                        fps = period_count / (now - last_report)
                        shape = (frame.height, frame.width)
                        if latency_samples:
                            vals = sorted(latency_samples)
                            p50 = vals[len(vals)//2]
                            p95 = vals[min(len(vals)-1, int(len(vals)*0.95))]
                            print('[RTX] video {}x{} fps={:.1f} approx capture->decode p50={:.1f}ms p95={:.1f}ms'.format(shape[1], shape[0], fps, p50, p95), flush=True)
                        else:
                            print('[RTX] video {}x{} fps={:.1f} waiting for frame_meta'.format(shape[1], shape[0], fps), flush=True)
                        last_report = now
                        period_count = 0

            asyncio.create_task(consume_video())

        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            typ = data.get('type')

            if typ == 'offer':
                print('[RTX] received offer', flush=True)
                await pc.setRemoteDescription(RTCSessionDescription(sdp=data['sdp'], type='offer'))

                if args.codec:
                    codecs = [c for c in RTCRtpSender.getCapabilities('video').codecs if c.mimeType.lower() == 'video/' + args.codec.lower()]
                    for transceiver in pc.getTransceivers():
                        if transceiver.kind == 'video' and codecs:
                            transceiver.setCodecPreferences(codecs)
                            print('[RTX] forcing codec {}'.format(args.codec.upper()), flush=True)

                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                full_sdp = pc.localDescription.sdp
                compat_sdp = gst14_compat_answer_sdp(strip_candidates(full_sdp))

                print('[RTX] answer DTLS lines:', flush=True)
                for line in compat_sdp.splitlines():
                    if line.startswith('a=fingerprint:') or line.startswith('a=setup:'):
                        print('[RTX]   ' + line, flush=True)

                await send({'type': 'answer', 'sdp': compat_sdp})
                for cand in candidate_messages_from_sdp(full_sdp):
                    await send(cand)
                await send({'type': 'ice', 'mline': 0, 'candidate': ''})
                print('[RTX] answer + ICE sent', flush=True)

            elif typ == 'ice':
                candidate_text = data.get('candidate', '')
                if not candidate_text:
                    await pc.addIceCandidate(None)
                else:
                    if candidate_text.startswith('candidate:'):
                        candidate_text = candidate_text[len('candidate:'):]
                    cand = candidate_from_sdp(candidate_text)
                    cand.sdpMLineIndex = int(data.get('mline', 0))
                    await pc.addIceCandidate(cand)

            elif typ == 'frame_meta':
                if meta_queue.full():
                    try:
                        meta_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                meta_queue.put_nowait(data)

            elif typ == 'peer':
                print('[RTX] peer {} {}'.format(data.get('role'), data.get('state')), flush=True)

    await pc.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--broker', required=True, help='ws://HOST:PORT/ws?role=rtx&session=mcqueen')
    p.add_argument('--codec', choices=['h264', 'vp8'], default='h264')
    p.add_argument('--stun', default='')
    p.add_argument('--turn', default='')
    p.add_argument('--turn-user', default='')
    p.add_argument('--turn-pass', default='')
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
