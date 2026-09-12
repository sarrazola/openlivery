"""The timezone moves from the agent to the client, and portal users get a role.

``clients.timezone`` is filled from the client's agents: the timezone most of
its living agents already use, or UTC when none set one. ``agents.timezone``
stays in place, unmapped, so the release running during this migration keeps
working; a later migration drops it.

Every portal user that exists today becomes an ``admin``: nobody loses a button
they had. People added from now on start as ``agent``.

Tag colors stop being palette names and become ``#rrggbb``; the eight names
map to the hex the interface used to paint them with.
"""

LEGACY_TAG_COLORS = {
    "gray": "#6b7280", "blue": "#3b82f6", "green": "#22c55e", "amber": "#f59e0b",
    "red": "#ef4444", "violet": "#8b5cf6", "pink": "#ec4899", "teal": "#14b8a6",
}
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
    for name, hex_value in LEGACY_TAG_COLORS.items():
        op.execute(f"UPDATE contact_tags SET color = '{hex_value}' WHERE color = '{name}'")
    op.execute("UPDATE contact_tags SET color = '#6b7280' WHERE color NOT LIKE '#%'")
    op.alter_column("contact_tags", "color", server_default="#6b7280")


def downgrade():
    for name, hex_value in LEGACY_TAG_COLORS.items():
        op.execute(f"UPDATE contact_tags SET color = '{name}' WHERE color = '{hex_value}'")
    op.execute("UPDATE contact_tags SET color = 'gray' WHERE color LIKE '#%'")
    op.alter_column("contact_tags", "color", server_default="gray")
    op.drop_column("portal_users", "role")
    op.drop_column("clients", "timezone")
