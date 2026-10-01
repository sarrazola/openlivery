"""Inactivity follow-ups and agent-resolved conversations.

An agent can write to a contact who stopped answering, up to two times, and
close the case with a last message; it can also resolve a conversation itself
once the request is settled. The schedule lives on the agent, the clock on the
conversation."""
from alembic import op
import sqlalchemy as sa

revision = "0052_follow_ups"
down_revision = "0051_conversation_started_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("follow_up_anchor_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("follow_up_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("follow_up_step", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("follow_up_claimed_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("pending_resolution", sa.JSON(), nullable=True))
    op.create_index("ix_conversations_follow_up_due_at", "conversations", ["follow_up_due_at"])
    op.add_column("agents", sa.Column("resolve_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("follow_up_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("follow_up_first_minutes", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_second_minutes", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_close_minutes", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_first_text", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_second_text", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_close_text", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_channels", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("agents", "follow_up_channels")
    op.drop_column("agents", "follow_up_close_text")
    op.drop_column("agents", "follow_up_second_text")
    op.drop_column("agents", "follow_up_first_text")
    op.drop_column("agents", "follow_up_close_minutes")
    op.drop_column("agents", "follow_up_second_minutes")
    op.drop_column("agents", "follow_up_first_minutes")
    op.drop_column("agents", "follow_up_enabled")
    op.drop_column("agents", "resolve_enabled")
    op.drop_index("ix_conversations_follow_up_due_at", table_name="conversations")
    op.drop_column("conversations", "pending_resolution")
    op.drop_column("conversations", "follow_up_claimed_until")
    op.drop_column("conversations", "follow_up_step")
    op.drop_column("conversations", "follow_up_due_at")
    op.drop_column("conversations", "follow_up_anchor_at")
