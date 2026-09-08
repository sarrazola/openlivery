"""A disconnected social channel no longer reserves its account.

The unique index on ``social_channels`` (provider, external_account_id) used
to cover every row with an account id, so an account that had been connected
once could never be connected under another client, even after it was
disconnected. Ownership now follows the credentials: only rows that still
hold an access token take part in the index. Disconnecting clears the token,
which releases the account while the row keeps its conversation history.

Revision ID: 0037_release_social_accounts
Revises: 0036_archive_and_agent_tombstone
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_release_social_accounts"
down_revision = "0036_archive_and_agent_tombstone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_social_channels_account", table_name="social_channels")
    op.create_index("uq_social_channels_account", "social_channels", ["provider", "external_account_id"], unique=True,
                    postgresql_where=sa.text("external_account_id <> '' AND encrypted_access_token IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_social_channels_account", table_name="social_channels")
    op.create_index("uq_social_channels_account", "social_channels", ["provider", "external_account_id"], unique=True,
                    postgresql_where=sa.text("external_account_id <> ''"))
