import socket, struct
MAGIC = 0x2112A442
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 3479))
print("mini STUN server on 0.0.0.0:3479")
while True:
    data, peer = s.recvfrom(2048)
    if len(data) < 20:
        continue
    typ, mlen, cookie, tid = struct.unpack("!HHI12s", data[:20])
    if typ != 1 or cookie != MAGIC:
        continue
    ip = socket.inet_aton(peer[0])
    port = peer[1]
    xor_port = port ^ (MAGIC >> 16)
    xip = bytes(b ^ c for b, c in zip(ip, struct.pack("!I", MAGIC)))
    body = struct.pack("!HH", 0x0020, 8) + bytes([0x01, 0x01]) + struct.pack("!H", xor_port) + xip
    resp = struct.pack("!HHI12s", 0x0101, len(body), MAGIC, tid) + body
    s.sendto(resp, peer)
    print("served", peer)
