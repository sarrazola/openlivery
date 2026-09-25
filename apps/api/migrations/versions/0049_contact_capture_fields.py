"""Contact fields a client defines, the values on each contact, and which of them an agent asks for."""
from alembic import op
import sqlalchemy as sa

revision = "0049_contact_capture_fields"
down_revision = "0048_number_quality"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_fields",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="text"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "key", name="uq_contact_fields_key"),
    )
    op.create_index("ix_contact_fields_client_id", "contact_fields", ["client_id"])
    op.create_table(
        "agent_capture_fields",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(60), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("channels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "field_key", name="uq_agent_capture_fields_key"),
    )
    op.create_index("ix_agent_capture_fields_agent_id", "agent_capture_fields", ["agent_id"])
    op.add_column("contacts", sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agents", sa.Column("capture_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("agents", "capture_enabled")
    op.drop_column("contacts", "attributes")
    op.drop_index("ix_agent_capture_fields_agent_id", table_name="agent_capture_fields")
    op.drop_table("agent_capture_fields")
    op.drop_index("ix_contact_fields_client_id", table_name="contact_fields")
    op.drop_table("contact_fields")
