"""Durable guest state, immutable feedback, and frozen content revisions."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Keep aware UTC dates on PostgreSQL and restore awareness on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Database timestamps must be timezone-aware")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LearningSessionRecord(Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint("mode = 'practice'", name="practice_mode"),
        CheckConstraint("status IN ('active', 'completed')", name="session_status"),
        CheckConstraint("requested_length IN (5, 10, 20)", name="session_length"),
        CheckConstraint("current_index >= 0", name="nonnegative_index"),
        CheckConstraint("draft_revision >= 0", name="nonnegative_revision"),
        CheckConstraint(
            "(status = 'active' AND completed_at IS NULL AND summary_snapshot IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL AND summary_snapshot IS NOT NULL)",
            name="completion_snapshot",
        ),
        Index("ix_learning_sessions_guest_created", "guest_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_length: Mapped[int] = mapped_column(Integer, nullable=False)
    notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    tasks_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    options_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    drafts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    help_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active_seconds: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    summary_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )


class AttemptRecord(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_attempts_session_sequence"),
        CheckConstraint("active_seconds >= 0 AND active_seconds <= 86400", name="bounded_time"),
        CheckConstraint("NOT skipped OR NOT independent", name="skip_is_not_independent"),
        CheckConstraint("NOT independent OR first_attempt", name="independent_is_first"),
        Index("ix_attempts_guest_task", "guest_id", "task_id"),
        Index("ix_attempts_session_sequence", "session_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("learning_sessions.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_answer: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    assisted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_attempt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    independent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    checker_revision: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class SeenTask(Base):
    __tablename__ = "seen_tasks"
    __table_args__ = (
        UniqueConstraint("guest_id", "task_id", name="uq_seen_tasks_guest_task"),
        Index("ix_seen_tasks_guest_seen", "guest_id", "last_seen_at"),
        Index("ix_seen_tasks_guest_instance", "guest_id", "instance_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instance_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    assistance_seen: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference_seen: Mapped[bool] = mapped_column(Boolean, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("guest_id", "request_key", name="uq_idempotency_guest_key"),
        CheckConstraint("status_code >= 200 AND status_code <= 599", name="response_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    request_key: Mapped[str] = mapped_column(String(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(256), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
