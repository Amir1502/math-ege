"""Bounded standard-library HTTP with one in-memory cookie jar per logical user."""

import json
import time
import urllib.error
import urllib.request
from http.client import HTTPException
from http.cookiejar import CookieJar
from typing import Any

from app.operations.common import OperationError, json_bytes

MAX_RESPONSE_BYTES = 2_097_152


class TransportError(OperationError):
    """Retain an already received status, never a URL, response fragment or secret."""

    def __init__(self, code: str, status_code: int = 0) -> None:
        super().__init__(code)
        self.status_code = status_code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send a write or credential to a server-supplied redirect target.
        return None


class HttpTransport:
    def __init__(self, target: str, *, namespace: str, timeout_seconds: int) -> None:
        self.target = target
        self.namespace = namespace
        self.timeout = timeout_seconds
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect(),
            urllib.request.HTTPCookieProcessor(self.cookies),
        )

    @property
    def has_cookie(self) -> bool:
        return len(self.cookies) > 0

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None,
    ) -> tuple[int, Any]:
        headers = {
            "Accept": "application/json", "User-Agent": "math-ege-verification-load/1",
            "X-Math-Ege-Verification": self.namespace,
        }
        if method != "GET":
            headers.update({"Origin": self.target, "X-Requested-With": "math-ege",
                            "Content-Type": "application/json"})
        if key is not None:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(
            self.target + path, data=None if body is None else json_bytes(body),
            headers=headers, method=method,
        )
        deadline = time.monotonic() + self.timeout
        status = 0
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = response.code
                raw = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise TransportError("load_response_deadline_exceeded", status)
                    chunk = response.read1(min(16_384, MAX_RESPONSE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise TransportError("load_response_size_exceeded", status)
                declared_length = response.headers.get("Content-Length")
                if declared_length is not None and not response.headers.get("Transfer-Encoding"):
                    try:
                        complete = int(declared_length) == len(raw)
                    except ValueError:
                        complete = False
                    if not complete:
                        raise TransportError("load_response_incomplete", status)
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    # Preserve the status for 5xx accounting, but never return body text.
                    payload = None
                return status, payload
        except (OSError, urllib.error.URLError, HTTPException):
            raise TransportError("load_transport_failed", status) from None
