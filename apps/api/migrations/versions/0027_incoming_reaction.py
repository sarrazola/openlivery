"""The customer's emoji reaction to a message, so the portal can mirror the
gesture WhatsApp shows under the business's bubble.

Revision ID: 0027_incoming_reaction
Revises: 0026_message_delivery
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_incoming_reaction"
down_revision = "0026_message_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("incoming_reaction", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "incoming_reaction")
