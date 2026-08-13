#!/usr/bin/env python3
import argparse
import asyncio
import json
import time
from aiohttp import web

SESSIONS = {}


def peer_name(request):
    return request.query.get('role', '')


def session_name(request):
    return request.query.get('session', 'mcqueen')


async def health(request):
    state = {}
    for session, peers in SESSIONS.items():
        state[session] = sorted(peers.keys())
    return web.json_response({'ok': True, 'sessions': state, 'time_ns': time.time_ns()})


async def ws_handler(request):
    role = peer_name(request)
    session = session_name(request)
    if role not in ('jetson', 'rtx'):
        return web.Response(status=400, text='role must be jetson or rtx')

    ws = web.WebSocketResponse(heartbeat=15.0, autoping=True)
    await ws.prepare(request)

    peers = SESSIONS.setdefault(session, {})
    old = peers.get(role)
    if old is not None and not old.closed:
        await old.close(code=4001, message=b'replaced')
    peers[role] = ws

    print('[BROKER] {} connected session={}'.format(role, session), flush=True)

    other_role = 'rtx' if role == 'jetson' else 'jetson'
    other = peers.get(other_role)
    if other is not None and not other.closed:
        await other.send_json({'type': 'peer', 'role': role, 'state': 'connected'})
    await ws.send_json({'type': 'hello', 'role': role, 'session': session, 'peer_connected': bool(other and not other.closed)})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    print('[BROKER] invalid json from {}'.format(role), flush=True)
                    continue
                payload.setdefault('from', role)
                payload.setdefault('broker_rx_mono_ns', time.monotonic_ns())
                target = peers.get(other_role)
                if target is not None and not target.closed:
                    await target.send_str(json.dumps(payload, separators=(',', ':')))
                elif payload.get('type') not in ('frame_meta', 'heartbeat'):
                    await ws.send_json({'type': 'peer', 'role': other_role, 'state': 'missing'})
            elif msg.type == web.WSMsgType.ERROR:
                print('[BROKER] ws error {} {}'.format(role, ws.exception()), flush=True)
    finally:
        if peers.get(role) is ws:
            peers.pop(role, None)
        target = peers.get(other_role)
        if target is not None and not target.closed:
            try:
                await target.send_json({'type': 'peer', 'role': role, 'state': 'disconnected'})
            except Exception:
                pass
        if not peers:
            SESSIONS.pop(session, None)
        print('[BROKER] {} disconnected session={}'.format(role, session), flush=True)

    return ws


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()

    app = web.Application()
    app.add_routes([web.get('/health', health), web.get('/ws', ws_handler)])
    print('[BROKER] listening on {}:{}'.format(args.host, args.port), flush=True)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == '__main__':
    main()
