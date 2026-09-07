"""Agents carry their own reply delay, a random quiet window between two bounds.

The quiet window before the AI answers a WhatsApp burst used to be one
process-wide setting (``REPLY_DEBOUNCE_SECONDS``, 8 seconds). Each agent now
owns two bounds, ``reply_delay_min_seconds`` and ``reply_delay_max_seconds``,
and every inbound message draws a wait between them, so the pace varies like
a person's and each agent can be tuned on its own. Every agent, new or
existing, starts at 6 to 9 seconds.

Revision ID: 0034_agent_reply_delay
Revises: 0033_client_identity
"""

from alembic import op
import sqlalchemy as sa


revision = "0034_agent_reply_delay"
down_revision = "0033_client_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("reply_delay_min_seconds", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("agents", sa.Column("reply_delay_max_seconds", sa.Integer(), nullable=False, server_default="9"))


def downgrade() -> None:
    op.drop_column("agents", "reply_delay_max_seconds")
    op.drop_column("agents", "reply_delay_min_seconds")
