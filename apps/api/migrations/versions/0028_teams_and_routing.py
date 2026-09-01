"""Teams and routing: named trays of portal users a conversation can be
escalated to, with the assignment strategy per team, the round-robin state per
member, the operator's availability, and the agent's escalation rules.

Revision ID: 0028_teams_and_routing
Revises: 0027_incoming_reaction
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_teams_and_routing"
down_revision = "0027_incoming_reaction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("strategy", sa.String(length=20), nullable=False, server_default="round_robin"),
        sa.Column("channels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "name", name="uq_teams_client_name"),
    )
    op.create_index("ix_teams_client_id", "teams", ["client_id"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portal_user_id", sa.Uuid(), sa.ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "portal_user_id", name="uq_team_members_team_user"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_portal_user_id", "team_members", ["portal_user_id"])

    op.add_column(
        "conversations",
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_conversations_team_id", "conversations", ["team_id"])

    op.add_column(
        "portal_users", sa.Column("availability", sa.String(length=10), nullable=False, server_default="online")
    )
    op.add_column("portal_users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "escalation_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("portal_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_escalation_rules_agent_id", "escalation_rules", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_escalation_rules_agent_id", table_name="escalation_rules")
    op.drop_table("escalation_rules")
    op.drop_column("portal_users", "last_seen_at")
    op.drop_column("portal_users", "availability")
    op.drop_index("ix_conversations_team_id", table_name="conversations")
    op.drop_column("conversations", "team_id")
    op.drop_index("ix_team_members_portal_user_id", table_name="team_members")
    op.drop_index("ix_team_members_team_id", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_client_id", table_name="teams")
    op.drop_table("teams")
