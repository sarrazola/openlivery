"""Telegram bots as a messaging channel of a client.

A bot is connected with the token @BotFather issued for it, nothing else. It
rides the same durable machinery as the other messaging accounts: the row is a
``SocialChannel`` with provider ``telegram``, updates land in the webhook inbox
(``social_webhook_events``), replies leave through the outbox, and the social
worker drives both. What differs lives here: how a bot is connected, and how a
Telegram update becomes an inbound message.

Telegram calls one webhook per bot, the channel's own public address, and
proves itself with the secret it was given when the webhook was set
(``webhook_verify_token``, sent back as ``X-Telegram-Bot-Api-Secret-Token``).
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Conversation, Message, SocialChannel, SocialWebhookEvent, User, new_public_id, new_uuid, now_utc
from ..security import decrypt_secret, encrypt_secret
from . import telegram_api
from .attachments import attachment_kind, safe_filename
from .social_connections import notify_connection, owned_client

logger = logging.getLogger(__name__)

PROVIDER = "telegram"
WEBHOOK_PATH = "/api/public/social/channels/{channel_id}/webhook"

# What the model reads for the message Telegram sends when someone opens the
# bot for the first time (or taps Start again).
OPENED_CHAT = "[The contact opened the chat and has not written anything yet]"


# --- where Telegram calls back -------------------------------------------------

# Telegram reaches the deployment at SOCIAL_PUBLIC_URL (or FRONTEND_URL). A
# deployment that serves each agency on its own address registers one function
# at startup returning the base URL for an agency, or None for the configured one.
PublicBase = Callable[[Session, Any], "str | None"]
_public_base: PublicBase | None = None


def register_public_base(resolver: PublicBase | None) -> None:
    """Install what says where an agency's bot webhooks arrive; None removes it."""
    global _public_base
    _public_base = resolver


def webhook_url(db: Session, channel: SocialChannel) -> str:
    base = _public_base(db, channel.agency_id) if _public_base is not None else None
    if not base:
        settings = get_settings()
        base = settings.social_public_url or settings.frontend_url
    base = (base or "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(409, "Telegram delivers messages only to a public HTTPS address. "
                                 "Set SOCIAL_PUBLIC_URL (or FRONTEND_URL) to one and connect the bot again.")
    return base + WEBHOOK_PATH.format(channel_id=channel.id)


# --- connection -------------------------------------------------------------------

def public_channel(db: Session, channel: SocialChannel) -> dict:
    keys = ("id", "client_id", "agent_id", "provider", "external_account_id", "display_name", "username", "label",
            "status", "is_enabled", "last_error", "last_connected_at", "created_at", "updated_at")
    return {**{key: getattr(channel, key) for key in keys}, "has_token": bool(channel.encrypted_access_token)}


def client_channels(db: Session, user: User, client_id) -> list[SocialChannel]:
    owned_client(db, user, client_id)
    return db.scalars(select(SocialChannel).where(
        SocialChannel.client_id == client_id, SocialChannel.agency_id == user.agency_id,
        SocialChannel.provider == PROVIDER,
    ).order_by(SocialChannel.created_at)).all()


def owned_channel(db: Session, user: User, channel_id) -> SocialChannel:
    channel = db.scalar(select(SocialChannel).where(
        SocialChannel.id == channel_id, SocialChannel.agency_id == user.agency_id, SocialChannel.provider == PROVIDER))
    if not channel:
        raise HTTPException(404, "This Telegram bot is not connected")
    return channel


