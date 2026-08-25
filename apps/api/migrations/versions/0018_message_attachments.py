"""Chat message attachments: persist original media files and split the LLM
text (description/transcript) from the displayed content.

Revision ID: 0018_message_attachments
Revises: 0017_whatsapp_cloud_channel
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_message_attachments"
down_revision = "0017_whatsapp_cloud_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("llm_content", sa.Text(), nullable=True))
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_table("message_attachments")
    op.drop_column("messages", "llm_content")
