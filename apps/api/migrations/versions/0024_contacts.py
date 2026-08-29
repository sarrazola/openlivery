"""Contacts, and one conversation per case.

A contact used to be a name and a chat id stored on the conversation, and
a chat could only ever have one conversation per channel. Now the contact
is its own record per client, keyed by phone number, and a chat may hold
several conversations over time: one per case, the way a help desk counts
them. A message that arrives while a case is open joins it; after the case
is resolved the next message opens a new one.

Existing conversations are backfilled: one contact per (client, phone)
found in the WhatsApp chat ids, linked back to the conversations it came
from. Widget and playground conversations have no phone and stay without
a contact.

Revision ID: 0024_contacts
Revises: 0023_conversation_status
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_contacts"
down_revision = "0023_conversation_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_contacts_client_phone",
        "contacts",
        ["client_id", "phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )

    op.add_column("conversations", sa.Column("contact_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_contact_id", "conversations", "contacts", ["contact_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_conversations_contact_id", "conversations", ["contact_id"])
    op.add_column("conversations", sa.Column("taken_over_at", sa.DateTime(timezone=True), nullable=True))

    # A chat may now carry several conversations, one per case.
    op.drop_constraint("uq_conversations_whatsapp_chat", "conversations", type_="unique")
    op.drop_constraint("uq_conversations_whatsapp_cloud_chat", "conversations", type_="unique")
    op.create_index("ix_conversations_whatsapp_chat", "conversations", ["whatsapp_channel_id", "external_chat_id"])
    op.create_index(
        "ix_conversations_whatsapp_cloud_chat", "conversations", ["whatsapp_cloud_channel_id", "external_chat_id"]
    )

    # Backfill: the phone is the chat id up to any "@" (QR jids carry a
    # domain, Cloud API ids are bare digits). Keep the most recent name.
    op.execute(
        """
        INSERT INTO contacts (id, client_id, name, phone, notes, created_at, updated_at)
        SELECT gen_random_uuid(), ranked.client_id,
               COALESCE(NULLIF(ranked.contact_name, ''), ranked.phone), ranked.phone, '',
               ranked.first_seen, now()
        FROM (
            SELECT client_id,
                   regexp_replace(split_part(external_chat_id, '@', 1), '[^0-9]', '', 'g') AS phone,
                   contact_name,
                   MIN(created_at) OVER (PARTITION BY client_id, regexp_replace(split_part(external_chat_id, '@', 1), '[^0-9]', '', 'g')) AS first_seen,
                   ROW_NUMBER() OVER (
                       PARTITION BY client_id, regexp_replace(split_part(external_chat_id, '@', 1), '[^0-9]', '', 'g')
                       ORDER BY updated_at DESC
                   ) AS rn
            FROM conversations
            WHERE channel IN ('whatsapp', 'whatsapp_cloud') AND external_chat_id IS NOT NULL
        ) ranked
        WHERE ranked.rn = 1 AND ranked.phone <> ''
        """
    )
    op.execute(
        """
        UPDATE conversations c
        SET contact_id = k.id
        FROM contacts k
        WHERE c.channel IN ('whatsapp', 'whatsapp_cloud')
          AND c.external_chat_id IS NOT NULL
          AND k.client_id = c.client_id
          AND k.phone = regexp_replace(split_part(c.external_chat_id, '@', 1), '[^0-9]', '', 'g')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_whatsapp_cloud_chat", table_name="conversations")
    op.drop_index("ix_conversations_whatsapp_chat", table_name="conversations")
    # Several conversations per chat may exist by now; the unique constraints
    # cannot be restored safely, so downgrade leaves them off.
    op.drop_column("conversations", "taken_over_at")
    op.drop_index("ix_conversations_contact_id", table_name="conversations")
    op.drop_constraint("fk_conversations_contact_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "contact_id")
    op.drop_index("uq_contacts_client_phone", table_name="contacts")
    op.drop_table("contacts")
