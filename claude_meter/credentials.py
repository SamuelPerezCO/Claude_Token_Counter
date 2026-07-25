"""Locate and read the Claude Code OAuth credentials.

The token is re-read from disk on every poll so that refreshes performed by
Claude Code itself are picked up without restarting this app. We never write to
the file and never expose the token outside this process.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


class CredentialsError(RuntimeError):
    """Raised when no usable OAuth token can be found on disk."""


@dataclass(frozen=True)
class Credentials:
    access_token: str
    source: Path
    expires_at: int | None = None
    subscription_type: str | None = None


def candidate_paths() -> list[Path]:
    """Every location a Claude Code credentials file might live, in priority order."""
    if override := os.environ.get("CLAUDE_CREDENTIALS_PATH"):
        return [Path(override)]
    if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
        return [Path(config_dir) / ".credentials.json"]

    home = Path.home()
    paths = [home / ".claude" / ".credentials.json"]
    for var in ("LOCALAPPDATA", "APPDATA"):
        if base := os.environ.get(var):
            paths.append(Path(base) / "Claude" / ".credentials.json")
    # Linux/macOS fallbacks, so the same code runs off-Windows.
    paths.append(home / ".config" / "claude" / ".credentials.json")
    return paths


def _extract_token(blob: dict) -> tuple[str, dict]:
    """Pull the access token out of either the nested or flat credentials shape."""
    # Observed shape: {"claudeAiOauth": {"accessToken": ..., "expiresAt": ...}}
    oauth = blob.get("claudeAiOauth")
    if isinstance(oauth, dict) and oauth.get("accessToken"):
        return oauth["accessToken"], oauth
    # Older/flat shape: {"accessToken": ...}
    if blob.get("accessToken"):
        return blob["accessToken"], blob
    raise CredentialsError("credentials file has no 'accessToken' field")


def load() -> Credentials:
    """Read the first credentials file that parses and contains a token."""
    tried: list[str] = []
    for path in candidate_paths():
        if not path.is_file():
            tried.append(f"{path} (not found)")
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            tried.append(f"{path} ({exc.__class__.__name__})")
            continue

        try:
            token, section = _extract_token(blob)
        except CredentialsError as exc:
            tried.append(f"{path} ({exc})")
            continue

        expires_at = section.get("expiresAt")
        return Credentials(
            access_token=token,
            source=path,
            # expiresAt is milliseconds since epoch; normalise to seconds.
            expires_at=int(expires_at) // 1000 if isinstance(expires_at, (int, float)) else None,
            subscription_type=section.get("subscriptionType"),
        )

    raise CredentialsError(
        "No Claude Code OAuth credentials found. Log in with the Claude Code CLI "
        "first (`claude`), or point CLAUDE_CREDENTIALS_PATH at the file.\nTried:\n  "
        + "\n  ".join(tried)
    )
