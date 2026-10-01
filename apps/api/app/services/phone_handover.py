"""Persist phone takeovers and resume pending WhatsApp conversations after silence."""
from datetime import timedelta
import logging

from sqlalchemy import or_, select

from ..models import Conversation, Message, now_utc
from .attachments import llm_text
from .conversation_state import cancel_follow_up, note_reply, record_activity

logger = logging.getLogger(__name__)


def cancel_phone_pause(conversation):
    changed = conversation.phone_pause_until is not None
    conversation.phone_pause_until = None
    conversation.phone_resume_claimed_until = None
    return changed


def pause_from_phone(db, conversation, *, occurred_at=None, actor=None):
    """A phone reply may extend a timed pause, but never replace a manual hold."""
    now = now_utc()
    until = min(occurred_at or now, now) + timedelta(minutes=conversation.agent.phone_handover_minutes)
    if (conversation.status == "resolved" or until <= now
            or (conversation.mode == "human" and conversation.phone_pause_until is None)):
        return False
    first = conversation.phone_pause_until is None
    conversation.phone_pause_until = max(conversation.phone_pause_until or until, until)
    conversation.phone_resume_claimed_until = None
    conversation.mode = "human"
    conversation.taken_over_at = now
    cancel_follow_up(conversation)
    if first:
        record_activity(db, conversation, "answered_from_phone", actor=actor)
    return True


def record_outgoing(db, channel, payload):
    """Mirror a phone message once, resolving contacts even when the business starts."""
    from .contacts import display_name, phone_from_chat_id, resolve_contact
    from .routing import route_new_conversation_by_tags
    from .whatsapp_coexistence import lock_chats

    lock_chats(db, channel.id, [payload.remote_jid])
    existing = db.scalar(select(Message).join(Conversation).where(
        Conversation.whatsapp_channel_id == channel.id,
        Message.external_message_id == payload.external_message_id))
    if existing:
        return
    phone = phone_from_chat_id(payload.remote_jid)
    contact = resolve_contact(db, channel.client_id, phone=phone) if phone else None
    conversation = db.scalar(select(Conversation).where(
        Conversation.whatsapp_channel_id == channel.id,
        Conversation.external_chat_id == payload.remote_jid,
        Conversation.status != "resolved").order_by(Conversation.created_at.desc()).limit(1)
        .with_for_update().execution_options(populate_existing=True))
    if not conversation:
        conversation = Conversation(agency_id=channel.agency_id, client_id=channel.client_id,
            agent_id=channel.agent_id, channel="whatsapp", whatsapp_channel_id=channel.id,
            external_chat_id=payload.remote_jid, contact_id=contact.id if contact else None,
            title=display_name(contact)[:240] if contact else payload.remote_jid.split("@")[0][:240])
        db.add(conversation)
        db.flush()
        route_new_conversation_by_tags(db, conversation, contact)
    elif not conversation.contact_id and contact:
        conversation.contact = contact
        route_new_conversation_by_tags(db, conversation, contact)
    occurred = payload.occurred_at or now_utc()
    content = payload.text.strip()
    if not content:
        labels = {"audio": ("Voice note", "Nota de voz"), "image": ("Image", "Imagen"),
                  "video": ("Video", "Video"), "sticker": ("Sticker", "Sticker"),
                  "document": ("File", "Archivo")}
        label = labels.get(payload.media_kind, ("File", "Archivo"))[conversation.agent.prompt_language == "es"]
        content = f"[{label}]"
    db.add(Message(conversation_id=conversation.id, role="assistant", sender_type="human",
        sender_name=channel.client.name, content=content,
        external_message_id=payload.external_message_id, created_at=occurred))
    pause_from_phone(db, conversation, occurred_at=occurred, actor=channel.client.name)
    # A delayed echo must not mark a newer customer question as answered.
    if not conversation.waiting_since or occurred >= conversation.waiting_since:
        note_reply(conversation)
    conversation.updated_at = max(conversation.updated_at, occurred)
    db.commit()


def _last_message(db, conversation):
    return db.scalar(select(Message).where(Message.conversation_id == conversation.id,
        Message.kind == "message", Message.is_historical.is_(False))
        .order_by(Message.created_at.desc()).limit(1))


async def resume_due(db, *, limit=10):
    """A database deadline survives restarts; a lease prevents competing workers."""
    from .whatsapp import send_channel_message
    from .whatsapp_inbound import _reply_with_ai

    processed = 0
    for _ in range(limit):
        now = now_utc()
        conversation = db.scalar(select(Conversation).where(
            Conversation.phone_pause_until <= now,
            or_(Conversation.phone_resume_claimed_until.is_(None), Conversation.phone_resume_claimed_until <= now),
        ).order_by(Conversation.phone_pause_until).with_for_update(skip_locked=True).limit(1)
        .execution_options(populate_existing=True))
        if not conversation:
            db.rollback()
            break
        deadline = conversation.phone_pause_until
        channel = conversation.whatsapp_channel or conversation.whatsapp_cloud_channel
        blocked = conversation.contact and conversation.contact.blocked_at is not None
        if (conversation.status == "resolved" or blocked or not channel or not channel.is_enabled
                or channel.status != "connected" or not channel.client.is_active or not conversation.agent.is_active):
            cancel_phone_pause(conversation)
            db.commit()
            continue
        if conversation.mode == "human":
            conversation.mode = "ai"
            conversation.assignee_id = None
            conversation.assigned_at = None
            record_activity(db, conversation, "resumed_after_phone")
        last = _last_message(db, conversation)
        if not last or last.role != "user":
            cancel_phone_pause(conversation)
            db.commit()
            continue
        conversation.phone_resume_claimed_until = now + timedelta(minutes=5)
        db.commit()
        try:
            result = await _reply_with_ai(db, channel, conversation, llm_text(last), expected_last_message_id=last.id)
            db.refresh(conversation)
            if result.reply and conversation.mode == "ai" and conversation.phone_pause_until == deadline:
                external_id = await send_channel_message(db, conversation, result.reply,
                                                         quoted_external_id=result.quote_external_id)
                if result.outbound_message_id and external_id:
                    db.get(Message, result.outbound_message_id).external_message_id = external_id
                    db.commit()
            db.refresh(conversation)
            if conversation.phone_pause_until == deadline:
                latest = _last_message(db, conversation)
                conversation.phone_resume_claimed_until = None
                # A new visitor turn during generation gets another pass.
                if not latest or latest.role != "user" or latest.id == last.id:
                    cancel_phone_pause(conversation)
                db.commit()
        except Exception:
            db.rollback()
            db.refresh(conversation)
            if conversation.phone_pause_until == deadline:
                cancel_phone_pause(conversation)
                conversation.mode = "human"
                record_activity(db, conversation, "taken_over")
                db.commit()
            logger.warning("Phone handover reply failed for %s", conversation.id)
        processed += 1
    return processed
