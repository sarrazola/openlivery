"""Who holds a conversation, and who wrote each message.

Taking a conversation over used to be anonymous: mode switched to human
and the person's name was stamped on each reply as text. Now the
conversation points at the portal user handling it, so it can be
transferred, released and listed as "mine", and each message points at
the portal user who wrote it, so reports can count per person.

Revision ID: 0025_assignment
Revises: 0024_contacts
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_assignment"
down_revision = "0024_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("assignee_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_assignee_id", "conversations", "portal_users", ["assignee_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_conversations_assignee_id", "conversations", ["assignee_id"])
    op.add_column("conversations", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("messages", sa.Column("portal_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_portal_user_id", "messages", "portal_users", ["portal_user_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_portal_user_id", "messages", type_="foreignkey")
    op.drop_column("messages", "portal_user_id")
    op.drop_column("conversations", "assigned_at")
    op.drop_index("ix_conversations_assignee_id", table_name="conversations")
    op.drop_constraint("fk_conversations_assignee_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "assignee_id")
