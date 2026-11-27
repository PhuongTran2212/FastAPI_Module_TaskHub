"""Index refresh-token expiry for bounded background cleanup."""

from alembic import op

revision = "7b019dca0001"
down_revision = "6ca7e1018abc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