async def connect_bot(db: Session, user: User, client_id, agent_id, token: str, *, label: str | None = None,
                      channel: SocialChannel | None = None) -> SocialChannel:
    """Check the token with Telegram, keep it encrypted and point the bot's
    webhook here. ``channel`` is the row being reconnected, which must stay on
    the same bot; without it the client's row for this bot is reused or a new
    one is added."""
    token = (token or "").strip()
    if not telegram_api.valid_token(token):
        raise HTTPException(422, "Paste the full token @BotFather gave you: digits, a colon and a long code.")
    owned_client(db, user, client_id, agent_id)
    me = await telegram_api.get_me(token)
    bot_id = str(me["id"])
    if channel is not None and channel.external_account_id and channel.external_account_id != bot_id:
        raise HTTPException(409, "This token belongs to another bot. Connect that bot as a new one.")
    # A bot has a single webhook, so it can answer for one client only.
    taken = db.scalar(select(SocialChannel.id).where(
        SocialChannel.provider == PROVIDER, SocialChannel.external_account_id == bot_id,
        SocialChannel.encrypted_access_token.is_not(None),
        SocialChannel.id != (channel.id if channel is not None else uuid.uuid4()),
        SocialChannel.client_id != client_id,
    ))
    if taken:
        raise HTTPException(409, "This bot is already connected to another client.")
    if channel is None:
        channel = db.scalar(select(SocialChannel).where(
            SocialChannel.client_id == client_id, SocialChannel.agency_id == user.agency_id,
            SocialChannel.provider == PROVIDER, SocialChannel.external_account_id == bot_id).with_for_update())
    try:
        if channel is None:
            channel = SocialChannel(agency_id=user.agency_id, client_id=client_id, agent_id=agent_id,
                                    provider=PROVIDER, webhook_verify_token=new_public_id())
            db.add(channel)
        channel.agent_id = agent_id
        if label is not None:
            channel.label = label.strip()[:80] or None
        # The bot id is both the account and, for deployments that route
        # webhooks by app and account, the app.
        channel.external_account_id = bot_id
        channel.app_id = bot_id
        channel.display_name = str(me.get("first_name") or "")[:180] or None
        channel.username = str(me.get("username") or "")[:180] or None
        channel.encrypted_access_token = encrypt_secret(token)
        channel.encrypted_app_secret = None
        channel.token_expires_at = None
        channel.granted_scopes = []
        channel.connection_source = "token"
        channel.webhook_verify_token = channel.webhook_verify_token or new_public_id()
        channel.status = "connected"
        channel.is_enabled = True
        channel.last_error = None
        channel.last_connected_at = now_utc()
        channel.updated_at = now_utc()
        db.flush()
        notify_connection(db, channel, "linked")
        await telegram_api.set_webhook(token, webhook_url(db, channel), channel.webhook_verify_token)
        db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "This bot is already connected.") from None
        raise
    db.refresh(channel)
    return channel


async def reconnect(db: Session, user: User, channel: SocialChannel) -> SocialChannel:
    """Check the stored token again and set the webhook anew, for when the
    public address moved or the bot was pointed somewhere else."""
    if not channel.encrypted_access_token:
        raise HTTPException(400, "Paste the bot's token to connect it.")
    return await connect_bot(db, user, channel.client_id, channel.agent_id,
                             decrypt_secret(channel.encrypted_access_token), channel=channel)


def check_secret(channel: SocialChannel, received: str) -> bool:
    expected = channel.webhook_verify_token or ""
    return bool(expected) and hmac.compare_digest(expected.encode("utf-8"), (received or "").encode("utf-8"))


