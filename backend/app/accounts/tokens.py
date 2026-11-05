"""High-entropy bearer values are stored only as SHA-256 digests."""

import hashlib
import re
import secrets

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(value: str | None) -> str | None:
    if value is None or not _TOKEN.fullmatch(value):
        return None
    return hashlib.sha256(value.encode("ascii")).hexdigest()
