"""Message buttons.

The buttons a WhatsApp template carried stay on the message that sent it, so
the portal shows what the customer could tap."""
from alembic import op
import sqlalchemy as sa

revision = "0054_message_buttons"
down_revision = "0053_template_webhooks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("buttons", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("messages", "buttons")
