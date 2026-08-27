"""Drop the legacy shared portal login.

0020 copied every configured portal login into portal_users and kept the old
columns as a bridge. The bridge leaked: the portal settings form kept writing
the old columns, so credentials saved after that upgrade never reached the new
model and the portal's user list looked empty while sign-in still worked. The
copy below runs once more to catch anything written since, then the columns go
away so a portal login can live in exactly one place.

Revision ID: 0021_drop_legacy_portal_login
Revises: 0020_portal_users_and_devices
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_drop_legacy_portal_login"
down_revision = "0020_portal_users_and_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO portal_users (id, client_id, name, email, password_hash, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, '', lower(c.portal_email), c.portal_password_hash, true, now(), now()
        FROM clients c
        WHERE c.portal_email IS NOT NULL
          AND c.portal_email <> ''
          AND c.portal_password_hash IS NOT NULL
          AND c.portal_password_hash <> ''
          AND NOT EXISTS (
            SELECT 1 FROM portal_users pu
            WHERE pu.client_id = c.id AND pu.email = lower(c.portal_email)
          )
        """
    )
    op.drop_column("clients", "portal_email")
    op.drop_column("clients", "portal_password_hash")


def downgrade() -> None:
    # The columns come back empty; the credentials themselves live on in
    # portal_users and are not copied back.
    op.add_column("clients", sa.Column("portal_email", sa.String(length=320), nullable=True))
    op.add_column("clients", sa.Column("portal_password_hash", sa.String(length=255), nullable=True))
