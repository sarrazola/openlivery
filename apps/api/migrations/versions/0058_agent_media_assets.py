"""Files the agent can send.

``agent_media_assets`` holds, per agent, the images and documents the model
may attach to a reply, each with a name and a description of when to send it.
Additive: a new table, nothing else moves."""
from alembic import op
import sqlalchemy as sa

revision = "0058_agent_media_assets"
down_revision = "0057_conversation_summary"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_media_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_media_assets_agent_id", "agent_media_assets", ["agent_id"])


def downgrade():
    op.drop_index("ix_agent_media_assets_agent_id", table_name="agent_media_assets")
    op.drop_table("agent_media_assets")
