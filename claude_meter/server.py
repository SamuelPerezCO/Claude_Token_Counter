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


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    poller: Poller  # injected by make_server
    quiet: bool = True

    server_version = "ClaudeMeter"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        if not self.quiet:
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Live data is never cached; immutable assets like the logo may be.
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_asset(self, name: str) -> bool:
        """Serve a file from the static directory. Returns False if not eligible."""
        root = static_dir().resolve()
        target = (root / name).resolve()
        # `name` comes off the URL, so resolve first and confirm the result is
        # still inside the static directory -- otherwise ../../ escapes it.
        if not target.is_relative_to(root) or not target.is_file():
            return False
        content_type = CONTENT_TYPES.get(target.suffix.lower())
        if content_type is None:
            return False
        self._send(200, target.read_bytes(), content_type, cache="public, max-age=3600")
        return True

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

        # Anything else may be a static asset (the logo, a favicon request).
        if "/" not in route.lstrip("/") and self._serve_asset(route.lstrip("/")):
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def make_server(host: str, port: int, poller: Poller, quiet: bool = True) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"poller": poller, "quiet": quiet})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
