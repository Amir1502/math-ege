"""Additive editorial storage. Published payloads and historical results are never edited."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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


class EditorRevision(Base):
    __tablename__ = "editor_revisions"
    __table_args__ = (
        UniqueConstraint("kind", "content_id", "version", name="uq_editor_content_version"),
        CheckConstraint("kind IN ('task', 'lesson', 'profile', 'template')", name="kind"),
        CheckConstraint(
            "status IN ('draft', 'review', 'ready', 'published', 'archived')",
            name="status",
        ),
        CheckConstraint("version >= 1 AND revision >= 1", name="positive_revisions"),
        CheckConstraint("reviewer_id IS NULL OR reviewer_id <> author_id", name="independent"),
        CheckConstraint(
            "status NOT IN ('ready', 'published') OR "
            "(reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="review_gate",
        ),
        Index("ix_editor_revisions_kind_status", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("editor_revisions.id"), nullable=True)
    # Pseudonymous account IDs remain in the audit even after an account is removed.
    author_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_note: Mapped[str] = mapped_column(Text, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_formula: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_constraints: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EditorCatalog(Base):
    """A single lock serializes cross-account publication and version allocation."""

    __tablename__ = "editor_catalog"
    __table_args__ = (CheckConstraint("id = 1 AND revision >= 0", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("editor_revisions.id"),
        nullable=True,
    )


class EditorPublication(Base):
    """An explicit withdrawn pointer is a tombstone, including for file-backed IDs."""

    __tablename__ = "editor_publications"
    __table_args__ = (
        CheckConstraint("kind IN ('task', 'lesson', 'profile', 'template')", name="kind"),
        CheckConstraint("withdrawn OR revision_id IS NOT NULL", name="active_revision"),
    )

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("editor_revisions.id"), nullable=True
    )
    withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class EditorAudit(Base):
    __tablename__ = "editor_audit"
    __table_args__ = (Index("ix_editor_audit_revision", "revision_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("editor_revisions.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CorrectionExclusion(Base):
    __tablename__ = "editor_exclusions"
    __table_args__ = (
        UniqueConstraint("task_id", "task_revision", name="uq_editor_excluded_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class TemplateCheckRun(Base):
    __tablename__ = "editor_template_checks"
    __table_args__ = (
        CheckConstraint("seed_count BETWEEN 0 AND 1000", name="bounded_seeds"),
        Index("ix_editor_checks_revision", "revision_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("editor_revisions.id"), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    checked_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    seed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    output_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    checks: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class TemplateHumanReview(Base):
    __tablename__ = "editor_template_reviews"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "payload_hash",
            "profile_hash",
            "seed",
            "reviewer_id",
            name="uq_editor_reviewed_seed",
        ),
        CheckConstraint("seed >= 0 AND seed <= 4294967295", name="uint32_seed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("editor_revisions.id"), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
