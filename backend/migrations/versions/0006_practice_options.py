import sqlalchemy as sa
from alembic import op

revision = "0006_practice_options"
down_revision = "0005_editor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_sessions",
        sa.Column("options_snapshot", sa.JSON(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Practice options are historical evidence; destructive downgrade is disabled."
    )
