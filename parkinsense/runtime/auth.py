"""
API access token (WP-03, ADR-0016).

The runtime API binds to 127.0.0.1 by default. Every state-changing request (POST) must carry the token in the
`X-ParkinSense-Token` header; when the API is bound to a non-loopback address (opt-in LAN access) reads need it too,
except `/health`. Token lookup order, shared by the runtime (server) and the dashboard (client):

  1. `$PARKINSENSE_TOKEN`
  2. the token file `$PARKINSENSE_TOKEN_FILE` or `~/.parkinsense/api_token` (mode 0600)

The server creates the file if neither exists; clients never create it. A launcher that starts the runtime and the
dashboard on one machine therefore needs no configuration.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

HEADER = "X-ParkinSense-Token"
ENV_TOKEN = "PARKINSENSE_TOKEN"
ENV_FILE = "PARKINSENSE_TOKEN_FILE"
MIN_TOKEN_LENGTH = 16
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def token_path() -> Path:
    return Path(os.environ.get(ENV_FILE) or Path.home() / ".parkinsense" / "api_token")


def is_loopback(host: str) -> bool:
    return host in LOOPBACK_HOSTS


def read_token() -> str | None:
    """The configured token or None. Never creates anything (used by clients)."""
    t = os.environ.get(ENV_TOKEN, "").strip()
    if t:
        return t
    p = token_path()
    try:
        return p.read_text().strip() or None
    except OSError:
        return None


def load_or_create_token(explicit: str | None = None) -> str:
    """Server side: explicit (`--token`) > env > file > newly generated and stored with mode 0600."""
    t = (explicit or "").strip() or read_token()
    if t:
        if len(t) < MIN_TOKEN_LENGTH:
            raise ValueError(f"API token must be at least {MIN_TOKEN_LENGTH} characters")
        return t
    t = secrets.token_urlsafe(32)
    p = token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t + "\n")
    return t


def check(provided: str | None, expected: str | None) -> bool:
    return bool(provided) and bool(expected) and secrets.compare_digest(provided, expected)
