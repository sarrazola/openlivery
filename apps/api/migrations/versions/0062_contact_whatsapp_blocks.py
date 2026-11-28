"""Where WhatsApp itself holds a block for a contact.

``contacts.whatsapp_blocks`` lists the WhatsApp API numbers on which the
person was blocked through Meta's block list, so the block can be lifted from
the same numbers later. Additive: null for every existing contact, whose block
stays the internal one."""
from alembic import op
import sqlalchemy as sa

revision = "0062_contact_whatsapp_blocks"
down_revision = "0061_follow_up_close_task"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contacts", sa.Column("whatsapp_blocks", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("contacts", "whatsapp_blocks")
