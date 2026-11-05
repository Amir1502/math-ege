"""Assessment storage is deliberately independent of practice sessions/attempts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, UTCDateTime


class AssessmentRecord(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("mode IN ('diagnostic', 'exam')", name="assessment_mode"),
        CheckConstraint(
            "status IN ('prepared', 'active', 'awaiting_snapshot', 'completed')",
            name="assessment_status",
        ),
        CheckConstraint("duration_minutes BETWEEN 15 AND 180", name="bounded_duration"),
        CheckConstraint("writer_generation >= 1", name="positive_generation"),
        CheckConstraint("draft_revision >= 0", name="nonnegative_revision"),
        CheckConstraint("current_index BETWEEN 0 AND 12", name="bounded_index"),
        CheckConstraint(
            "(mode = 'diagnostic' AND deadline_at IS NULL) OR "
            "(mode = 'exam' AND ((status = 'prepared' AND deadline_at IS NULL) OR "
            "(status <> 'prepared' AND deadline_at IS NOT NULL)))",
            name="exam_deadline",
        ),
        CheckConstraint(
            "(status = 'prepared' AND started_at IS NULL AND server_result IS NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'active' AND started_at IS NOT NULL AND server_result IS NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'awaiting_snapshot' AND started_at IS NOT NULL AND "
            "deadline_at IS NOT NULL AND server_result IS NOT NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND server_result IS NOT NULL "
            "AND released_at IS NOT NULL AND finish_hash IS NOT NULL)",
            name="release_gate",
        ),
        CheckConstraint("local_result IS NULL OR status = 'completed'", name="local_is_final"),
        Index("ix_assessments_guest_created", "guest_id", "created_at"),
        Index("ix_assessments_status_deadline", "status", "deadline_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    tasks_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    writer_device_id: Mapped[str] = mapped_column(String(36), nullable=False)
    writer_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False)
    drafts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    first_drafts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    answer_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    server_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    local_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    finish_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
