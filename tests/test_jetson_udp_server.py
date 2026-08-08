import socket
import time

from robot.jetson_nano.mcqueen_edge.drive import MockDriveBackend
from robot.jetson_nano.mcqueen_edge.server import TeleopServer


def recv_status(sock, timeout=1.0):
    sock.settimeout(timeout)
    raw, _ = sock.recvfrom(2048)
    text = raw.decode("ascii").strip()
    fields = text.split(",")
    assert len(fields) == 11, text
    assert fields[0] == "S", text
    return fields, text


def recv_until(sock, predicate, timeout=1.5):
    deadline = time.time() + timeout
    last_text = None
    while time.time() < deadline:
        remaining = max(0.05, deadline - time.time())
        try:
            fields, text = recv_status(sock, timeout=remaining)
        except socket.timeout:
            break
        last_text = text
        if predicate(fields):
            return fields, text
    raise AssertionError("Expected status not received. Last status: {}".format(last_text))


backend = MockDriveBackend()
server = TeleopServer(
    backend=backend,
    bind_host="127.0.0.1",
    port=0,
    failsafe_seconds=0.300,
    status_hz=30.0,
)
server.start()

deadline = time.time() + 2.0
while server.port == 0 and time.time() < deadline:
    time.sleep(0.01)

assert server.port != 0

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
target = ("127.0.0.1", server.port)

# HELLO establishes session and should result in a safe state.
client.sendto(b"H,rc-car,phone123,1,1000\n", target)
fields, text = recv_until(client, lambda f: f[1] == "phone123" and f[8] == "1")

# First neutral command arms the new session.
client.sendto(b"C,rc-car,phone123,2,1010,0,0,0\n", target)
fields, text = recv_until(
    client,
    lambda f: f[2] == "2" and f[4] == "0" and f[6] == "0" and f[8] == "0",
)

# Normal drive packet.
client.sendto(b"C,rc-car,phone123,3,1020,-250,700,1\n", target)
fields, text = recv_until(
    client,
    lambda f: f[2] == "3" and f[4] == "-250" and f[6] == "700" and f[8] == "0",
)
assert fields[9] == "JETSON"

# Duplicate sequence must not replace the accepted drive state.
client.sendto(b"C,rc-car,phone123,3,1030,999,999,1\n", target)
fields, text = recv_until(
    client,
    lambda f: f[2] == "3" and f[4] == "-250" and f[6] == "700",
)

# Wait for the 300 ms watchdog. Ignore any older queued status packets and
# specifically wait for the safe/failsafe status.
fields, text = recv_until(
    client,
    lambda f: f[4] == "0" and f[6] == "0" and f[8] == "1",
    timeout=1.5,
)

# Explicit ESTOP remains safe.
client.sendto(b"E,rc-car,phone123,4,1400\n", target)
fields, text = recv_until(
    client,
    lambda f: f[2] == "4" and f[8] == "1",
)

print("SERVER PORT :", server.port)
print("LAST STATUS :", text)
print("BACKEND CALLS:", backend.calls)
print("UDP SERVER SELF-TEST : PASS")

server.stop()
server.join(timeout=2.0)
client.close()

assert not server.is_alive()
