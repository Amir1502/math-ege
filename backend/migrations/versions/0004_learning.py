"""Add the learning evidence ledger, versioned policy state and task annotations.

Revision ID: 0004_learning
Revises: 0003_assessments
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_learning"
down_revision = "0003_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_evidence",
        sa.Column("event_id", sa.String(256), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name="pk_learning_evidence"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["guests.id"], name="fk_learning_evidence_owner_id_guests",
        ),
    )
    op.create_index(
        "ix_learning_evidence_owner_at", "learning_evidence", ["owner_id", "created_at"],
    )
    op.create_table(
        "learning_policy_states",
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("policy_config", sa.JSON(), nullable=False),
        sa.Column("notice", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("owner_id", name="pk_learning_policy_states"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["guests.id"], name="fk_learning_policy_states_owner_id_guests",
        ),
    )
    op.create_table(
        "learning_annotations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("favourite", sa.Boolean(), nullable=False),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.Column("not_understood", sa.Boolean(), nullable=False),
        sa.Column("cause", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_learning_annotations"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["guests.id"], name="fk_learning_annotations_owner_id_guests",
        ),
        sa.UniqueConstraint("session_id", "task_id", name="uq_learning_annotation_task"),
        sa.CheckConstraint(
            "source IN ('practice', 'assessment')",
            name=op.f("ck_learning_annotations_annotation_source"),
        ),
        sa.CheckConstraint(
            "cause IS NULL OR cause IN ('theory', 'model', 'calculation', "
            "'restriction', 'graph', 'format')",
            name=op.f("ck_learning_annotations_annotation_cause"),
        ),
    )
    op.create_index(
        "ix_learning_annotations_owner_updated", "learning_annotations", ["owner_id", "updated_at"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Learning evidence and annotations must not be deleted by downgrade. "
        "Use a backed-up, explicitly approved recovery plan."
    )
