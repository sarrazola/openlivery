"""Conversation summaries, and what each model call was for.

``conversations.summary``, ``summary_at``, ``summary_message_count`` and
``summary_by`` hold a summary a person asked for, and who asked. ``usage_records.purpose`` tells a reply from a
summary in the cost reports. Additive: existing usage rows read as replies."""
from alembic import op
import sqlalchemy as sa

revision = "0057_conversation_summary"
down_revision = "0056_key_pause_agent_schedule"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("summary_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("summary_message_count", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("summary_by", sa.String(160), nullable=True))
    op.add_column("usage_records", sa.Column("purpose", sa.String(20), nullable=False, server_default="reply"))


def downgrade():
    op.drop_column("usage_records", "purpose")
    op.drop_column("conversations", "summary_by")
    op.drop_column("conversations", "summary_message_count")
    op.drop_column("conversations", "summary_at")
    op.drop_column("conversations", "summary")
