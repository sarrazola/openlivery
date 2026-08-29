"""Conversation status, separate from who answers.

``mode`` says whether the AI or a person replies; it said nothing about
whether the case is still being worked. ``status`` adds that: open or
resolved, with the timestamps reports need (when it was resolved, when the
first reply went out, since when the contact has been waiting).

Messages gain a ``kind`` so the same thread can carry activity events
(resolved, reopened, taken over) next to the exchanged messages. Only
``message`` rows reach the model or the contact.

Revision ID: 0023_conversation_status
Revises: 0022_message_gestures
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_conversation_status"
down_revision = "0022_message_gestures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
    )
    op.add_column("conversations", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("first_reply_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_conversations_client_status", "conversations", ["client_id", "status"])

    op.add_column(
        "messages",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="message"),
    )
    op.add_column("messages", sa.Column("activity", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "activity")
    op.drop_column("messages", "kind")
    op.drop_index("ix_conversations_client_status", table_name="conversations")
    op.drop_column("conversations", "waiting_since")
    op.drop_column("conversations", "first_reply_at")
    op.drop_column("conversations", "resolved_at")
    op.drop_column("conversations", "status_changed_at")
    op.drop_column("conversations", "status")
