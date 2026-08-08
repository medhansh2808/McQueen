import json
import time
import urllib.error
import urllib.request

from robot.jetson_nano.mcqueen_edge.http_server import McQueenHTTPServer, RuntimeState


def get(url):
    with urllib.request.urlopen(url, timeout=2.0) as response:
        return response.status, response.headers.get_content_type(), response.read()


def post(url):
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return response.status, response.headers.get_content_type(), response.read()


state = RuntimeState()
server = McQueenHTTPServer(runtime_state=state, bind_host="127.0.0.1", port=0)
server.start()

deadline = time.time() + 2.0
while server.httpd is None and time.time() < deadline:
    time.sleep(0.01)

assert server.httpd is not None
assert server.port != 0

base = "http://127.0.0.1:{}".format(server.port)

status, content_type, body = get(base + "/health")
assert status == 200
assert content_type == "application/json"
assert json.loads(body.decode("utf-8"))["ok"] is True

status, content_type, body = get(base + "/")
assert status == 200
assert content_type == "text/html"
html = body.decode("utf-8")
assert "McQueen Camera" in html
assert "OAK-D/WebRTC" in html

status, content_type, body = get(base + "/status")
initial = json.loads(body.decode("utf-8"))
assert initial["recording"] is False
assert initial["logging"] is False
assert initial["camera_ready"] is False
assert initial["task"] == "Imitate expert driving"

status, content_type, body = post(base + "/api/log/start")
started = json.loads(body.decode("utf-8"))
assert started["recording"] is True
assert started["logging"] is True
assert started["session"].startswith("session-")
session = started["session"]

status, content_type, body = get(base + "/status")
during = json.loads(body.decode("utf-8"))
assert during["recording"] is True
assert during["logging"] is True
assert during["session"] == session

status, content_type, body = post(base + "/api/log/stop")
stopped = json.loads(body.decode("utf-8"))
assert stopped["recording"] is False
assert stopped["logging"] is False
assert stopped["session"] == session

try:
    get(base + "/does-not-exist")
except urllib.error.HTTPError as exc:
    assert exc.code == 404
else:
    raise AssertionError("Expected HTTP 404")

print("HTTP PORT   :", server.port)
print("SESSION     :", session)
print("FINAL STATUS:", state.snapshot())
print("HTTP SERVER SELF-TEST : PASS")

server.stop()
server.join(timeout=2.0)
assert not server.is_alive()
