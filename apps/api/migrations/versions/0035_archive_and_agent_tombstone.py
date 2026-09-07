"""Conversations can be archived; deleted agents leave a tombstone; contacts can be blocked.

``conversations.archived_at`` takes a conversation out of the inboxes while
keeping its messages and its place in reports. Deleting is only allowed
from the archive, so history never goes in one step.

``agents.deleted_at`` marks an agent as deleted. The row stays so the
conversations it handled keep its name; its knowledge, tools and rules are
purged when it is deleted and it is hidden from every list.

``contacts.blocked_at`` mutes a contact: their messages are kept but never
reach the agent or a person's phone, and their conversations leave the
inboxes until they are unblocked.

Revision ID: 0035_archive_and_agent_tombstone
Revises: 0034_agent_reply_delay
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_archive_and_agent_tombstone"
down_revision = "0034_agent_reply_delay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_conversations_archived_at", "conversations", ["archived_at"])
    op.add_column("agents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "blocked_at")
    op.drop_column("agents", "deleted_at")
    op.drop_index("ix_conversations_archived_at", table_name="conversations")
    op.drop_column("conversations", "archived_at")
