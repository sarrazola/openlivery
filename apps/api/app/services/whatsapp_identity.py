"""Keep Meta's opaque user identifiers distinct from telephone numbers."""

import re

_USER_ID = re.compile(r"[A-Z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128}\Z")


def is_user_id(value: str | None) -> bool:
    return isinstance(value, str) and bool(_USER_ID.fullmatch(value))


def user_id(message: dict, direction: str = "from") -> str | None:
    for key in (f"{direction}_user_id", f"{direction}_parent_user_id"):
        if is_user_id(message.get(key)):
            return message[key]
    return None


def peer_id(message: dict, direction: str = "from") -> str | None:
    return message.get(direction) or user_id(message, direction)


def recipient_fields(recipient: str) -> dict:
    # Meta requires `recipient`, not `to`, when the phone number is hidden.
    return {"recipient" if is_user_id(recipient) else "to": recipient}


def contact_names(contacts: list[dict]) -> dict[str, str]:
    names = {}
    for contact in contacts:
        profile = contact.get("profile") or {}
        name = profile.get("name") or profile.get("username") or contact.get("username")
        for key in ("wa_id", "user_id", "parent_user_id"):
            if contact.get(key) and name:
                names[contact[key]] = name
    return names


def resolve_peer_contact(db, channel, peer: str, *, name=None, sender_user_id=None):
    from .contacts import find_contact, phone_from_chat_id, resolve_contact

    phone = phone_from_chat_id(peer)
    identity = sender_user_id or (peer if is_user_id(peer) else None)
    if identity:
        contact = resolve_contact(db, channel.client_id, provider="whatsapp",
            external_account_id=channel.waba_id or channel.phone_number_id or str(channel.id),
            external_user_id=identity, phone=phone, name=name)
        if phone and not contact.phone and not find_contact(db, channel.client_id, phone):
            contact.phone = phone
            db.flush()
        return contact
    return resolve_contact(db, channel.client_id, phone=phone, name=name) if phone else None
