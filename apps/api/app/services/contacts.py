"""Contacts: the people behind the chats, one record per client and phone.

WhatsApp identifies a person by number, so that is the key. Widget and
playground conversations carry no number and therefore no contact.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Contact, Conversation, Message, now_utc


_NON_DIGITS = re.compile(r"[^0-9]")


def normalize_phone(raw: str | None) -> str | None:
    """Digits only, no plus sign, the way WhatsApp reports numbers. None when
    what is left is too short to be a phone number."""
    digits = _NON_DIGITS.sub("", raw or "")
    return digits if len(digits) >= 7 else None


def phone_from_chat_id(external_chat_id: str | None) -> str | None:
    """QR jids look like 5730011122@s.whatsapp.net; Cloud API ids are bare digits."""
    if not external_chat_id:
        return None
    return normalize_phone(external_chat_id.split("@", 1)[0])


def find_contact(db: Session, client_id, phone: str) -> Contact | None:
    return db.scalar(select(Contact).where(Contact.client_id == client_id, Contact.phone == phone))


def resolve_contact(db: Session, client_id, *, phone: str, name: str | None) -> Contact:
    """The contact for this number, created on first sight."""
    contact = find_contact(db, client_id, phone)
    if contact:
        if name and not contact.name.strip():
            contact.name = name.strip()[:180]
        return contact
    contact = Contact(client_id=client_id, phone=phone, name=(name or "").strip()[:180])
    db.add(contact)
    db.flush()
    return contact


def display_name(contact: Contact) -> str:
    return contact.name.strip() or (f"+{contact.phone}" if contact.phone else "Contact")


def rename_conversations(db: Session, contact: Contact) -> None:
    """Conversation titles follow the contact's name, so a rename shows
    everywhere at once."""
    db.execute(
        update(Conversation).where(Conversation.contact_id == contact.id).values(title=display_name(contact)[:240])
    )


def previous_conversation_recap(db: Session, conversation: Conversation, *, limit: int = 8) -> str:
    """A compact recap of the contact's latest resolved conversation, for the
    model to carry context into a new case. Empty when there is none."""
    if not conversation.contact_id:
        return ""
    previous = db.scalar(
        select(Conversation)
        .where(
            Conversation.contact_id == conversation.contact_id,
            Conversation.id != conversation.id,
            Conversation.status == "resolved",
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    if not previous:
        return ""
    exchanged = db.scalars(
        select(Message)
        .where(Message.conversation_id == previous.id, Message.kind == "message")
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()
    if not exchanged:
        return ""
    when: datetime = previous.resolved_at or previous.updated_at
    lines = [
        f"CONTEXTO DEL CONTACTO: esta persona ya habló con nosotros; su último caso se cerró el {when:%Y-%m-%d}. "
        "Últimos mensajes de ese caso, del más antiguo al más reciente:"
    ]
    for item in reversed(exchanged):
        who = "Cliente" if item.role == "user" else (item.sender_name or "Nosotros")
        text = (item.content or "").strip().replace("\n", " ")
        lines.append(f"- {who}: {text[:200]}")
    return "\n".join(lines)


def touch(contact: Contact) -> None:
    contact.updated_at = now_utc()
