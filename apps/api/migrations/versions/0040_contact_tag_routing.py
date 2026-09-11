"""A tag can route new conversations of its contacts straight to a team or a person."""
from alembic import op
import sqlalchemy as sa

revision = "0040_contact_tag_routing"
down_revision = "0039_contact_tags"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contact_tags", sa.Column("route_team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_contact_tags_route_team_id", "contact_tags", ["route_team_id"])
    op.add_column("contact_tags", sa.Column("route_assignee_id", sa.Uuid(), sa.ForeignKey("portal_users.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_contact_tags_route_assignee_id", "contact_tags", ["route_assignee_id"])


def downgrade():
    op.drop_index("ix_contact_tags_route_assignee_id", table_name="contact_tags")
    op.drop_column("contact_tags", "route_assignee_id")
    op.drop_index("ix_contact_tags_route_team_id", table_name="contact_tags")
    op.drop_column("contact_tags", "route_team_id")
