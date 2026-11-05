"""Editorial revisions, active pointers, evidence and correction projections.

Revision ID: 0005_editor
Revises: 0004_learning
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_editor"
down_revision = "0004_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("base_snapshot", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("editor_revisions.id"), nullable=True),
        sa.Column("author_id", sa.String(128), nullable=False),
        sa.Column("reviewer_id", sa.String(128), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_formula", sa.Boolean(), nullable=False),
        sa.Column("reviewed_constraints", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("kind", "content_id", "version", name="uq_editor_content_version"),
        sa.CheckConstraint("kind IN ('task', 'lesson', 'profile', 'template')", name="kind"),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'ready', 'published', 'archived')", name="status"
        ),
        sa.CheckConstraint("version >= 1 AND revision >= 1", name="positive_revisions"),
        sa.CheckConstraint("reviewer_id IS NULL OR reviewer_id <> author_id", name="independent"),
        sa.CheckConstraint(
            "status NOT IN ('ready', 'published') OR "
            "(reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="review_gate",
        ),
    )
    op.create_index("ix_editor_revisions_kind_status", "editor_revisions", ["kind", "status"])
    op.create_table(
        "editor_catalog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "profile_revision_id",
            sa.String(36),
            sa.ForeignKey("editor_revisions.id"),
            nullable=True,
        ),
        sa.CheckConstraint("id = 1 AND revision >= 0", name="singleton"),
    )
    op.bulk_insert(
        sa.table(
            "editor_catalog",
            sa.column("id", sa.Integer()),
            sa.column("revision", sa.Integer()),
        ),
        [{"id": 1, "revision": 0}],
    )
    op.create_table(
        "editor_publications",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("content_id", sa.String(128), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("editor_revisions.id"), nullable=True
        ),
        sa.Column("withdrawn", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('task', 'lesson', 'profile', 'template')", name="kind"),
        sa.CheckConstraint("withdrawn OR revision_id IS NOT NULL", name="active_revision"),
    )
    op.create_table(
        "editor_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("editor_revisions.id"), nullable=True
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_editor_audit_revision", "editor_audit", ["revision_id", "created_at"])
    op.create_table(
        "editor_exclusions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("task_revision", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "task_revision", name="uq_editor_excluded_revision"),
    )
    op.create_table(
        "editor_template_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("editor_revisions.id"), nullable=False
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("generator_version", sa.String(128), nullable=False),
        sa.Column("checked_revision", sa.Integer(), nullable=False),
        sa.Column("seed_count", sa.Integer(), nullable=False),
        sa.Column("output_hashes", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("seed_count BETWEEN 0 AND 1000", name="bounded_seeds"),
    )
    op.create_index(
        "ix_editor_checks_revision", "editor_template_checks", ["revision_id", "created_at"]
    )
    op.create_table(
        "editor_template_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("editor_revisions.id"), nullable=False
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("reviewer_id", sa.String(128), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "revision_id",
            "payload_hash",
            "profile_hash",
            "seed",
            "reviewer_id",
            name="uq_editor_reviewed_seed",
        ),
        sa.CheckConstraint("seed >= 0 AND seed <= 4294967295", name="uint32_seed"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Editorial revisions, audit and correction history must not be deleted by downgrade. "
        "Use a separately approved recovery plan and a verified backup."
    )
