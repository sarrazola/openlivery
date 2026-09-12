"""Tell a pause the business set by answering apart from one it chose."""
from alembic import op
import sqlalchemy as sa

revision = "0042_conversation_auto_paused"
down_revision = "0041_client_tz_portal_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("auto_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("conversations", "auto_paused")
