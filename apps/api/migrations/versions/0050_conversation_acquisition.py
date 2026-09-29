"""Where a conversation came from: the ad referral WhatsApp attaches to a click-to-chat message."""
from alembic import op
import sqlalchemy as sa

revision = "0050_conversation_acquisition"
down_revision = "0049_contact_capture_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("acquisition", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("conversations", "acquisition")