def enqueue_update(db: Session, channel: SocialChannel, update: dict) -> bool:
    """Persist one update before acknowledging it. Telegram retries until it
    is acknowledged, and the update id keeps a retry from being stored twice."""
    if not channel.is_enabled or channel.status != "connected":
        return False
    update_id = update.get("update_id")
    key = f"update:{update_id}" if isinstance(update_id, int) else "event:" + hashlib.sha256(
        json.dumps(update, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = db.execute(insert(SocialWebhookEvent).values(
        id=new_uuid(), channel_id=channel.id, external_event_id=key, payload=update, status="pending",
        attempts=0, available_at=now_utc(), created_at=now_utc(),
    ).on_conflict_do_nothing(index_elements=["channel_id", "external_event_id"]).returning(SocialWebhookEvent.id))
    stored = result.scalar_one_or_none() is not None
    db.commit()
    return stored


# --- inbound ----------------------------------------------------------------------

def _sender_name(sender: dict) -> str | None:
    name = " ".join(part.strip() for part in (str(sender.get("first_name") or ""), str(sender.get("last_name") or ""))
                    if part.strip())
    return name[:180] or None


def _media(message: dict) -> tuple[str, str, str | None, str] | None:
    """``(file_id, kind, filename, mime)`` of the file a message carries, if any."""
    if isinstance(message.get("photo"), list) and message["photo"]:
        # Sizes come smallest first; the largest a bot may download wins.
        sizes = [item for item in message["photo"] if isinstance(item, dict) and item.get("file_id")]
        fitting = [item for item in sizes if int(item.get("file_size") or 0) <= telegram_api.MAX_DOWNLOAD_BYTES]
        chosen = (fitting or sizes)[-1] if sizes else None
        return (chosen["file_id"], "image", None, "image/jpeg") if chosen else None
    for field, kind, default_mime in (("voice", "audio", "audio/ogg"), ("audio", "audio", "audio/mpeg"),
                                      ("video", "video", "video/mp4"), ("video_note", "video", "video/mp4"),
                                      ("document", "file", "application/octet-stream")):
        item = message.get(field)
        if isinstance(item, dict) and item.get("file_id"):
            mime = str(item.get("mime_type") or default_mime).lower()
            if field == "document":
                kind = attachment_kind(mime)
            return item["file_id"], kind, safe_filename(item.get("file_name")), mime
    sticker = message.get("sticker")
    if isinstance(sticker, dict) and sticker.get("file_id") and not sticker.get("is_animated") and not sticker.get("is_video"):
        return sticker["file_id"], "image", None, "image/webp"
    return None


def _labels(message: dict) -> list[str]:
    """What a message without words still says, for the thread and the model."""
    labels = []
    sticker = message.get("sticker")
    if isinstance(sticker, dict):
        labels.append(f"[Sticker {sticker.get('emoji') or ''}]".replace(" ]", "]"))
    location = message.get("location")
    if isinstance(location, dict) and "latitude" in location and "longitude" in location:
        venue = message.get("venue") if isinstance(message.get("venue"), dict) else {}
        place = " ".join(str(venue.get(key) or "") for key in ("title", "address")).strip()
        labels.append(f"[Location{': ' + place if place else ''}] "
                      f"https://maps.google.com/?q={location['latitude']},{location['longitude']}")
    contact = message.get("contact")
    if isinstance(contact, dict):
        name = " ".join(str(contact.get(key) or "") for key in ("first_name", "last_name")).strip()
        labels.append(f"[Shared contact] {name} {contact.get('phone_number') or ''}".strip())
    for field, label in (("poll", "Poll"), ("dice", "Dice"), ("game", "Game"), ("story", "Shared story")):
        if message.get(field):
            labels.append(f"[{label}]")
    return labels


def _existing(db: Session, channel: SocialChannel, external_id: str) -> Message | None:
    return db.scalar(select(Message).join(Conversation).where(
        Conversation.social_channel_id == channel.id, Message.external_message_id == external_id))


async def process_update(db: Session, channel: SocialChannel, update: dict, *, last_attempt: bool = True) -> None:
    """Apply one update. ``last_attempt`` False lets a file that would not
    download raise ``MediaNotFetched`` so the queue tries the event again."""
    from .contacts import rename_conversations, resolve_contact
    from .social_inbound import MediaNotFetched, event_time
    from .whatsapp_inbound import InboundMessage, process_inbound, reply_delay_seconds

    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    if chat.get("type") != "private" or sender.get("is_bot") or not chat.get("id") or not message.get("message_id"):
        return
    person = str(chat["id"])
    mid = telegram_api.external_id(person, message["message_id"])
    if _existing(db, channel, mid):
        return
    occurred = event_time(message.get("date"))
    text = str(message.get("text") or message.get("caption") or "").strip()
    opened = text == "/start" or text.startswith("/start ")
    media = _media(message)
    data = mime = kind = filename = None
    warnings = []
    if media:
        file_id, kind, filename, mime = media
        try:
            data = await telegram_api.download(decrypt_secret(channel.encrypted_access_token), file_id)
        except HTTPException as exc:
            logger.warning("Inbound Telegram %s was not fetched: %s %s", kind, exc.status_code, exc.detail)
            if exc.status_code not in (401, 413, 422) and not last_attempt:
                raise MediaNotFetched() from exc
            warnings.append("[Attachment unavailable: larger than 20 MB]" if exc.status_code == 413
                            else "[Attachment unavailable]")
            data = None
    labels = _labels(message)
    if not text and not media and not labels:
        labels.append("[This kind of message is not supported on this channel]")
    body = "\n".join(part for part in (*labels, text, *warnings) if part)
    name = _sender_name(sender)
    username = str(sender.get("username") or "").strip() or None
    contact = resolve_contact(db, channel.client_id, provider=PROVIDER, external_account_id=channel.external_account_id,
                              external_user_id=person, name=name, username=username)
    rename_conversations(db, contact)
    reply_to = message.get("reply_to_message") if isinstance(message.get("reply_to_message"), dict) else {}
    inbound = InboundMessage(
        external_message_id=mid, external_chat_id=person, text=body, sender_name=name or username,
        media_kind=kind if data else None, media_bytes=data, media_mime=mime if data else None,
        occurred_at=occurred,
        quoted_external_id=telegram_api.external_id(person, reply_to["message_id"]) if reply_to.get("message_id") else None,
    )
    result = await process_inbound(db, channel, inbound, conversation_channel=PROVIDER,
                                   channel_fk_field="social_channel_id", defer_reply=True)
    conversation = db.get(Conversation, result.conversation_id) if result.conversation_id else None
    if not conversation:
        return
    incoming = _existing(db, channel, mid)
    if incoming is not None:
        if opened:
            incoming.llm_content = OPENED_CHAT
        if filename and data:
            for attachment in incoming.attachments:
                attachment.filename = filename
    if conversation.mode == "ai" and occurred and occurred + timedelta(hours=24) > now_utc():
        conversation.social_reply_due_at = now_utc() + timedelta(seconds=reply_delay_seconds(channel.agent))
    elif conversation.mode == "human" and result.accepted:
        from .notifications import notify_needs_human
        await notify_needs_human(db, conversation, body)
    db.commit()
