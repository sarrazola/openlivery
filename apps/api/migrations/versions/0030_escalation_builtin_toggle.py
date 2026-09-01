"""A switch for the built-in escalation triggers (frustration, explicit
request for a human, unsolvable), on by default. Business rules keep
escalating when it is off.

Revision ID: 0030_escalation_builtin_toggle
Revises: 0029_canned_responses
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_escalation_builtin_toggle"
down_revision = "0029_canned_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("escalation_builtin_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("agents", "escalation_builtin_enabled")
