"""Several WhatsApp lines and social accounts per client, each with a label."""
from alembic import op
import sqlalchemy as sa

revision = "0047_multi_account_channels"
down_revision = "0046_embedding_model"
branch_labels = None
depends_on = None


def upgrade():
    # conversations first. Live requests lock conversations and then the
    # channel tables (loading the line a reply goes out on); locking the
    # channel tables first and then waiting on conversations deadlocked
    # against that traffic, with the migration as the victim every time.
    # Taking conversations first turns those requests into plain waiters.
    # Removing a line keeps its conversations as history instead of deleting them.
    op.drop_constraint("fk_conversations_whatsapp_channel_id", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "fk_conversations_whatsapp_channel_id", "conversations", "whatsapp_channels",
        ["whatsapp_channel_id"], ["id"], ondelete="SET NULL",
    )
    op.drop_constraint("fk_conversations_whatsapp_cloud_channel_id", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "fk_conversations_whatsapp_cloud_channel_id", "conversations", "whatsapp_cloud_channels",
        ["whatsapp_cloud_channel_id"], ["id"], ondelete="SET NULL",
    )
    op.drop_constraint("uq_whatsapp_channels_client_id", "whatsapp_channels", type_="unique")
    op.drop_constraint("uq_whatsapp_cloud_channels_client_id", "whatsapp_cloud_channels", type_="unique")
    op.drop_constraint("uq_social_channels_client_provider", "social_channels", type_="unique")
    for table in ("whatsapp_channels", "whatsapp_cloud_channels", "social_channels"):
        op.add_column(table, sa.Column("label", sa.String(80), nullable=True))


def downgrade():
    op.drop_constraint("fk_conversations_whatsapp_cloud_channel_id", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "fk_conversations_whatsapp_cloud_channel_id", "conversations", "whatsapp_cloud_channels",
        ["whatsapp_cloud_channel_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_conversations_whatsapp_channel_id", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "fk_conversations_whatsapp_channel_id", "conversations", "whatsapp_channels",
        ["whatsapp_channel_id"], ["id"], ondelete="CASCADE",
    )
    for table in ("whatsapp_channels", "whatsapp_cloud_channels", "social_channels"):
        op.drop_column(table, "label")
    # Only possible while every client still has at most one account per channel.
    op.create_unique_constraint("uq_social_channels_client_provider", "social_channels", ["client_id", "provider"])
    op.create_unique_constraint("uq_whatsapp_cloud_channels_client_id", "whatsapp_cloud_channels", ["client_id"])
    op.create_unique_constraint("uq_whatsapp_channels_client_id", "whatsapp_channels", ["client_id"])
