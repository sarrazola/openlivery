"""Durable delivery: store each part before contacting the provider."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, aliased

from ..models import Conversation, Message, MessageAttachment, SocialChannel, SocialOutbox, now_utc
from .conversation_state import note_reply
from .social_policy import require_reply
from .social_media import attachment_url


def split_text(text: str, provider: str) -> list[str]:
    """Respect byte limits without splitting a Unicode code point."""
    limit = 1000 if provider == "instagram" else 2000
    chunks, current, size = [], [], 0
    for char in text:
        width = len(char.encode("utf-8")) if provider == "instagram" else 1
        if size + width > limit:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += width
    if current:
        chunks.append("".join(current))
    return chunks


def queue_message(db: Session, conversation: Conversation, message: Message, *, attachment: MessageAttachment | None = None) -> None:
    human = message.sender_type == "human"
    require_reply(conversation, human=human)
    if not conversation.external_chat_id or not conversation.social_channel_id:
        raise HTTPException(status_code=409, detail="This conversation has no channel destination.")
    db.flush()
    payloads = []
    if attachment:
        payloads.append({"attachment_id": str(attachment.id), "kind": attachment.kind})
    payloads.extend({"text": part} for part in split_text(message.content, conversation.channel))
    if not payloads:
        raise HTTPException(status_code=422, detail="Write a message or attach a file.")
    for part, payload in enumerate(payloads):
        payload.update(recipient_id=conversation.external_chat_id, human=human)
        db.add(SocialOutbox(channel_id=conversation.social_channel_id, conversation_id=conversation.id,
                            message_id=message.id, part=part, payload=payload))
    message.delivery_status = "pending"
    message.delivery_error = None


def _finish_message(db: Session, row: SocialOutbox, error: str | None = None) -> None:
    message = db.get(Message, row.message_id)
    if not message:
        return
    siblings = db.scalars(select(SocialOutbox).where(SocialOutbox.message_id == row.message_id)).all()
    states = {item.status for item in siblings}
    if "unknown" in states:
        message.delivery_status = "unknown"
    elif "failed" in states or "cancelled" in states:
        message.delivery_status = "failed"
    elif states <= {"sent"}:
        receipts = {item.receipt_status for item in siblings}
        message.delivery_status = "read" if receipts == {"read"} else (
            "delivered" if receipts <= {"delivered", "read"} else "sent")
        conversation = db.get(Conversation, row.conversation_id)
        if conversation and (not conversation.social_last_inbound_at or message.created_at >= conversation.social_last_inbound_at):
            note_reply(conversation)
    else:
        message.delivery_status = "pending"
    message.delivery_error = error or next((item.last_error for item in siblings if item.status in {"failed", "unknown", "cancelled"}), None)


async def process_outbox(db: Session, *, limit: int = 25) -> int:
    from . import social_graph
    count = 0
    # An interrupted POST has an ambiguous outcome. Never send it twice blindly.
    abandoned = db.scalars(select(SocialOutbox).where(
        SocialOutbox.status == "sending", SocialOutbox.locked_until < now_utc(),
    ).with_for_update(skip_locked=True)).all()
    for item in abandoned:
        item.status = "unknown"
        item.last_error = "Delivery was interrupted. Check the conversation before sending again."
        _finish_message(db, item, item.last_error)
    db.commit()
    for _ in range(limit):
        earlier = aliased(SocialOutbox)
        row = db.scalar(select(SocialOutbox).where(
            SocialOutbox.status == "pending", SocialOutbox.available_at <= now_utc(),
            ~exists(select(earlier.id).where(earlier.conversation_id == SocialOutbox.conversation_id,
                earlier.status.in_(("pending", "sending")),
                or_(earlier.created_at < SocialOutbox.created_at,
                    (earlier.message_id == SocialOutbox.message_id) & (earlier.part < SocialOutbox.part)))),
        ).order_by(SocialOutbox.created_at, SocialOutbox.part).with_for_update(skip_locked=True).limit(1))
        if not row:
            db.rollback()
            break
        conversation = db.get(Conversation, row.conversation_id)
        channel = db.get(SocialChannel, row.channel_id)
        try:
            if not conversation or not channel or conversation.social_channel_id != channel.id:
                raise HTTPException(status_code=409, detail="The channel destination is no longer available.")
            db.refresh(conversation)
            db.refresh(channel)
            # A failed or uncertain previous part must not produce a truncated reply.
            previous_failure = db.scalar(select(SocialOutbox.id).where(
                SocialOutbox.message_id == row.message_id, SocialOutbox.part < row.part,
                SocialOutbox.status.in_(("failed", "unknown", "cancelled")),
            ).limit(1))
            if previous_failure:
                raise HTTPException(status_code=409, detail="An earlier part of this message was not delivered.")
            human_agent = require_reply(conversation, human=bool(row.payload.get("human")))
            media_url = None
            if row.payload.get("attachment_id"):
                attachment = db.get(MessageAttachment, row.payload["attachment_id"])
                if not attachment or attachment.message_id != row.message_id:
                    raise HTTPException(status_code=409, detail="The attachment is unavailable.")
                media_url = attachment_url(channel, attachment)
        except HTTPException as exc:
            row.status, row.last_error = "failed", str(exc.detail)[:400]
            db.flush()
            _finish_message(db, row, row.last_error)
            db.commit()
            continue
        row.status, row.locked_until = "sending", now_utc() + timedelta(minutes=2)
        row.attempts += 1
        db.commit()
        try:
            # Sessions remain alive across worker stages. Refresh again after
            # the claim commit so a takeover or revocation cannot use a cached
            # permission decision at the external send boundary.
            db.refresh(conversation)
            db.refresh(channel)
            human_agent = require_reply(conversation, human=bool(row.payload.get("human")))
            if media_url:
                external_id = await social_graph.send_media(channel, row.payload["recipient_id"],
                    row.payload["kind"], media_url, human_agent=human_agent)
            else:
                external_id = await social_graph.send_text(channel, row.payload["recipient_id"],
                    row.payload["text"], human_agent=human_agent)
            if not external_id:
                raise ValueError("No delivery identifier was returned")
            row.status, row.external_message_id, row.sent_at = "sent", external_id, now_utc()
            message = db.get(Message, row.message_id)
            if message and not message.external_message_id:
                message.external_message_id = external_id
            row.last_error = None
        except HTTPException as exc:
            # Retry only explicit rate-limit refusals. Network/server failures
            # can occur after the provider accepted a message.
            if exc.status_code in (401, 403):
                channel.status = "reauthorization_required"
                channel.last_error = str(exc.detail)[:400]
                channel.updated_at = now_utc()
            if exc.status_code == 429 and row.attempts < 5:
                row.status = "pending"
                row.available_at = now_utc() + timedelta(seconds=min(300, 2 ** row.attempts * 5))
            else:
                row.status = "unknown" if exc.status_code >= 500 else "failed"
            row.last_error = str(exc.detail)[:400]
        except Exception:
            row.status = "unknown"
            row.last_error = "Delivery could not be confirmed. Check the conversation before sending again."
        row.locked_until = None
        db.flush()
        _finish_message(db, row, row.last_error)
        db.commit()
        count += 1
    return count
