"""Additive learning state; source attempts, results and snapshots are never edited."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, UTCDateTime


class EvidenceRecord(Base):
    __tablename__ = "learning_evidence"
    __table_args__ = (Index("ix_learning_evidence_owner_at", "owner_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LearningState(Base):
    __tablename__ = "learning_policy_states"

    owner_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class TaskAnnotation(Base):
    __tablename__ = "learning_annotations"
    __table_args__ = (
        UniqueConstraint("session_id", "task_id", name="uq_learning_annotation_task"),
        CheckConstraint("source IN ('practice', 'assessment')", name="annotation_source"),
        CheckConstraint(
            "cause IS NULL OR cause IN ('theory', 'model', 'calculation', "
            "'restriction', 'graph', 'format')", name="annotation_cause",
        ),
        Index("ix_learning_annotations_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    favourite: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False)
    not_understood: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cause: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
