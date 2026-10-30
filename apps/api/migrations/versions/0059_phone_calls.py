"""Phone calls.

``call_accounts`` holds an agency's ElevenLabs key and its phone carrier
accounts, ``phone_channels`` the numbers voice agents answer and
``phone_calls`` one row per call. Conversations gain the line they came in on;
agents gain their kind (chat or voice), voice and greeting. Additive: new
tables and columns with defaults, nothing else moves."""
from alembic import op
import sqlalchemy as sa

revision = "0059_phone_calls"
down_revision = "0058_agent_media_assets"
branch_labels = None
depends_on = None


def upgrade():
    # conversations first: a reply locks it before the channel tables.
    op.add_column("conversations", sa.Column("phone_channel_id", sa.Uuid(), nullable=True))
    op.create_index("ix_conversations_phone_channel_id", "conversations", ["phone_channel_id"])

    op.add_column("agents", sa.Column("kind", sa.String(20), nullable=False, server_default="chat"))
    op.add_column("agents", sa.Column("voice_id", sa.String(80), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("voice_name", sa.String(180), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("greeting", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("transfer_number", sa.String(32), nullable=True))
    op.add_column("agents", sa.Column("transfer_when", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "call_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(40), nullable=False, server_default=""),
        sa.Column("webhook_id", sa.String(80), nullable=True),
        sa.Column("encrypted_webhook_secret", sa.Text(), nullable=True),
        sa.Column("tool_secret_id", sa.String(80), nullable=True),
        sa.Column("tool_token_hash", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agency_id", "provider", name="uq_call_accounts_agency_provider"),
        sa.UniqueConstraint("public_id", name="uq_call_accounts_public_id"),
    )
    op.create_index("ix_call_accounts_agency_id", "call_accounts", ["agency_id"])

    op.create_table(
        "phone_channels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_number_id", sa.String(80), nullable=True),
        sa.Column("elevenlabs_agent_id", sa.String(80), nullable=True),
        sa.Column("elevenlabs_phone_number_id", sa.String(80), nullable=True),
        sa.Column("elevenlabs_tools", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(30), nullable=False, server_default="disconnected"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_phone_channels_public_id"),
    )
    for column in ("agency_id", "client_id", "agent_id"):
        op.create_index(f"ix_phone_channels_{column}", "phone_channels", [column])

    op.create_table(
        "phone_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone_channel_id", sa.Uuid(), sa.ForeignKey("phone_channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_call_id", sa.String(80), nullable=False),
        sa.Column("caller", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("end_reason", sa.String(180), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.UniqueConstraint("conversation_id", name="uq_phone_calls_conversation_id"),
        sa.UniqueConstraint("external_call_id", name="uq_phone_calls_external_call_id"),
    )
    op.create_index("ix_phone_calls_phone_channel_id", "phone_calls", ["phone_channel_id"])

    op.create_foreign_key(
        "fk_conversations_phone_channel", "conversations", "phone_channels", ["phone_channel_id"], ["id"], ondelete="SET NULL"
    )


def downgrade():
    op.drop_constraint("fk_conversations_phone_channel", "conversations", type_="foreignkey")
    op.drop_index("ix_conversations_phone_channel_id", table_name="conversations")
    op.drop_column("conversations", "phone_channel_id")
    for column in ("transfer_when", "transfer_number", "greeting", "voice_name", "voice_id", "kind"):
        op.drop_column("agents", column)
    op.drop_index("ix_phone_calls_phone_channel_id", table_name="phone_calls")
    op.drop_table("phone_calls")
    for column in ("agency_id", "client_id", "agent_id"):
        op.drop_index(f"ix_phone_channels_{column}", table_name="phone_channels")
    op.drop_table("phone_channels")
    op.drop_index("ix_call_accounts_agency_id", table_name="call_accounts")
    op.drop_table("call_accounts")
