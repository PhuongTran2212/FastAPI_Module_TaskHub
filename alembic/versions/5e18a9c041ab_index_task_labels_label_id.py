"""Index reverse lookups and cascade deletes by label_id."""

from alembic import op

revision = "5e18a9c041ab"
down_revision = "b1a8de19275e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_task_labels_label_id", "task_labels", ["label_id"])


def downgrade() -> None:
    op.drop_index("ix_task_labels_label_id", table_name="task_labels")
