"""A provider key can be paused, and an agent can keep a schedule.

``provider_credentials.enabled`` keeps a stored key out of use without
deleting it. ``agents.schedule_enabled`` and ``agents.schedule_slots`` say
when the agent is on duty. Both are additive: every existing row keeps
answering as before (key in use, agent always on duty)."""
from alembic import op
import sqlalchemy as sa

revision = "0056_key_pause_agent_schedule"
down_revision = "0055_push_device_token_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_credentials", sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("agents", sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("schedule_slots", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("agents", "schedule_slots")
    op.drop_column("agents", "schedule_enabled")
    op.drop_column("provider_credentials", "enabled")
