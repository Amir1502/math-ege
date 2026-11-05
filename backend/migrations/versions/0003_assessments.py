"""Add prepared assessments, writer leases, drafts and separately frozen results.

Revision ID: 0003_assessments
Revises: 0002_accounts
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_assessments"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("profile_revision", sa.String(128), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("tasks_snapshot", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("writer_device_id", sa.String(36), nullable=False),
        sa.Column("writer_generation", sa.Integer(), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("drafts", sa.JSON(), nullable=False),
        sa.Column("first_drafts", sa.JSON(), nullable=False),
        sa.Column("answer_context", sa.JSON(), nullable=False),
        sa.Column("server_result", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("local_result", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("finish_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], name="fk_assessments_guest_id_guests"),
        sa.CheckConstraint(
            "mode IN ('diagnostic', 'exam')", name=op.f("ck_assessments_assessment_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('prepared', 'active', 'awaiting_snapshot', 'completed')",
            name=op.f("ck_assessments_assessment_status"),
        ),
        sa.CheckConstraint(
            "duration_minutes BETWEEN 15 AND 180", name=op.f("ck_assessments_bounded_duration"),
        ),
        sa.CheckConstraint(
            "writer_generation >= 1", name=op.f("ck_assessments_positive_generation"),
        ),
        sa.CheckConstraint(
            "draft_revision >= 0", name=op.f("ck_assessments_nonnegative_revision"),
        ),
        sa.CheckConstraint(
            "current_index BETWEEN 0 AND 12", name=op.f("ck_assessments_bounded_index"),
        ),
        sa.CheckConstraint(
            "(mode = 'diagnostic' AND deadline_at IS NULL) OR "
            "(mode = 'exam' AND ((status = 'prepared' AND deadline_at IS NULL) OR "
            "(status <> 'prepared' AND deadline_at IS NOT NULL)))",
            name=op.f("ck_assessments_exam_deadline"),
        ),
        sa.CheckConstraint(
            "(status = 'prepared' AND started_at IS NULL AND server_result IS NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'active' AND started_at IS NOT NULL AND server_result IS NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'awaiting_snapshot' AND started_at IS NOT NULL AND "
            "deadline_at IS NOT NULL AND server_result IS NOT NULL AND "
            "released_at IS NULL AND finish_hash IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND server_result IS NOT NULL "
            "AND released_at IS NOT NULL AND finish_hash IS NOT NULL)",
            name=op.f("ck_assessments_release_gate"),
        ),
        sa.CheckConstraint(
            "local_result IS NULL OR status = 'completed'",
            name=op.f("ck_assessments_local_is_final"),
        ),
    )
    op.create_index("ix_assessments_guest_created", "assessments", ["guest_id", "created_at"])
    op.create_index("ix_assessments_status_deadline", "assessments", ["status", "deadline_at"])


def downgrade() -> None:
    raise RuntimeError(
        "Assessment history downgrade is intentionally disabled. "
        "Use a backed-up, explicitly approved recovery plan."
    )
