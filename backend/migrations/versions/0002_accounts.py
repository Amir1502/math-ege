"""Add accounts, owner claims, opaque sessions, consent and staff MFA.

Revision ID: 0002_accounts
Revises: 0001_learning_core
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_accounts"
down_revision = "0001_learning_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("root_guest_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("email", name="uq_accounts_email"),
        sa.UniqueConstraint("root_guest_id", name="uq_accounts_root_guest_id"),
        sa.ForeignKeyConstraint(
            ["root_guest_id"], ["guests.id"], name="fk_accounts_root_guest_id_guests",
        ),
        sa.CheckConstraint(
            "role IN ('student', 'methodist', 'admin')", name=op.f("ck_accounts_account_role"),
        ),
        sa.CheckConstraint("daily_minutes IN (10, 20, 30)", name=op.f("ck_accounts_daily_minutes")),
    )
    op.create_table(
        "guest_claims",
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("guest_id", name="pk_guest_claims"),
        sa.ForeignKeyConstraint(
            ["guest_id"], ["guests.id"], name="fk_guest_claims_guest_id_guests",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_guest_claims_account_id_accounts",
        ),
    )
    op.create_index("ix_guest_claims_account_id", "guest_claims", ["account_id"])
    op.create_table(
        "access_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_access_sessions"),
        sa.UniqueConstraint("token_digest", name="uq_access_sessions_token_digest"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_access_sessions_account_id_accounts",
        ),
    )
    op.create_index(
        "ix_access_sessions_account_created", "access_sessions", ["account_id", "created_at"],
    )
    op.create_table(
        "account_magic_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("browser_state_digest", sa.String(64), nullable=False),
        sa.Column("browser_credential_digest", sa.String(64), nullable=True),
        sa.Column("guest_id", sa.String(36), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_account_magic_links"),
        sa.UniqueConstraint("token_digest", name="uq_account_magic_links_token_digest"),
        sa.ForeignKeyConstraint(
            ["guest_id"], ["guests.id"], name="fk_account_magic_links_guest_id_guests",
        ),
    )
    op.create_index(
        "ix_account_magic_links_email_created", "account_magic_links", ["email", "created_at"],
    )
    op.create_table(
        "account_rate_limits",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_account_rate_limits"),
    )
    op.create_table(
        "account_consents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_account_consents"),
        sa.UniqueConstraint("account_id", "policy_version", name="uq_account_consents_version"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_account_consents_account_id_accounts",
        ),
    )
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_account_deletion_requests"),
        sa.UniqueConstraint("account_id", name="uq_account_deletion_requests_account_id"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_account_deletion_requests_account_id_accounts",
        ),
        sa.CheckConstraint(
            "status = 'requested'", name=op.f("ck_account_deletion_requests_request_only"),
        ),
        sa.CheckConstraint(
            "deadline_at > requested_at", name=op.f("ck_account_deletion_requests_future_deadline"),
        ),
    )
    op.create_table(
        "account_totp_credentials",
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("enrollment_session_id", sa.String(36), nullable=False),
        sa.Column("enrollment_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_timecode", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("account_id", name="pk_account_totp_credentials"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_account_totp_credentials_account_id_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_session_id"], ["access_sessions.id"],
            name="fk_account_totp_credentials_enrollment_session",
        ),
    )
    op.create_table(
        "account_role_audit",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("previous_role", sa.String(16), nullable=False),
        sa.Column("new_role", sa.String(16), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_account_role_audit"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_account_role_audit_account_id_accounts",
        ),
    )
    op.create_index("ix_account_role_audit_account_id", "account_role_audit", ["account_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Account history and consent downgrade is intentionally disabled. "
        "Use a backed-up, explicitly approved recovery plan."
    )
