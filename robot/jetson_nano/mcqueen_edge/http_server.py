"""HTTP compatibility server for the existing McQueen Android app.

Compatible with Python 3.6+ so it runs on the Jetson Nano Ubuntu 18.04 image.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class RuntimeState:
    def __init__(self):
        self._lock = threading.Lock()
        self.camera_ready = False
        self.recording = False
        self.logging = False
        self.session = ""
        self.episode = ""
        self.frame_index = 0
        self.task = "Imitate expert driving"

    def snapshot(self):
        with self._lock:
            return {
                "ok": True,
                "success": True,
                "camera_ready": bool(self.camera_ready),
                "recording": bool(self.recording),
                "logging": bool(self.logging),
                "session": self.session,
                "episode": self.episode,
                "frame_index": int(self.frame_index),
                "recording_fps": 10,
                "rgb_width": 1280,
                "rgb_height": 720,
                "task": self.task,
            }

    def set_camera_ready(self, ready):
        with self._lock:
            self.camera_ready = bool(ready)

    def set_episode(self, episode, frame_index=0):
        with self._lock:
            self.episode = str(episode)
            self.frame_index = int(frame_index)

    def set_frame_index(self, frame_index):
        with self._lock:
            self.frame_index = int(frame_index)

    def start_recording(self):
        with self._lock:
            if not self.camera_ready:
                return {
                    "ok": False,
                    "success": False,
                    "recording": False,
                    "logging": False,
                    "session": self.session,
                    "error": "camera not ready",
                }

            if not self.session:
                self.session = time.strftime(
                    "session_%Y%m%d_%H%M%S",
                    time.localtime(),
                )

            self.logging = True
            self.recording = True

            return {
                "ok": True,
                "success": True,
                "recording": True,
                "logging": True,
                "session": self.session,
            }

    def stop_recording(self):
        with self._lock:
            self.logging = False
            self.recording = False

            return {
                "ok": True,
                "success": True,
                "recording": False,
                "logging": False,
                "session": self.session,
                "episode": self.episode,
                "frame_index": int(self.frame_index),
            }


CAMERA_PLACEHOLDER_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>McQueen Camera</title>
</head>
<body>
  <h2>McQueen Camera</h2>
  <p>Jetson-local camera capture is active for dataset recording.</p>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "McQueenHTTP/1.0"

    def log_message(self, format, *args):
        return

    @property
    def runtime_state(self):
        return self.server.runtime_state

    def _json(self, payload, status=200):
        body = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html, status=200):
        body = html.encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/":
            self._html(CAMERA_PLACEHOLDER_HTML)
            return

        if path == "/health":
            self._json({"ok": True, "success": True})
            return

        if path == "/status":
            self._json(self.runtime_state.snapshot())
            return

        self._json(
            {
                "ok": False,
                "success": False,
                "error": "not found",
            },
            status=404,
        )

    def do_POST(self):
        path = self.path.split("?", 1)[0]

        length = int(
            self.headers.get("Content-Length", "0") or "0"
        )
        if length:
            self.rfile.read(length)

        if path == "/api/log/start":
            self._json(self.runtime_state.start_recording())
            return

        if path == "/api/log/stop":
            self._json(self.runtime_state.stop_recording())
            return

        self._json(
            {
                "ok": False,
                "success": False,
                "error": "not found",
            },
            status=404,
        )


class McQueenHTTPServer(threading.Thread):
    def __init__(
        self,
        runtime_state=None,
        bind_host="0.0.0.0",
        port=8080,
    ):
        threading.Thread.__init__(self, name="mcqueen-http")
        self.daemon = True

        self.runtime_state = runtime_state or RuntimeState()
        self.bind_host = str(bind_host)
        self.port = int(port)
        self.httpd = None

    def run(self):
        httpd = ThreadingHTTPServer(
            (self.bind_host, self.port),
            _Handler,
        )
        httpd.runtime_state = self.runtime_state
        self.httpd = httpd
        self.port = int(httpd.server_address[1])
        httpd.serve_forever(poll_interval=0.05)

    def stop(self):
        httpd = self.httpd
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def main():
    server = McQueenHTTPServer()
    server.start()

    deadline = time.time() + 2.0
    while server.httpd is None and time.time() < deadline:
        time.sleep(0.01)

    print(
        "McQueen HTTP server listening on http://0.0.0.0:{}".format(
            server.port
        ),
        flush=True,
    )

    try:
        while server.is_alive():
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.join(timeout=2.0)


if __name__ == "__main__":
    main()
