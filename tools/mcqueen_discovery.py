#!/usr/bin/env python3

import socket

DISCOVERY_PORT = 5006
CONTROL_PORT = 5007
HTTP_PORT = 8080
TELEMETRY_PORT = 5008

REQUEST = b"KACHOW_DISCOVER_V1"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(("0.0.0.0", DISCOVERY_PORT))

print(f"McQueen discovery listening on UDP {DISCOVERY_PORT}", flush=True)

while True:
    data, address = sock.recvfrom(512)

    if data.strip() != REQUEST:
        continue

    # Blank IP intentionally makes Android use the packet source IP.
    replies = (
        f"KACHOW_CAR_V1,,{CONTROL_PORT}\n",
        f"KACHOW_HOST_V1,,{HTTP_PORT},{TELEMETRY_PORT}\n",
    )

    for reply in replies:
        sock.sendto(reply.encode("ascii"), address)

    print(f"Discovery reply -> {address[0]}", flush=True)
