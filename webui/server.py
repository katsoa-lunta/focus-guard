"""Local HTTP server that hosts the FocusGuard web UI.

Standard library only: ThreadingHTTPServer serves the static files, a small JSON
API drives FocusController and Server-Sent Events push live state to the page.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from webui.controller import FocusController

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 7788
PORT_ATTEMPTS = 10


class Handler(BaseHTTPRequestHandler):
    controller: FocusController = None  # injected by make_server
    server_version = "FocusGuard"

    # ------------------------------------------------------------- utilities
    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        pass

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求体不是合法 JSON")
        return data if isinstance(data, dict) else {}

    def _serve_static(self, path: str) -> None:
        if path in ("/", ""):
            target = STATIC_DIR / "index.html"
        else:
            target = (STATIC_DIR / path.lstrip("/")).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self._send_error_json("not found", HTTPStatus.NOT_FOUND)
                return
            if not target.is_file():
                self._send_error_json("not found", HTTPStatus.NOT_FOUND)
                return
        ctype, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------- SSE
    def _stream_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(b"retry: 1000\n\n")
        self.wfile.flush()
        last = None
        try:
            while True:
                payload = json.dumps(self.controller.snapshot(), ensure_ascii=False)
                if payload != last:
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last = payload
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    # ------------------------------------------------------------------ verbs
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                self._send_json(self.controller.snapshot())
            elif path == "/api/preview":
                self._send_json(self.controller.preview())
            elif path == "/api/events":
                self._stream_events()
            else:
                self._serve_static(path)
        except Exception as exc:  # keep the server alive on unexpected errors
            self._send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/start":
                self._send_json({"ok": True, "state": self.controller.start(payload.get("minutes"))})
            elif path == "/api/pause":
                self._send_json({"ok": True, "state": self.controller.pause()})
            elif path == "/api/resume":
                self._send_json({"ok": True, "state": self.controller.resume()})
            elif path == "/api/stop":
                self._send_json({"ok": True, "state": self.controller.stop()})
            elif path == "/api/config":
                self._send_json({"ok": True, "state": self.controller.update_config(payload)})
            else:
                self._send_error_json("not found", HTTPStatus.NOT_FOUND)
        except PermissionError as exc:
            self._send_error_json(str(exc), HTTPStatus.FORBIDDEN)
        except ValueError as exc:
            self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)


def make_server(controller: FocusController, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
    """Bind the first free port starting at `port`."""
    Handler.controller = controller
    last_error = None
    for offset in range(PORT_ATTEMPTS):
        candidate = port + offset
        try:
            httpd = ThreadingHTTPServer((host, candidate), Handler)
            httpd.daemon_threads = True
            return httpd, candidate
        except OSError as exc:
            last_error = exc
            continue
    raise OSError(f"端口 {port}-{port + PORT_ATTEMPTS - 1} 都被占用：{last_error}")


def serve(controller: FocusController, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          ready: threading.Event | None = None, holder: dict | None = None):
    httpd, chosen = make_server(controller, host, port)
    if holder is not None:
        holder["port"] = chosen
        holder["httpd"] = httpd
    if ready is not None:
        ready.set()
    try:
        httpd.serve_forever(poll_interval=0.3)
    finally:
        httpd.server_close()
