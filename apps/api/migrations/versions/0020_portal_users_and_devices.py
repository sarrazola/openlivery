"""Portal users and push devices.

A portal used to have one shared e-mail and password. This adds real users so a
business can have several people answering, and a table of devices to notify.

The upgrade copies every existing portal login into a user of its client, so an
install that upgrades keeps signing in with exactly the credentials it had. The
old columns stay and still authenticate, which is what lets the browser portal
and any older client carry on untouched.

Revision ID: 0020_portal_users_and_devices
Revises: 0019_client_logo
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_portal_users_and_devices"
down_revision = "0019_client_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "email", name="uq_portal_users_client_email"),
    )
    op.create_index("ix_portal_users_client_id", "portal_users", ["client_id"])
    op.create_index("ix_portal_users_email", "portal_users", ["email"])

    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("portal_user_id", sa.Uuid(), nullable=True),
        sa.Column("token", sa.String(length=400), nullable=False),
        sa.Column("provider", sa.String(length=40), server_default="", nullable=False),
        sa.Column("platform", sa.String(length=20), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portal_user_id"], ["portal_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_push_devices_token"),
    )
    op.create_index("ix_push_devices_client_id", "push_devices", ["client_id"])
    op.create_index("ix_push_devices_portal_user_id", "push_devices", ["portal_user_id"])

    # Carry every configured portal login over as a user of its client, so
    # nobody has to be told their password stopped working. gen_random_uuid()
    # ships with Postgres 13+, which the stack already requires.
    op.execute(
        """
        INSERT INTO portal_users (id, client_id, name, email, password_hash, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), id, '', lower(portal_email), portal_password_hash, true, now(), now()
        FROM clients
        WHERE portal_email IS NOT NULL
          AND portal_email <> ''
          AND portal_password_hash IS NOT NULL
          AND portal_password_hash <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_push_devices_portal_user_id", table_name="push_devices")
    op.drop_index("ix_push_devices_client_id", table_name="push_devices")
    op.drop_table("push_devices")
    op.drop_index("ix_portal_users_email", table_name="portal_users")
    op.drop_index("ix_portal_users_client_id", table_name="portal_users")
    op.drop_table("portal_users")
