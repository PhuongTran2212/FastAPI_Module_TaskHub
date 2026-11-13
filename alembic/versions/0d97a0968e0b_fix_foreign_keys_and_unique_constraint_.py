"""fix foreign keys and unique constraint naming

Revision ID: 0d97a0968e0b
Revises: 5857005dfb78
Create Date: 2026-11-13 13:36:03.815007

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0d97a0968e0b'
down_revision: Union[str, Sequence[str], None] = '5857005dfb78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FOREIGN_KEYS = (
    ("workspaces", "owner_id", "RESTRICT"),
    ("tasks", "created_by", "RESTRICT"),
    ("tasks", "assignee_id", "SET NULL"),
    ("comments", "author_id", "RESTRICT"),
)


def _replace_foreign_key(table: str, column: str, ondelete: str | None) -> None:
    name = f"fk_{table}_{column}_users"
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        name, table, "users", [column], ["id"], ondelete=ondelete,
    )


def upgrade() -> None:
    for table, column, ondelete in _FOREIGN_KEYS:
        _replace_foreign_key(table, column, ondelete)
    # Preserve the existing unique index; only its constraint name changes.
    op.execute(
        "ALTER TABLE labels RENAME CONSTRAINT "
        "uq_labels_project_id TO uq_labels_project_id_name"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE labels RENAME CONSTRAINT "
        "uq_labels_project_id_name TO uq_labels_project_id"
    )
    for table, column, _ in reversed(_FOREIGN_KEYS):
        _replace_foreign_key(table, column, None)
