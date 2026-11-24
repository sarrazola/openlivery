"""A task the agent runs with its tools when a conversation closes unanswered.

``agents.follow_up_close_task`` holds the instruction and
``follow_up_close_tools`` the ids of the agent tools it may use. Additive:
agents without a task close as before."""
from alembic import op
import sqlalchemy as sa

revision = "0061_follow_up_close_task"
down_revision = "0060_widget_appearance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("follow_up_close_task", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("follow_up_close_tools", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("agents", "follow_up_close_tools")
    op.drop_column("agents", "follow_up_close_task")
