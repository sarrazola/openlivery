"""The web chat widget becomes a channel of the client.

One ``widget_channels`` row per client, answered by an assigned agent, in
place of the widget settings that lived on each agent. Existing widgets
move over: for every client with an enabled agent widget, the most recently
updated one becomes the client's channel and keeps its public id, so the
snippets already embedded on websites keep working. Widget conversations
are linked to the new channel.

Revision ID: 0032_widget_channels
Revises: 0030_escalation_builtin_toggle
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_widget_channels"
down_revision = "0030_escalation_builtin_toggle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "widget_channels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("greeting", sa.Text(), nullable=False, server_default=""),
        sa.Column("color", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("position", sa.String(length=10), nullable=False, server_default="right"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", name="uq_widget_channels_client_id"),
    )
    op.create_index("ix_widget_channels_agency_id", "widget_channels", ["agency_id"])
    op.create_index("ix_widget_channels_client_id", "widget_channels", ["client_id"])
    op.create_index("ix_widget_channels_agent_id", "widget_channels", ["agent_id"])
    op.create_index("ix_widget_channels_public_id", "widget_channels", ["public_id"], unique=True)
    op.add_column("conversations", sa.Column("widget_channel_id", sa.Uuid(), sa.ForeignKey("widget_channels.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_conversations_widget_channel_id", "conversations", ["widget_channel_id"])

    # Carry over the enabled widgets, one per client, keeping the public id.
    op.execute(
        """
        INSERT INTO widget_channels (id, agency_id, client_id, agent_id, public_id, is_enabled, greeting, color, position, created_at, updated_at)
        SELECT DISTINCT ON (client_id) gen_random_uuid(), agency_id, client_id, id, widget_public_id, true,
               widget_greeting, widget_color, widget_position, now(), now()
        FROM agents
        WHERE widget_enabled
        ORDER BY client_id, updated_at DESC
        """
    )
    op.execute(
        """
        UPDATE conversations c
        SET widget_channel_id = w.id
        FROM widget_channels w
        WHERE c.channel = 'widget' AND c.agent_id = w.agent_id
        """
    )
    for column in ("widget_enabled", "widget_public_id", "widget_greeting", "widget_color", "widget_position"):
        op.drop_column("agents", column)


def downgrade() -> None:
    op.add_column("agents", sa.Column("widget_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("widget_public_id", sa.String(length=64), nullable=True))
    op.add_column("agents", sa.Column("widget_greeting", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("widget_color", sa.String(length=20), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("widget_position", sa.String(length=10), nullable=False, server_default="right"))
    op.execute(
        """
        UPDATE agents a
        SET widget_enabled = w.is_enabled, widget_public_id = w.public_id, widget_greeting = w.greeting,
            widget_color = w.color, widget_position = w.position
        FROM widget_channels w WHERE w.agent_id = a.id
        """
    )
    op.execute("UPDATE agents SET widget_public_id = replace(gen_random_uuid()::text, '-', '') WHERE widget_public_id IS NULL")
    op.alter_column("agents", "widget_public_id", nullable=False)
    op.create_index("ix_agents_widget_public_id", "agents", ["widget_public_id"], unique=True)
    op.drop_index("ix_conversations_widget_channel_id", table_name="conversations")
    op.drop_column("conversations", "widget_channel_id")
    for name in ("ix_widget_channels_public_id", "ix_widget_channels_agent_id", "ix_widget_channels_client_id", "ix_widget_channels_agency_id"):
        op.drop_index(name, table_name="widget_channels")
    op.drop_table("widget_channels")
