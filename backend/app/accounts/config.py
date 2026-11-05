"""Account settings are opt-in and independent from the learning core."""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

LINK_TTL_SECONDS = 900
SESSION_DAYS = 30
MFA_RECENCY_SECONDS = 900


def _boolean(name: str) -> bool:
    value = os.getenv(name, "false").lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be 'true' or 'false'")
    return value == "true"


def _url(value: str, *, origin: bool = False) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or (origin and parsed.path)
        or any(char.isspace() for char in value)
    ):
        raise ValueError("Account URLs must be explicit HTTP(S) URLs without credentials")
    _ = parsed.port


@dataclass(frozen=True, slots=True)
class AccountSettings:
    enabled: bool = False
    policy_approved: bool = False
    policy_version: str | None = None
    policy_url: str | None = None
    public_origin: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    smtp_from: str | None = None
    smtp_tls: str = "starttls"
    smtp_timeout_seconds: int = 5
    mfa_encryption_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.policy_version is not None and not re.fullmatch(
            r"[A-Za-z0-9._-]{1,64}", self.policy_version
        ):
            raise ValueError("ACCOUNTS_POLICY_VERSION must be a bounded version identifier")
        if self.policy_url is not None:
            _url(self.policy_url)
        if self.public_origin is not None:
            _url(self.public_origin, origin=True)
        if self.smtp_tls not in {"starttls", "ssl"}:
            raise ValueError("ACCOUNTS_SMTP_TLS must be 'starttls' or 'ssl'")
        if not 1 <= self.smtp_port <= 65535 or not 1 <= self.smtp_timeout_seconds <= 10:
            raise ValueError("SMTP port or timeout outside the supported range")
        for value in (self.smtp_host, self.smtp_username, self.smtp_from):
            if value is not None and (not value or "\r" in value or "\n" in value):
                raise ValueError("SMTP settings must not contain line breaks or empty values")
        if self.mfa_encryption_key is not None:
            try:
                Fernet(self.mfa_encryption_key)
            except (ValueError, TypeError) as exc:
                raise ValueError("ACCOUNTS_MFA_ENCRYPTION_KEY must be a Fernet key") from exc

    @property
    def policy_ready(self) -> bool:
        return bool(
            self.enabled and self.policy_approved and self.policy_version
            and self.policy_url and self.public_origin
        )

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and self.smtp_from)

    @classmethod
    def from_env(cls) -> "AccountSettings":
        return cls(
            enabled=_boolean("ACCOUNTS_ENABLED"),
            policy_approved=_boolean("ACCOUNTS_POLICY_APPROVED"),
            policy_version=os.getenv("ACCOUNTS_POLICY_VERSION"),
            policy_url=os.getenv("ACCOUNTS_POLICY_URL"),
            public_origin=os.getenv("ACCOUNTS_PUBLIC_ORIGIN"),
            smtp_host=os.getenv("ACCOUNTS_SMTP_HOST"),
            smtp_port=int(os.getenv("ACCOUNTS_SMTP_PORT", "587")),
            smtp_username=os.getenv("ACCOUNTS_SMTP_USERNAME"),
            smtp_password=os.getenv("ACCOUNTS_SMTP_PASSWORD"),
            smtp_from=os.getenv("ACCOUNTS_SMTP_FROM"),
            smtp_tls=os.getenv("ACCOUNTS_SMTP_TLS", "starttls"),
            smtp_timeout_seconds=int(os.getenv("ACCOUNTS_SMTP_TIMEOUT_SECONDS", "5")),
            mfa_encryption_key=os.getenv("ACCOUNTS_MFA_ENCRYPTION_KEY"),
        )
