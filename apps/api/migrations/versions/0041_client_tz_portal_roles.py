"""The timezone moves from the agent to the client, and portal users get a role.

``clients.timezone`` is filled from the client's agents: the timezone most of
its living agents already use, or UTC when none set one. ``agents.timezone``
stays in place, unmapped, so the release running during this migration keeps
working; a later migration drops it.

Every portal user that exists today becomes an ``admin``: nobody loses a button
they had. People added from now on start as ``agent``.
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_client_tz_portal_roles"
down_revision = "0040_contact_tag_routing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clients", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"))
    op.execute(
        """
        UPDATE clients SET timezone = picked.timezone
        FROM (
            SELECT DISTINCT ON (client_id) client_id, timezone
            FROM (
                SELECT client_id, timezone, COUNT(*) AS n
                FROM agents
                WHERE deleted_at IS NULL AND timezone IS NOT NULL AND timezone <> '' AND timezone <> 'UTC'
                GROUP BY client_id, timezone
            ) counted
            ORDER BY client_id, n DESC, timezone
        ) picked
        WHERE clients.id = picked.client_id
        """
    )
    op.add_column("portal_users", sa.Column("role", sa.String(length=20), nullable=False, server_default="agent"))
    op.execute("UPDATE portal_users SET role = 'admin'")


def downgrade():
    op.drop_column("portal_users", "role")
    op.drop_column("clients", "timezone")
