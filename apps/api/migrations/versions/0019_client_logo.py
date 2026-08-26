"""Per-client logo (shown in the widget and portal, falls back to the agency).

Revision ID: 0019_client_logo
Revises: 0018_message_attachments
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_client_logo"
down_revision = "0018_message_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("logo_data", sa.LargeBinary(), nullable=True))
    op.add_column("clients", sa.Column("logo_mime", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "logo_mime")
    op.drop_column("clients", "logo_data")
