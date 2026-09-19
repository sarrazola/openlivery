"""Quality rating and messaging limit of a WhatsApp Cloud number, as Meta reports them."""
from alembic import op
import sqlalchemy as sa

revision = "0048_number_quality"
down_revision = "0047_multi_account_channels"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("whatsapp_cloud_channels", sa.Column("quality_rating", sa.String(20), nullable=True))
    op.add_column("whatsapp_cloud_channels", sa.Column("messaging_limit", sa.String(30), nullable=True))


def downgrade():
    op.drop_column("whatsapp_cloud_channels", "messaging_limit")
    op.drop_column("whatsapp_cloud_channels", "quality_rating")
