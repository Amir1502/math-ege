"""Add terminal cancellation, detached completion receipts and private audit disposition."""

import sqlalchemy as sa
from alembic import op

revision = "0008_account_deletion_completion"
down_revision = "0007_instance_exposures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_cancellations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_account_deletion_cancellations"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_account_deletion_cancellations_account_id_accounts",
        ),
        sa.CheckConstraint(
            "deadline_at > requested_at",
            name=op.f("ck_account_deletion_cancellations_future_deadline"),
        ),
        sa.CheckConstraint(
            "canceled_at >= requested_at",
            name=op.f("ck_account_deletion_cancellations_cancellation_time"),
        ),
    )
    op.create_index(
        "ix_account_deletion_cancellations_account_id", "account_deletion_cancellations",
        ["account_id"],
    )
    op.create_table(
        "account_deletion_receipts",
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("request_id", name="pk_account_deletion_receipts"),
        sa.CheckConstraint(
            "deadline_at > requested_at", name=op.f("ck_account_deletion_receipts_future_deadline"),
        ),
        sa.CheckConstraint(
            "completed_at >= requested_at",
            name=op.f("ck_account_deletion_receipts_completion_time"),
        ),
        sa.CheckConstraint(
            "scope = 'active_cloud_v1'", name=op.f("ck_account_deletion_receipts_known_scope"),
        ),
    )
    # Both tables have no inbound FKs. SQLite's batch copy preserves every legacy
    # row/column; PostgreSQL applies ordinary ALTERs. No account data is removed.
    with op.batch_alter_table("account_role_audit") as batch:
        batch.add_column(sa.Column("subject_id", sa.String(36), nullable=True))
        batch.alter_column("account_id", existing_type=sa.String(36), nullable=True)
        batch.create_check_constraint(
            op.f("ck_account_role_audit_audit_subject"),
            "(account_id IS NOT NULL AND subject_id IS NULL) OR "
            "(account_id IS NULL AND subject_id IS NOT NULL)",
        )
    with op.batch_alter_table("account_magic_links") as batch:
        batch.add_column(sa.Column("credential_account_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_account_magic_links_credential_account_id_accounts", "accounts",
            ["credential_account_id"], ["id"],
        )
        batch.create_index(
            "ix_account_magic_links_credential_account_id", ["credential_account_id"],
        )
    # Recover existing known associations without changing any original binding.
    links = sa.table(
        "account_magic_links", sa.column("credential_account_id", sa.String(36)),
        sa.column("browser_credential_digest", sa.String(64)), sa.column("guest_id", sa.String(36)),
    )
    access = sa.table(
        "access_sessions", sa.column("account_id", sa.String(36)),
        sa.column("token_digest", sa.String(64)),
    )
    claims = sa.table(
        "guest_claims", sa.column("account_id", sa.String(36)),
        sa.column("guest_id", sa.String(36)),
    )
    op.execute(links.update().where(links.c.credential_account_id.is_(None)).values(
        credential_account_id=sa.func.coalesce(
            sa.select(access.c.account_id).where(
                access.c.token_digest == links.c.browser_credential_digest,
            ).scalar_subquery(),
            sa.select(claims.c.account_id).where(
                claims.c.guest_id == links.c.guest_id,
            ).scalar_subquery(),
        ),
    ))


def downgrade() -> None:
    raise RuntimeError("Deletion receipts and audit history are preserved; downgrade is disabled.")
