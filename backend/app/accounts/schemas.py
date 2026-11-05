"""Allowlisted account DTOs; never serialize authentication ORM records."""

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas import LearningSession, Schema, StrictInteger


class AuthConfig(Schema):
    enabled: bool
    policy_version: str | None
    policy_url: str | None
    link_ttl_seconds: int


class LinkRequest(Schema):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    accept_policy: bool

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        return normalize_email(value)


def normalize_email(value: str) -> str:
    """SMTP ASCII addresses, normalized identically for login, limits and CLI."""
    value = value.strip().lower()
    local, separator, domain = value.rpartition("@")
    if (
        not separator or not 1 <= len(local) <= 64 or len(value) > 254
        or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
        or local.startswith(".") or local.endswith(".") or ".." in local
        or len(domain.split(".")) < 2
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
               for label in domain.split("."))
    ):
        raise ValueError("Provide a valid ASCII email address")
    return value


class LinkComplete(Schema):
    token: Annotated[str, Field(min_length=1, max_length=256)]


class Message(Schema):
    message: str


class AccountView(Schema):
    id: str
    email: str
    email_verified: bool
    role: Literal["student", "methodist", "admin"]
    root_guest_id: str
    owner_ids: list[str]
    created_at: str
    policy_version: str
    consented_at: str
    daily_minutes: Literal[10, 20, 30]
    mfa_enabled: bool
    mfa_verified_until: str | None


class ConsentView(Schema):
    policy_version: str
    accepted_at: str


class DeletionRequest(Schema):
    confirm: bool


class DeletionView(Schema):
    id: str
    status: Literal["requested"]
    requested_at: str
    deadline_at: str


class DeletionStatus(Schema):
    request: DeletionView | None


class DeletionCancellation(Schema):
    id: str
    status: Literal["canceled"] = "canceled"
    requested_at: str
    deadline_at: str
    canceled_at: str


class DeletionReceipt(Schema):
    request_id: str
    status: Literal["completed"] = "completed"
    scope: Literal["active_cloud_v1"]
    requested_at: str
    deadline_at: str
    completed_at: str


class AccountExport(Schema):
    version: Literal["1"]
    exported_at: str
    account: AccountView
    sessions: list[LearningSession]
    consents: list[ConsentView]
    deletion_request: DeletionView | None


class AccountPatch(Schema):
    daily_minutes: Annotated[Literal[10, 20, 30], StrictInteger]


class Success(Schema):
    ok: Literal[True] = True


class AccessSessionView(Schema):
    id: str
    created_at: str
    last_seen_at: str
    expires_at: str
    current: bool
    mfa_verified_until: str | None


class ActiveSessions(Schema):
    sessions: list[AccessSessionView]


class MFACode(Schema):
    code: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")]


class MFAEnrollment(Schema):
    secret: str
    provisioning_uri: str
    expires_at: str


class MFAStatus(Schema):
    enabled: bool
    verified_until: str
