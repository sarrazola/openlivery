"""Delivery state of outbound messages, as WhatsApp reports it.

Meta sends a receipt for every message a business sends: sent, then
delivered to the phone, then read (when the person allows read
receipts), or failed with a reason. Only failures were kept, on the
channel. Now each message carries its own state, so the portal can show
the ticks people know from WhatsApp.

Revision ID: 0026_message_delivery
Revises: 0025_assignment
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_message_delivery"
down_revision = "0025_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("delivery_status", sa.String(length=20), nullable=True))
    op.add_column("messages", sa.Column("delivery_error", sa.Text(), nullable=True))
    op.create_index("ix_messages_external_message_id", "messages", ["external_message_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_external_message_id", table_name="messages")
    op.drop_column("messages", "delivery_error")
    op.drop_column("messages", "delivery_status")
