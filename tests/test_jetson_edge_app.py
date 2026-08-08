import json
import socket
import time
import urllib.request

from robot.jetson_nano.mcqueen_edge.app import EdgeApp
from robot.jetson_nano.mcqueen_edge.drive import MockDriveBackend


def recv_until(sock, predicate, timeout=1.5):
    deadline = time.time() + timeout
    last = None

    while time.time() < deadline:
        sock.settimeout(max(0.05, deadline - time.time()))
        try:
            raw, _ = sock.recvfrom(2048)
        except socket.timeout:
            break

        text = raw.decode("ascii").strip()
        fields = text.split(",")
        last = text

        assert len(fields) == 11, text
        assert fields[0] == "S", text

        if predicate(fields):
            return fields, text

    raise AssertionError("Expected UDP status not received. Last: {}".format(last))


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=2.0) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url):
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=2.0) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


backend = MockDriveBackend()

app = EdgeApp(
    backend=backend,
    udp_host="127.0.0.1",
    udp_port=0,
    http_host="127.0.0.1",
    http_port=0,
)
app.start()

assert app.udp_port != 0
assert app.http_port != 0

# Prove HTTP and UDP are alive inside the SAME edge application.
base = "http://127.0.0.1:{}".format(app.http_port)
health = http_get_json(base + "/health")
assert health["ok"] is True

started = http_post_json(base + "/api/log/start")
assert started["recording"] is True
assert started["logging"] is True

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
target = ("127.0.0.1", app.udp_port)

client.sendto(b"H,rc-car,combo1,1,1000\n", target)
recv_until(client, lambda f: f[1] == "combo1" and f[8] == "1")

client.sendto(b"C,rc-car,combo1,2,1010,0,0,0\n", target)
recv_until(client, lambda f: f[2] == "2" and f[8] == "0")

client.sendto(b"C,rc-car,combo1,3,1020,200,500,1\n", target)
fields, status = recv_until(
    client,
    lambda f: f[2] == "3" and f[4] == "200" and f[6] == "500" and f[8] == "0",
)

stopped = http_post_json(base + "/api/log/stop")
assert stopped["recording"] is False
assert stopped["logging"] is False

print("UDP PORT    :", app.udp_port)
print("HTTP PORT   :", app.http_port)
print("UDP STATUS  :", status)
print("HTTP SESSION:", started["session"])
print("EDGE APP SELF-TEST : PASS")

client.close()
app.stop()

assert not app.teleop.is_alive()
assert not app.http.is_alive()
assert backend.calls[-1] == ("estop",)
