"""Naming the account a conversation runs on.

A client may have several WhatsApp lines or social accounts. The inbox then
needs to say which one a conversation belongs to: the operator's label for
that account, or a short fallback (the number's last digits, the handle)
when no label was given. With a single account the badge is noise, so the
fallback only appears once the client has more than one on that channel.
"""

import re
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Conversation, SocialChannel, WhatsAppChannel, WhatsAppCloudChannel


_FAMILY = {
    "whatsapp": (WhatsAppChannel, "whatsapp_channel_id"),
    "whatsapp_cloud": (WhatsAppCloudChannel, "whatsapp_cloud_channel_id"),
    "instagram": (SocialChannel, "social_channel_id"),
    "messenger": (SocialChannel, "social_channel_id"),
}


def phone_suffix(phone: str | None, digits: int = 4) -> str | None:
    """The last digits of a number, however the provider formatted it."""
    only_digits = re.sub(r"\D", "", phone or "")
    return only_digits[-digits:] if len(only_digits) >= digits else None


def fallback_label(channel) -> str | None:
    """What identifies the account when the operator gave it no name."""
    if isinstance(channel, (WhatsAppChannel, WhatsAppCloudChannel)):
        suffix = phone_suffix(channel.phone_number)
        return f"\u00b7\u00b7\u00b7{suffix}" if suffix else channel.display_name
    if isinstance(channel, SocialChannel):
        return f"@{channel.username}" if channel.username else channel.display_name
    return None


def account_name(channel) -> str | None:
    """The label, else the fallback: the name to show wherever the account is
    listed on its own (channel pages, the line picker)."""
    if channel is None:
        return None
    return (channel.label or "").strip() or fallback_label(channel)


def _family_filter(model, conversation_channel: str):
    if model is SocialChannel:
        return (SocialChannel.provider == conversation_channel,)
    return ()


def sibling_count(db: Session, conversation: Conversation) -> int:
    family = _FAMILY.get(conversation.channel)
    if not family:
        return 0
    model, _ = family
    return db.scalar(
        select(func.count(model.id)).where(model.client_id == conversation.client_id, *_family_filter(model, conversation.channel))
    ) or 0


def _channel_of(db: Session, conversation: Conversation):
    family = _FAMILY.get(conversation.channel)
    if not family:
        return None
    model, fk = family
    channel_id = getattr(conversation, fk)
    return db.get(model, channel_id) if channel_id else None


def account_label(db: Session | None, conversation: Conversation) -> str | None:
    if db is None or conversation.channel not in _FAMILY:
        return None
    channel = _channel_of(db, conversation)
    if channel is None:
        return None
    if (channel.label or "").strip():
        return channel.label.strip()
    return fallback_label(channel) if sibling_count(db, conversation) > 1 else None


def annotate(db: Session, conversations: list[Conversation]) -> None:
    """Compute ``account_label`` for a list in a handful of queries instead of
    one per row. Rows on channels without accounts get None."""
    wanted: dict[type, set[uuid.UUID]] = {}
    for conversation in conversations:
        family = _FAMILY.get(conversation.channel)
        if not family:
            conversation.__dict__["_account_label"] = None
            continue
        model, fk = family
        channel_id = getattr(conversation, fk)
        if channel_id:
            wanted.setdefault(model, set()).add(channel_id)
        else:
            conversation.__dict__["_account_label"] = None
    channels = {}
    for model, ids in wanted.items():
        for row in db.scalars(select(model).where(model.id.in_(ids))):
            channels[row.id] = row
    counts: Counter = Counter()
    client_ids = {row.client_id for row in channels.values()}
    if client_ids:
        for model in (WhatsAppChannel, WhatsAppCloudChannel):
            for client_id, n in db.execute(
                select(model.client_id, func.count(model.id)).where(model.client_id.in_(client_ids)).group_by(model.client_id)
            ):
                counts[(model.__name__, client_id, None)] = n
        for client_id, provider, n in db.execute(
            select(SocialChannel.client_id, SocialChannel.provider, func.count(SocialChannel.id))
            .where(SocialChannel.client_id.in_(client_ids)).group_by(SocialChannel.client_id, SocialChannel.provider)
        ):
            counts[("SocialChannel", client_id, provider)] = n
    for conversation in conversations:
        if "_account_label" in conversation.__dict__:
            continue
        model, fk = _FAMILY[conversation.channel]
        channel = channels.get(getattr(conversation, fk))
        if channel is None:
            conversation.__dict__["_account_label"] = None
            continue
        if (channel.label or "").strip():
            conversation.__dict__["_account_label"] = channel.label.strip()
            continue
        key = (model.__name__, channel.client_id, conversation.channel if model is SocialChannel else None)
        conversation.__dict__["_account_label"] = fallback_label(channel) if counts.get(key, 0) > 1 else None
