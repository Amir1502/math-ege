"""Additive account records; historic practice owners and event IDs never move."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, UTCDateTime


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'methodist', 'admin')", name="account_role"),
        CheckConstraint("daily_minutes IN (10, 20, 30)", name="daily_minutes"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    root_guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    email_verified_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    daily_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=20)


class GuestClaim(Base):
    __tablename__ = "guest_claims"

    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AccessSession(Base):
    __tablename__ = "access_sessions"
    __table_args__ = (Index("ix_access_sessions_account_created", "account_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MagicLink(Base):
    __tablename__ = "account_magic_links"
    __table_args__ = (Index("ix_account_magic_links_email_created", "email", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    browser_state_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    browser_credential_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Keep the privacy association when MFA rotates the original bearer digest.
    credential_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), index=True, nullable=True,
    )
    guest_id: Mapped[str | None] = mapped_column(ForeignKey("guests.id"), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AuthRateLimit(Base):
    __tablename__ = "account_rate_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    events: Mapped[list[float]] = mapped_column(JSON, nullable=False)


class AccountConsent(Base):
    __tablename__ = "account_consents"
    __table_args__ = (
        UniqueConstraint("account_id", "policy_version", name="uq_account_consents_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"
    __table_args__ = (
        CheckConstraint("status = 'requested'", name="request_only"),
        CheckConstraint("deadline_at > requested_at", name="future_deadline"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), unique=True, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class AccountDeletionCancellation(Base):
    """Terminal request IDs, retained privately until the account itself is removed."""

    __tablename__ = "account_deletion_cancellations"
    __table_args__ = (
        CheckConstraint("deadline_at > requested_at", name="future_deadline"),
        CheckConstraint("canceled_at >= requested_at", name="cancellation_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    canceled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AccountDeletionReceipt(Base):
    """An immutable completion fact with no account, owner, email or credential linkage."""

    __tablename__ = "account_deletion_receipts"
    __table_args__ = (
        CheckConstraint("deadline_at > requested_at", name="future_deadline"),
        CheckConstraint("completed_at >= requested_at", name="completion_time"),
        CheckConstraint("scope = 'active_cloud_v1'", name="known_scope"),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)


class TotpCredential(Base):
    __tablename__ = "account_totp_credentials"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    enrollment_session_id: Mapped[str] = mapped_column(
        ForeignKey("access_sessions.id", name="fk_account_totp_credentials_enrollment_session"),
        nullable=False,
    )
    enrollment_expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_timecode: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1)
    attempts: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)


class AccountRoleAudit(Base):
    __tablename__ = "account_role_audit"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND subject_id IS NULL) OR "
            "(account_id IS NULL AND subject_id IS NOT NULL)", name="audit_subject",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), index=True, nullable=True,
    )
    # Same pseudonymous subject as editorial attribution; no surviving email mapping.
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    previous_role: Mapped[str] = mapped_column(String(16), nullable=False)
    new_role: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
