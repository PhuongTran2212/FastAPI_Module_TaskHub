"""add users.password_changed_at

Revision ID: b1a8de19275e
Revises: d3c0a1800d97
Create Date: 2026-11-14 11:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a8de19275e"
down_revision: Union[str, Sequence[str], None] = "d3c0a1800d97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "password_changed_at")
