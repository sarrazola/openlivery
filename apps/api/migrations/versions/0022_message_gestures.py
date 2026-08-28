"""Message gestures: the business's emoji reaction to a visitor message and
the quoted-reply reference (swipe-to-reply), so the portal can mirror what the
customer sees on WhatsApp.

Revision ID: 0022_message_gestures
Revises: 0021_drop_legacy_portal_login
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_message_gestures"
down_revision = "0021_drop_legacy_portal_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("reaction", sa.String(length=16), nullable=True))
    op.add_column("messages", sa.Column("quoted_message_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_quoted_message_id",
        "messages",
        "messages",
        ["quoted_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_quoted_message_id", "messages", type_="foreignkey")
    op.drop_column("messages", "quoted_message_id")
    op.drop_column("messages", "reaction")
