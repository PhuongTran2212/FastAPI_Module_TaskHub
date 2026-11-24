"""Add a transactional task-list cache generation per project."""

import sqlalchemy as sa
from alembic import op

revision = "6ca7e1018abc"
down_revision = "5e18a9c041ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "task_cache_version", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "task_cache_version")
