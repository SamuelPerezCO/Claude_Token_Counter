"""Tiny local HTTP server exposing the usage snapshot and the dashboard page."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .usage import Poller


def static_dir() -> Path:
    """Where index.html lives, both in dev and inside a PyInstaller bundle."""
    if bundle := getattr(sys, "_MEIPASS", None):
        return Path(bundle) / "claude_meter" / "static"
    return Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    poller: Poller  # injected by make_server
    quiet: bool = True

    server_version = "ClaudeMeter"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        if not self.quiet:
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Always fresh: this is a live dashboard on a LAN, caching only confuses.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        route = self.path.split("?", 1)[0].rstrip("/") or "/"

        if route == "/":
            index = static_dir() / "index.html"
            try:
                self._send(200, index.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"dashboard asset missing", "text/plain; charset=utf-8")
            return

        if route == "/api/usage":
            payload = json.dumps(self.poller.snapshot.to_dict()).encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8")
            return

        if route == "/api/refresh":
            self.poller.refresh_now()
            self._send(202, b'{"queued":true}', "application/json; charset=utf-8")
            return

        if route == "/healthz":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def make_server(host: str, port: int, poller: Poller, quiet: bool = True) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"poller": poller, "quiet": quiet})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
