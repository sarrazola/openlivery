"""Template webhooks.

An address another system posts to so an approved WhatsApp template goes out
on one number, and the sends a caller named with an idempotency key."""
from alembic import op
import sqlalchemy as sa

revision = "0053_template_webhooks"
down_revision = "0052_follow_ups"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "template_webhooks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "whatsapp_cloud_channel_id",
            sa.Uuid(),
            sa.ForeignKey("whatsapp_cloud_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("secret_hint", sa.String(12), nullable=False),
        sa.Column("template_name", sa.String(512), nullable=False),
        sa.Column("template_language", sa.String(10), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_template_webhooks_client_id", "template_webhooks", ["client_id"])
    op.create_index("ix_template_webhooks_whatsapp_cloud_channel_id", "template_webhooks", ["whatsapp_cloud_channel_id"])
    op.create_table(
        "template_webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("webhook_id", sa.Uuid(), sa.ForeignKey("template_webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("webhook_id", "idempotency_key", name="uq_template_webhook_deliveries_key"),
    )
    op.create_index("ix_template_webhook_deliveries_webhook_id", "template_webhook_deliveries", ["webhook_id"])


def downgrade():
    op.drop_table("template_webhook_deliveries")
    op.drop_table("template_webhooks")
