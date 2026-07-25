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
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
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

# Transient server-side conditions. urllib has no reason phrase for the
# non-standard 529, so it would otherwise surface as a bare "<none>".
RETRYABLE_STATUS = {408, 500, 502, 503, 504, 529}

HTTP_EXPLANATIONS = {
    408: "The request timed out on Anthropic's side.",
    500: "Anthropic hit an internal error.",
    502: "Bad gateway while reaching Anthropic.",
    503: "Anthropic's API is unavailable.",
    529: "Anthropic's API is temporarily overloaded.",
}

MAX_ATTEMPTS = 3


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
    # True when the numbers are real but the most recent refresh failed, so the
    # dashboard can keep showing them instead of blanking out over a blip.
    stale: bool = False

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
            "stale": self.stale,
        }


def _describe_http_error(code: int, reason: Any) -> str:
    """Readable text for an HTTP failure.

    urllib has no reason phrase for non-standard codes like 529, so the raw
    value renders as an unhelpful "<none>".
    """
    if explanation := HTTP_EXPLANATIONS.get(code):
        return f"{explanation} (HTTP {code})"
    return f"API returned HTTP {code}" + (f": {reason}" if reason else "")


def fetch_once(timeout: float = 30.0) -> Snapshot:
    """Probe the API and snapshot the rate-limit state, retrying transient errors."""
    try:
        creds = credentials.load()
    except credentials.CredentialsError as exc:
        return Snapshot(ok=False, error=str(exc), fetched_at=time.time())

    last_error = "Unknown error"

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            # Exponential backoff with jitter. Retrying an overloaded API in
            # lockstep is how a brief blip turns into a stampede.
            time.sleep(min(2**attempt, 8) + random.uniform(0, 0.5))

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(PROBE_BODY).encode("utf-8"),
            headers={**BASE_HEADERS, "Authorization": f"Bearer {creds.access_token}"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                headers = response.headers
                response.read()  # drain so the connection closes cleanly
        except urllib.error.HTTPError as exc:
            headers = exc.headers
            if headers and headers.get("anthropic-ratelimit-unified-status"):
                # A 429 still carries the rate-limit headers, and being throttled
                # is precisely what we want to display -- fall through and parse.
                pass
            elif exc.code == 401:
                return Snapshot(
                    ok=False,
                    fetched_at=time.time(),
                    error="Token rejected (401). Run `claude` once to refresh your login.",
                )
            else:
                last_error = _describe_http_error(exc.code, exc.reason)
                if exc.code in RETRYABLE_STATUS:
                    continue
                return Snapshot(ok=False, fetched_at=time.time(), error=last_error)
        except urllib.error.URLError as exc:
            # HTTPError subclasses URLError, so this only catches transport faults.
            last_error = f"Network error: {exc.reason}"
            continue
        except TimeoutError:
            last_error = "Request timed out"
            continue

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

    return Snapshot(ok=False, fetched_at=time.time(), error=last_error)


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
                result = fetch_once()
            except Exception as exc:  # a poller thread must never die
                result = Snapshot(ok=False, fetched_at=time.time(), error=repr(exc))

            with self._lock:
                previous = self._snapshot
                if result.ok:
                    self._snapshot = result
                elif previous.ok:
                    # Keep the last real numbers on screen and flag the problem,
                    # rather than blanking the dashboard over a transient outage.
                    # fetched_at stays put, so the age shown keeps climbing.
                    self._snapshot = replace(previous, stale=True, error=result.error)
                else:
                    self._snapshot = result
                degraded = not self._snapshot.ok or self._snapshot.stale

            # Check back sooner while degraded so recovery shows up promptly, but
            # not so fast that we pile onto an API that is already struggling.
            self._wake.wait(min(self.interval, 20.0) if degraded else self.interval)
            self._wake.clear()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="usage-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
