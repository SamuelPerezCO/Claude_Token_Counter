"""Fetch Claude Code usage by reading the unified rate-limit response headers.

There is no dedicated usage endpoint. The trick (same as Clawdmeter's) is to send
the smallest possible request to /v1/messages and throw the reply away -- the
numbers we want ride along in the response headers:

    anthropic-ratelimit-unified-status               allowed | allowed_warning | rejected
    anthropic-ratelimit-unified-5h-utilization       fraction 0.0-1.0
    anthropic-ratelimit-unified-5h-reset             unix epoch seconds
    anthropic-ratelimit-unified-7d-utilization       fraction 0.0-1.0
    anthropic-ratelimit-unified-7d-reset             unix epoch seconds
    anthropic-ratelimit-unified-overage-utilization  fraction 0.0-1.0
    anthropic-ratelimit-unified-representative-claim which window is binding

Header values were confirmed against the live API rather than assumed.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from . import credentials

API_URL = "https://api.anthropic.com/v1/messages"

# max_tokens=1 keeps this as close to free as an API call gets: ~8 input tokens,
# 1 output token. It still returns the full set of rate-limit headers.
PROBE_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}

BASE_HEADERS = {
    "anthropic-version": "2023-06-01",
    # OAuth bearer tokens require this beta flag; without it /v1/messages 401s.
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.5",
}

WINDOWS = {
    "session": "5h",
    "week": "7d",
    "overage": "overage",
}


def _as_fraction(raw: str | None) -> float | None:
    """Parse a utilization header. The API reports a 0.0-1.0 fraction."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # Defensive: if the API ever switches to 0-100, don't render 4300%.
    if value > 1.0:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _as_epoch(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def parse_headers(headers: Any) -> dict:
    """Turn the unified rate-limit headers into a JSON-friendly snapshot."""

    def get(name: str) -> str | None:
        return headers.get(f"anthropic-ratelimit-unified-{name}")

    windows = {}
    for label, key in WINDOWS.items():
        utilization = _as_fraction(get(f"{key}-utilization"))
        if utilization is None and label == "overage":
            continue  # not every plan reports an overage window
        windows[label] = {
            "utilization": utilization,
            "reset": _as_epoch(get(f"{key}-reset")),
            "status": get(f"{key}-status"),
        }

    return {
        "status": get("status") or "unknown",
        "representative_claim": get("representative-claim"),
        "windows": windows,
    }


@dataclass
class Snapshot:
    """The latest known state. Always JSON-serialisable, never holds the token."""

    ok: bool = False
    fetched_at: float | None = None
    status: str = "unknown"
    representative_claim: str | None = None
    windows: dict = field(default_factory=dict)
    error: str | None = None
    account: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "fetched_at": self.fetched_at,
            "server_time": time.time(),
            "status": self.status,
            "representative_claim": self.representative_claim,
            "windows": self.windows,
            "error": self.error,
            "account": self.account,
        }


def fetch_once(timeout: float = 30.0) -> Snapshot:
    """Make one probe request and return a snapshot of the rate-limit state."""
    try:
        creds = credentials.load()
    except credentials.CredentialsError as exc:
        return Snapshot(ok=False, error=str(exc), fetched_at=time.time())

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(PROBE_BODY).encode("utf-8"),
        headers={**BASE_HEADERS, "Authorization": f"Bearer {creds.access_token}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = response.headers
            response.read()  # drain so the connection can be reused/closed cleanly
    except urllib.error.HTTPError as exc:
        # A 429 still carries the rate-limit headers, and they're exactly what we
        # want to show -- so parse them rather than treating this as a failure.
        headers = exc.headers
        if exc.code == 401:
            return Snapshot(
                ok=False,
                fetched_at=time.time(),
                error="Token rejected (401). Run `claude` once to refresh your login.",
            )
        if not headers or not headers.get("anthropic-ratelimit-unified-status"):
            return Snapshot(
                ok=False,
                fetched_at=time.time(),
                error=f"API returned HTTP {exc.code}: {exc.reason}",
            )
    except urllib.error.URLError as exc:
        return Snapshot(ok=False, fetched_at=time.time(), error=f"Network error: {exc.reason}")
    except TimeoutError:
        return Snapshot(ok=False, fetched_at=time.time(), error="Request timed out")

    parsed = parse_headers(headers)
    if not parsed["windows"]:
        return Snapshot(
            ok=False,
            fetched_at=time.time(),
            error="Response carried no unified rate-limit headers.",
        )

    return Snapshot(
        ok=True,
        fetched_at=time.time(),
        status=parsed["status"],
        representative_claim=parsed["representative_claim"],
        windows=parsed["windows"],
        account=creds.subscription_type,
    )


class Poller:
    """Refreshes the snapshot on a timer in a background thread."""

    def __init__(self, interval: float = 60.0) -> None:
        self.interval = interval
        self._snapshot = Snapshot(error="Starting up...")
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def refresh_now(self) -> None:
        """Ask the polling thread to fetch immediately instead of waiting."""
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snapshot = fetch_once()
            except Exception as exc:  # a poller thread must never die
                snapshot = Snapshot(ok=False, fetched_at=time.time(), error=repr(exc))
            with self._lock:
                self._snapshot = snapshot
            self._wake.wait(self.interval)
            self._wake.clear()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="usage-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
