"""The WhatsApp Cloud API reply window, checked where messages leave.

A free-form message is accepted for 24 hours after the person's last one;
outside that only an approved template goes through. The check lives next to
the send, not in the routes that call it, so every path that delivers a
message (a person in the inbox, the agent, work added later) meets the same
rule without having to opt in.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Conversation, Message
from .whatsapp_templates import window_is_open

WINDOW_CLOSED = "The 24-hour reply window is closed. Send an approved template to reach this person."


def last_inbound_at(db: Session, conversation: Conversation):
    """When the person last wrote, from the stored messages."""
    return db.scalar(
        select(func.max(Message.created_at)).where(
            Message.conversation_id == conversation.id,
            Message.kind == "message",
            Message.sender_type == "visitor",
        )
    )


def require_open_window(db: Session, conversation: Conversation) -> None:
    """Refuse a free-form message on a WhatsApp Cloud API conversation whose
    window is closed. Other channels have no window here."""
    if conversation.channel != "whatsapp_cloud":
        return
    if not window_is_open(last_inbound_at(db, conversation)):
        raise HTTPException(status_code=409, detail=WINDOW_CLOSED)
