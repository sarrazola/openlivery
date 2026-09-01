"""Canned responses: saved replies the portal composer inserts through a
/shortcut, with placeholders filled at insert time.

Revision ID: 0029_canned_responses
Revises: 0028_teams_and_routing
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_canned_responses"
down_revision = "0028_teams_and_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canned_responses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shortcut", sa.String(length=60), nullable=False),
        sa.Column("content", sa.String(length=4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "shortcut", name="uq_canned_responses_client_shortcut"),
    )
    op.create_index("ix_canned_responses_client_id", "canned_responses", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_canned_responses_client_id", table_name="canned_responses")
    op.drop_table("canned_responses")
