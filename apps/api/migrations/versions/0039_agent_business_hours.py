"""Opening hours per agent, so the prompt can say whether the business is open."""
from alembic import op
import sqlalchemy as sa

revision = "0039_agent_business_hours"
down_revision = "0038_whatsapp_coexistence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("business_hours", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("agents", "business_hours")
