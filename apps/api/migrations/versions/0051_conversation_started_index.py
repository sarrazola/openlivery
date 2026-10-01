"""Index conversations by when they started: the reports list and the
operational report both read a date range of them."""
from alembic import op

revision = "0051_conversation_started_index"
down_revision = "0050_conversation_acquisition"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_conversations_created_at", "conversations", ["created_at"])


def downgrade():
    op.drop_index("ix_conversations_created_at", table_name="conversations")
