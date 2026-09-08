"""Durable professional messaging ingress and normalized conversation events."""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from ..models import ContactIdentity, Conversation, Message, SocialChannel, SocialOutbox, SocialWebhookEvent, new_uuid, now_utc
from ..security import decrypt_secret
from . import social_graph
from .attachments import store_attachment
from .conversation_state import set_mode
from .social_media import fetch_inbound_media
from .whatsapp_inbound import InboundMessage, process_inbound, reply_delay_seconds

logger = logging.getLogger(__name__)


def event_time(value) -> datetime | None:
    try:
        if isinstance(value, str) and not value.replace(".", "", 1).isdigit():
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        else:
            numeric = float(value)
            stamp = datetime.fromtimestamp(numeric / 1000 if numeric > 10**11 else numeric, timezone.utc)
        return stamp if datetime(2000, 1, 1, tzinfo=timezone.utc) < stamp <= now_utc() + timedelta(minutes=5) else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def enqueue_webhook(db: Session, provider: str, payload: dict, channel: SocialChannel | None = None,
                    *, commit: bool = True) -> int:
    """The caller authenticates the raw body. A successful return means persisted."""
    if payload.get("object") != ("instagram" if provider == "instagram" else "page"):
        return 0
    count = 0
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        account_id = str(entry.get("id", ""))
        matched = channel or db.scalar(select(SocialChannel).where(
            SocialChannel.provider == provider, SocialChannel.external_account_id == account_id))
        if (not matched or matched.provider != provider or matched.external_account_id != account_id
                or not matched.is_enabled or matched.status not in {"connected", "reauthorization_required"}):
            continue
        for field in ("messaging", "standby"):
            for raw in entry.get(field, []):
                if not isinstance(raw, dict):
                    continue
                event = dict(raw)
                event["_standby"] = field == "standby"
                event.setdefault("timestamp", entry.get("time"))
                message = event.get("message") or {}
                mid = message.get("mid")
                # Message retries can change batch timestamps. Their stable id
                # wins; status/reaction/control events use the complete event.
                key = f"message:{mid}" if mid else "event:" + hashlib.sha256(
                    json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if len(key) > 512:
                    key = "message:" + hashlib.sha256(key.encode()).hexdigest()
                result = db.execute(insert(SocialWebhookEvent).values(
                    id=new_uuid(), channel_id=matched.id, external_event_id=key,
                    payload=event, status="pending", attempts=0, available_at=now_utc(), created_at=now_utc(),
                ).on_conflict_do_nothing(index_elements=["channel_id", "external_event_id"]).returning(SocialWebhookEvent.id))
                count += int(result.scalar_one_or_none() is not None)
    if commit:
        db.commit()
    return count


def _conversation(db: Session, channel: SocialChannel, person: str) -> Conversation | None:
    return db.scalar(select(Conversation).where(Conversation.social_channel_id == channel.id,
        Conversation.external_chat_id == person).order_by(Conversation.created_at.desc()).limit(1))


async def _name_contact(db: Session, channel: SocialChannel, person: str, sender: dict) -> None:
    """Give the sender's contact a name the first time it is needed.
    Webhooks only carry the sender id, so an unnamed contact is looked up on
    the provider once; a failed lookup leaves the message untouched."""
    from .contacts import rename_conversations, resolve_contact
    identity = db.scalar(select(ContactIdentity).where(
        ContactIdentity.client_id == channel.client_id, ContactIdentity.provider == channel.provider,
        ContactIdentity.external_account_id == channel.external_account_id, ContactIdentity.external_user_id == person))
    if identity and identity.contact.name.strip():
        return
    name = str(sender.get("name") or "").strip()
    username = str(sender.get("username") or "").strip() or None
    if not name and channel.encrypted_access_token and channel.encrypted_app_secret:
        try:
            profile = await social_graph.sender_profile(channel.provider, decrypt_secret(channel.encrypted_access_token),
                                                        decrypt_secret(channel.encrypted_app_secret), person)
            name = profile.get("name") or ""
            username = profile.get("username") or username
        except Exception as exc:
            logger.info("Sender profile unavailable on %s: %s", channel.provider, type(exc).__name__)
    name = name or username or ""
    if not name:
        return
    contact = resolve_contact(db, channel.client_id, provider=channel.provider, external_account_id=channel.external_account_id,
                              external_user_id=person, name=name, username=username)
    rename_conversations(db, contact)


def _message(db: Session, channel: SocialChannel, mid: str) -> Message | None:
    result = db.scalar(select(Message).join(Conversation).where(
        Conversation.social_channel_id == channel.id, Message.external_message_id == mid))
    if result:
        return result
    sent = db.scalar(select(SocialOutbox).where(SocialOutbox.channel_id == channel.id,
                                                SocialOutbox.external_message_id == mid))
    return db.get(Message, sent.message_id) if sent else None


class WaitForDelivery(Exception):
    pass


async def process_event(db: Session, channel: SocialChannel, event: dict) -> None:
    sender = str((event.get("sender") or {}).get("id") or "")
    recipient = str((event.get("recipient") or {}).get("id") or "")
    message = event.get("message") or {}
    echo = bool(message.get("is_echo") or sender == channel.external_account_id)
    historical = bool(event.get("_historical"))
    person = recipient if echo else sender
    if not person or person == channel.external_account_id:
        return
    # Both the envelope and the message must address this exact business.
    if (echo and sender != channel.external_account_id) or (not echo and recipient != channel.external_account_id):
        return
    conversation = _conversation(db, channel, person)
    occurred = event_time(event.get("timestamp"))
    if conversation and (event.get("_standby") or event.get("pass_thread_control") or event.get("take_thread_control")):
        control = event.get("pass_thread_control") or event.get("take_thread_control") or {}
        owner = str(control.get("new_owner_app_id") or "")
        if owner and channel.app_id:
            conversation.social_thread_owned = owner == channel.app_id
        elif event.get("_standby"):
            conversation.social_thread_owned = False
        db.commit()
    if conversation and (event.get("read") or event.get("delivery")):
        if db.scalar(select(SocialOutbox.id).where(
            SocialOutbox.conversation_id == conversation.id, SocialOutbox.status == "sending",
            SocialOutbox.locked_until > now_utc()).limit(1)):
            # The provider may emit its receipt before the Send API returns
            # the message ID. Keep the event until that ID can be matched.
            raise WaitForDelivery()
        receipt = event.get("read") or event.get("delivery")
        state = "read" if event.get("read") else "delivered"
        mids = receipt.get("mids") or ([receipt["mid"]] if receipt.get("mid") else [])
        watermark = event_time(receipt.get("watermark"))
        from .social_delivery import _finish_message
        parts = db.scalars(select(SocialOutbox).where(
            SocialOutbox.conversation_id == conversation.id,
            or_(SocialOutbox.external_message_id.in_([str(mid) for mid in mids]),
                SocialOutbox.sent_at <= watermark if watermark else False),
            SocialOutbox.status == "sent",
        )).all()
        touched = set()
        for part in parts:
            if part.receipt_status != "read":
                part.receipt_status = state
            touched.add(part.message_id)
        db.flush()
        for part in parts:
            if part.message_id in touched:
                _finish_message(db, part)
                touched.remove(part.message_id)
        # Native business replies have no outbox. Do not infer receipts for
        # pending or partially delivered multipart messages.
        for mid in mids:
            target = _message(db, channel, str(mid))
            if (target and target.conversation_id == conversation.id and target.role == "assistant"
                    and not db.scalar(select(SocialOutbox.id).where(SocialOutbox.message_id == target.id).limit(1))
                    and target.delivery_status in {"sent", "delivered"}):
                target.delivery_status = state
        db.commit()
        return
    if event.get("reaction"):
        target = _message(db, channel, str(event["reaction"].get("mid") or ""))
        if target and conversation and target.conversation_id == conversation.id:
            reaction = event["reaction"]
            target.incoming_reaction = None if reaction.get("action") == "unreact" else str(reaction.get("emoji") or reaction.get("reaction") or "")[:16]
            db.commit()
        return
    if not message and not event.get("postback"):
        return
    mid = message.get("mid") or (event.get("postback") or {}).get("mid") or ""
    if mid and (not isinstance(mid, str) or len(mid) > 1024
                or not all(32 < ord(char) < 127 for char in mid)):
        return
    if not mid:
        mid = "postback:" + hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
    if _message(db, channel, mid):
        return
    if historical:
        if not occurred or not channel.last_connected_at or occurred > channel.last_connected_at:
            return
        if not conversation:
            from .contacts import resolve_contact, display_name
            profile = event.get("recipient") if echo else event.get("sender")
            profile = profile or {}
            contact = resolve_contact(db, channel.client_id, provider=channel.provider,
                external_account_id=channel.external_account_id, external_user_id=person,
                name=profile.get("name"), username=profile.get("username"))
            conversation = Conversation(agency_id=channel.agency_id, client_id=channel.client_id,
                agent_id=channel.agent_id, channel=channel.provider, social_channel_id=channel.id,
                external_chat_id=person, contact_id=contact.id, title=display_name(contact),
                status="resolved", mode="human", resolved_at=channel.last_connected_at,
                operator_read_at=channel.last_connected_at, created_at=occurred, updated_at=occurred)
            db.add(conversation)
            db.flush()
        text = str(message.get("text") or "[Historical attachment unavailable]")
        db.add(Message(conversation_id=conversation.id, role="assistant" if echo else "user",
            content=text, sender_type="human" if echo else "visitor", is_historical=True,
            sender_name=channel.display_name if echo else None, external_message_id=mid,
            created_at=occurred, delivery_status="sent" if echo else None))
        db.commit()
        return
    if echo:
        # Allow the Send API result to arrive before an echo is classified as
        # a native/manual reply. No text-based identity guesses are made.
        sending = db.scalar(select(SocialOutbox.id).where(SocialOutbox.channel_id == channel.id,
            SocialOutbox.conversation_id == conversation.id if conversation else False,
            SocialOutbox.status == "sending", SocialOutbox.locked_until > now_utc()).limit(1))
        if sending:
            raise WaitForDelivery()
    text = str(message.get("text") or (event.get("postback") or {}).get("title") or "")
    attachments = message.get("attachments") or []
    fetched = []
    warnings = []
    total_bytes = 0
    for media in attachments[:10]:
        if not isinstance(media, dict):
            continue
        media_kind = media.get("type")
        url = str((media.get("payload") or {}).get("url") or "")
        if media_kind not in ("image", "audio", "video", "file") or not url:
            warnings.append("[Shared content is not available through this channel]")
            continue
        try:
            blob, blob_mime = await fetch_inbound_media(url)
            if total_bytes + len(blob) > 20 * 1024 * 1024:
                warnings.append("[Attachment unavailable: the message exceeds the 20 MB total limit]")
                continue
            total_bytes += len(blob)
            fetched.append((blob, blob_mime, media_kind))
        except Exception:
            warnings.append("[Attachment unavailable]")
    if len(attachments) > 10:
        warnings.append(f"[{len(attachments) - 10} additional attachments exceed the 10-file limit]")
    if message.get("is_unsupported") and not attachments:
        warnings.append("[Shared content is not available through this channel]")
    if warnings:
        text = "\n".join([text, *warnings]).strip()
    data, mime, kind = fetched[0] if fetched else (None, None, None)
    if echo:
        if not conversation:
            # Imported outgoing history alone must not create an active AI case.
            return
        own_app = bool(channel.app_id and str(message.get("app_id") or "") == channel.app_id)
        outgoing = Message(conversation_id=conversation.id, role="assistant", content=text,
            sender_type="ai" if own_app else "human", sender_name=channel.display_name or channel.provider,
            external_message_id=mid, delivery_status="sent", created_at=occurred or now_utc())
        db.add(outgoing)
        db.flush()
        for blob, blob_mime, media_kind in fetched:
            store_attachment(db, outgoing, data=blob, mime=blob_mime, kind=media_kind)
        if not own_app and not historical and conversation.status != "resolved":
            set_mode(db, conversation, "human", actor=channel.display_name or "Business inbox")
            conversation.social_reply_due_at = None
            from .conversation_state import note_reply
            if not conversation.social_last_inbound_at or (occurred and occurred >= conversation.social_last_inbound_at):
                note_reply(conversation)
        conversation.updated_at = now_utc()
        db.commit()
        return
    await _name_contact(db, channel, person, event.get("sender") or {})
    inbound = InboundMessage(external_message_id=mid, external_chat_id=person,
        text=text, media_kind=kind if kind in ("image", "audio", "video", "file") else None,
        sender_name=(event.get("sender") or {}).get("name") or (event.get("sender") or {}).get("username"),
        media_bytes=data, media_mime=mime, occurred_at=occurred,
        quoted_external_id=(message.get("reply_to") or {}).get("mid"))
    result = await process_inbound(db, channel, inbound, conversation_channel=channel.provider,
                                  channel_fk_field="social_channel_id", defer_reply=True)
    conversation = db.get(Conversation, result.conversation_id)
    if not conversation:
        return
    if len(fetched) > 1 and result.accepted:
        from .whatsapp_inbound import resolve_inbound_content
        incoming = _message(db, channel, mid)
        for blob, blob_mime, media_kind in fetched[1:]:
            store_attachment(db, incoming, data=blob, mime=blob_mime, kind=media_kind)
            _, context = await resolve_inbound_content(db, channel.agent, InboundMessage(
                external_message_id=mid, external_chat_id=person,
                media_kind=media_kind, media_bytes=blob, media_mime=blob_mime))
            incoming.llm_content = (incoming.llm_content or incoming.content) + "\n" + context
    if event.get("_standby"):
        conversation.social_thread_owned = False
    if channel.status == "reauthorization_required" and conversation.mode == "ai":
        set_mode(db, conversation, "human", actor="Channel authorization required")
    if conversation.mode == "ai" and occurred and occurred + timedelta(hours=24) > now_utc():
        conversation.social_reply_due_at = now_utc() + timedelta(seconds=reply_delay_seconds(channel.agent))
    elif conversation.mode == "human" and result.accepted:
        from .notifications import notify_needs_human
        await notify_needs_human(db, conversation, text)
    db.commit()


async def process_pending(db: Session, *, limit: int = 25) -> int:
    count = 0
    for _ in range(limit):
        now = now_utc()
        other = aliased(SocialWebhookEvent)
        event = db.scalar(select(SocialWebhookEvent).where(
            SocialWebhookEvent.status.in_(("pending", "processing")), SocialWebhookEvent.available_at <= now,
            or_(SocialWebhookEvent.locked_until.is_(None), SocialWebhookEvent.locked_until < now),
            ~exists(select(other.id).where(other.channel_id == SocialWebhookEvent.channel_id,
                other.id != SocialWebhookEvent.id, other.status == "processing", other.locked_until > now)),
        ).order_by(SocialWebhookEvent.created_at).with_for_update(skip_locked=True).limit(1))
        if not event:
            db.rollback()
            break
        event.status, event.locked_until = "processing", now + timedelta(minutes=5)
        event.attempts += 1
        event_id = event.id
        try:
            db.commit()
        except IntegrityError:
            # Another worker claimed a different event for this account.
            db.rollback()
            break
        try:
            channel = db.get(SocialChannel, event.channel_id)
            if channel and channel.is_enabled and channel.status in {"connected", "reauthorization_required"}:
                await process_event(db, channel, event.payload)
            event.status, event.processed_at, event.last_error = "processed", now_utc(), None
        except WaitForDelivery:
            event.status, event.available_at = "pending", now_utc() + timedelta(seconds=5)
        except Exception as exc:
            db.rollback()
            event = db.get(SocialWebhookEvent, event_id)
            if not event:
                continue
            event.status = "failed" if event.attempts >= 5 else "pending"
            event.available_at = now_utc() + timedelta(seconds=min(300, 2 ** event.attempts * 5))
            event.last_error = "This event could not be processed. Check the channel configuration and retry."
            logger.error("Social event processing failed for %s (%s)", event.id, type(exc).__name__)
        event.locked_until = None
        db.commit()
        count += 1
    return count
