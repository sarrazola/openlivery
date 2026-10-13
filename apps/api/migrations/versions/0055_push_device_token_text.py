"""Push device tokens become text.

A browser's web push subscription (its endpoint plus two keys) is longer than
the 400 characters a native device token needed, so the column loses its
bound. Nothing is rewritten; the index and the unique constraint stay."""
from alembic import op
import sqlalchemy as sa

revision = "0055_push_device_token_text"
down_revision = "0054_message_buttons"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("push_devices", "token", type_=sa.Text(), existing_type=sa.String(400), existing_nullable=False)


def downgrade():
    op.alter_column("push_devices", "token", type_=sa.String(400), existing_type=sa.Text(), existing_nullable=False)
