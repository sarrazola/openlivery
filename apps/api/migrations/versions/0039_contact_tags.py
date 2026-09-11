"""Contact tags: a per-client catalog and the links to contacts."""
from alembic import op
import sqlalchemy as sa

revision = "0039_contact_tags"
down_revision = "0038_whatsapp_coexistence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("contact_tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("color", sa.String(20), nullable=False, server_default="gray"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_contact_tags_client_id", "contact_tags", ["client_id"])
    # One name per client, whatever the casing: "VIP" and "vip" are the same tag.
    op.create_index("uq_contact_tags_client_name", "contact_tags", ["client_id", sa.text("lower(name)")], unique=True)
    op.create_table("contact_tag_links",
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Uuid(), sa.ForeignKey("contact_tags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_contact_tag_links_tag_id", "contact_tag_links", ["tag_id"])


def downgrade():
    op.drop_table("contact_tag_links")
    op.drop_index("uq_contact_tags_client_name", table_name="contact_tags")
    op.drop_table("contact_tags")
