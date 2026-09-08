"""Persist WhatsApp Business app coexistence and resumable imports."""
from alembic import op
import sqlalchemy as sa

revision = "0038_whatsapp_coexistence"
down_revision = "0037_release_social_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contacts", sa.Column("whatsapp_contact_name", sa.String(180), nullable=True))
    op.add_column("contacts", sa.Column("whatsapp_contact_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("whatsapp_cloud_channels", sa.Column("coexistence", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("whatsapp_cloud_channels", sa.Column("coexistence_sync", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("whatsapp_coexistence_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("channel_id", sa.Uuid(), sa.ForeignKey("whatsapp_cloud_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("field", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("channel_id", "event_key", name="uq_whatsapp_coexistence_event"))
    for column in ("channel_id", "available_at", "processed_at"):
        op.create_index(f"ix_whatsapp_coexistence_events_{column}", "whatsapp_coexistence_events", [column])


def downgrade():
    op.drop_column("contacts", "whatsapp_contact_updated_at")
    op.drop_column("contacts", "whatsapp_contact_name")
    op.drop_table("whatsapp_coexistence_events")
    op.drop_column("whatsapp_cloud_channels", "coexistence_sync")
    op.drop_column("whatsapp_cloud_channels", "coexistence")
