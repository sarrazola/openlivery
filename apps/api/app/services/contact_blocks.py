"""Blocking a contact on WhatsApp itself, on top of the internal block.

The internal (soft) block keeps a person's messages and answers none of them;
the person notices nothing. A hard block also puts them on the block list of
the WhatsApp API number they wrote to, so they can no longer write to it and
the business cannot write to them. Meta keeps that list per business number
and only accepts people who wrote in the last 24 hours, so a hard block exists
only where both hold, and the contact remembers on which numbers it was placed
to lift it from the same ones.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Contact, Conversation, Message, WhatsAppCloudChannel
from ..security import decrypt_secret
from .whatsapp_cloud import block_user, unblock_user
from .whatsapp_templates import window_is_open

# Why a hard block cannot be offered for a contact.
NO_WHATSAPP_API = "no_whatsapp_api"
WINDOW_CLOSED = "window_closed"


def _usable(channel: WhatsAppCloudChannel | None) -> bool:
    return bool(channel and channel.encrypted_access_token and channel.phone_number_id)


def _candidates(db: Session, contact: Contact) -> list[tuple[WhatsAppCloudChannel, str, bool]]:
    """Each WhatsApp API number the contact has written to, with the identity
    they wrote from and whether Meta's 24-hour window is still open there."""
    rows = db.execute(
        select(Conversation.whatsapp_cloud_channel_id, Conversation.external_chat_id, func.max(Message.created_at))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Conversation.contact_id == contact.id,
            Conversation.channel == "whatsapp_cloud",
            Conversation.whatsapp_cloud_channel_id.is_not(None),
            Conversation.external_chat_id.is_not(None),
            Message.kind == "message",
            Message.sender_type == "visitor",
        )
        .group_by(Conversation.whatsapp_cloud_channel_id, Conversation.external_chat_id)
    ).all()
    found = []
    for channel_id, user, last_inbound in rows:
        channel = db.get(WhatsAppCloudChannel, channel_id)
        if _usable(channel):
            found.append((channel, user, window_is_open(last_inbound)))
    return found


def hard_block_unavailable(db: Session, contact: Contact) -> str | None:
    """Why this contact cannot be blocked on WhatsApp right now, or None."""
    candidates = _candidates(db, contact)
    if not candidates:
        return NO_WHATSAPP_API
    if not any(open_window for _, _, open_window in candidates):
        return WINDOW_CLOSED
    return None


async def place_hard_block(db: Session, contact: Contact) -> None:
    """Block the contact on every WhatsApp API number whose window is open.

    Raises when the contact cannot be hard-blocked or Meta refuses every
    number; a partial success keeps the numbers that accepted it."""
    reason = hard_block_unavailable(db, contact)
    if reason == NO_WHATSAPP_API:
        raise HTTPException(status_code=409, detail="This contact has not written to a WhatsApp API number, so it can only be soft-blocked")
    if reason == WINDOW_CLOSED:
        raise HTTPException(status_code=409, detail="WhatsApp only blocks people who wrote in the last 24 hours. This contact can only be soft-blocked for now")
    placed = list(contact.whatsapp_blocks or [])
    known = {(entry["channel_id"], entry["user"]) for entry in placed}
    refusal = None
    for channel, user, open_window in _candidates(db, contact):
        if not open_window or (str(channel.id), user) in known:
            continue
        refusal = await block_user(decrypt_secret(channel.encrypted_access_token), channel.phone_number_id, user)
        if refusal is None:
            placed.append({"channel_id": str(channel.id), "user": user})
    if not placed:
        raise HTTPException(status_code=502, detail=f"WhatsApp did not block this contact: {refusal}")
    contact.whatsapp_blocks = placed


async def lift_hard_block(db: Session, contact: Contact) -> None:
    """Take the contact off WhatsApp's block list wherever it was placed.

    A number that is gone or no longer has credentials is forgotten: nothing
    can reach its list. A number where Meta refuses stays recorded and the
    call raises, so the contact is not shown as unblocked while WhatsApp still
    blocks them."""
    remaining, refusal = [], None
    for entry in contact.whatsapp_blocks or []:
        channel = db.get(WhatsAppCloudChannel, entry["channel_id"])
        if not _usable(channel):
            continue
        failure = await unblock_user(decrypt_secret(channel.encrypted_access_token), channel.phone_number_id, entry["user"])
        if failure is not None:
            remaining.append(entry)
            refusal = failure
    contact.whatsapp_blocks = remaining or None
    if remaining:
        db.commit()
        raise HTTPException(status_code=502, detail=f"WhatsApp did not unblock this contact: {refusal}")
