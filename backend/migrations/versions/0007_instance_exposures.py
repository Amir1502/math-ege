"""Add condition identity without replacing original exposure IDs or snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0007_instance_exposures"
down_revision = "0006_practice_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("seen_tasks", sa.Column("instance_key", sa.String(64), nullable=True))
    op.create_index("ix_seen_tasks_guest_instance", "seen_tasks", ["guest_id", "instance_key"])


def downgrade() -> None:
    raise RuntimeError("Instance exposure history is preserved; destructive downgrade is disabled.")
