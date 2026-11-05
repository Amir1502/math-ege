"""Guest practice, frozen content, attempt history and idempotent responses.

Revision ID: 0001_learning_core
Revises:
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_learning_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_guests"),
        sa.UniqueConstraint("token_digest", name="uq_guests_token_digest"),
    )
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("profile_revision", sa.String(128), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("requested_length", sa.Integer(), nullable=False),
        sa.Column("notice", sa.Text(), nullable=True),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("tasks_snapshot", sa.JSON(), nullable=False),
        sa.Column("drafts", sa.JSON(), nullable=False),
        sa.Column("help_state", sa.JSON(), nullable=False),
        sa.Column("active_seconds", sa.JSON(), nullable=False),
        sa.Column("summary_snapshot", sa.JSON(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_learning_sessions"),
        sa.ForeignKeyConstraint(
            ["guest_id"], ["guests.id"], name="fk_learning_sessions_guest_id_guests"
        ),
        sa.CheckConstraint("mode = 'practice'", name=op.f("ck_learning_sessions_practice_mode")),
        sa.CheckConstraint(
            "status IN ('active', 'completed')", name=op.f("ck_learning_sessions_session_status")
        ),
        sa.CheckConstraint(
            "requested_length IN (5, 10, 20)", name=op.f("ck_learning_sessions_session_length")
        ),
        sa.CheckConstraint(
            "current_index >= 0", name=op.f("ck_learning_sessions_nonnegative_index")
        ),
        sa.CheckConstraint(
            "draft_revision >= 0", name=op.f("ck_learning_sessions_nonnegative_revision")
        ),
        sa.CheckConstraint(
            "(status = 'active' AND completed_at IS NULL AND summary_snapshot IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL AND summary_snapshot IS NOT NULL)",
            name=op.f("ck_learning_sessions_completion_snapshot"),
        ),
    )
    op.create_index(
        "ix_learning_sessions_guest_created", "learning_sessions", ["guest_id", "created_at"]
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("task_revision", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("raw_answer", sa.String(64), nullable=False),
        sa.Column("normalized_answer", sa.Text(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("assisted", sa.Boolean(), nullable=False),
        sa.Column("first_attempt", sa.Boolean(), nullable=False),
        sa.Column("independent", sa.Boolean(), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checker_revision", sa.String(32), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("solution", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attempts"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], name="fk_attempts_guest_id_guests"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_attempts_session_id_learning_sessions"
        ),
        sa.UniqueConstraint("session_id", "sequence", name="uq_attempts_session_sequence"),
        sa.CheckConstraint(
            "active_seconds >= 0 AND active_seconds <= 86400", name=op.f("ck_attempts_bounded_time")
        ),
        sa.CheckConstraint(
            "NOT skipped OR NOT independent", name=op.f("ck_attempts_skip_is_not_independent")
        ),
        sa.CheckConstraint(
            "NOT independent OR first_attempt", name=op.f("ck_attempts_independent_is_first")
        ),
    )
    op.create_index("ix_attempts_guest_task", "attempts", ["guest_id", "task_id"])
    op.create_index("ix_attempts_session_sequence", "attempts", ["session_id", "sequence"])
    op.create_table(
        "seen_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assistance_seen", sa.Boolean(), nullable=False),
        sa.Column("reference_seen", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_seen_tasks"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], name="fk_seen_tasks_guest_id_guests"),
        sa.UniqueConstraint("guest_id", "task_id", name="uq_seen_tasks_guest_task"),
    )
    op.create_index("ix_seen_tasks_guest_seen", "seen_tasks", ["guest_id", "last_seen_at"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(256), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.ForeignKeyConstraint(
            ["guest_id"], ["guests.id"], name="fk_idempotency_records_guest_id_guests"
        ),
        sa.UniqueConstraint("guest_id", "request_key", name="uq_idempotency_guest_key"),
        sa.CheckConstraint(
            "status_code >= 200 AND status_code <= 599",
            name=op.f("ck_idempotency_records_response_status"),
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "This migration stores guest history. Downgrade would permanently delete it and is "
        "intentionally disabled. Back up the database and use an explicitly approved recovery plan."
    )
