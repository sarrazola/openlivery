"""How a web chat presents itself.

``widget_channels.appearance`` holds what the channel shows before the visitor
writes and how it looks, as one JSON object: a new option is a new key, not a
new column. Additive: one column with an empty default, nothing else moves."""
from alembic import op
import sqlalchemy as sa

revision = "0060_widget_appearance"
down_revision = "0059_phone_calls"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("widget_channels", sa.Column("appearance", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("widget_channels", "appearance")
