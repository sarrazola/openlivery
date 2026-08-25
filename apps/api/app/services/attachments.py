"""Chat message attachments: persistence and serving helpers.

The original media bytes are stored next to the message (Postgres LargeBinary,
same pattern as knowledge documents). The LLM pipeline never reads them — it
uses the text resolved into ``Message.llm_content`` at ingestion time.
"""

import re
import uuid

from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Message, MessageAttachment

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def attachment_kind(mime: str) -> str:
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return "image"
    # video/ogg is what browsers label opus voice notes, not a real video.
    if mime.startswith("audio/") or mime.startswith("video/ogg"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    return "file"


def safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    return re.sub(r"[^\w. -]", "_", filename)[:255] or None


def store_attachment(
    db: Session,
    message: Message,
    *,
    data: bytes,
    mime: str,
    filename: str | None = None,
    kind: str | None = None,
) -> MessageAttachment:
    attachment = MessageAttachment(
        message_id=message.id,
        kind=kind or attachment_kind(mime),
        mime=(mime or "application/octet-stream")[:100],
        filename=safe_filename(filename),
        size_bytes=len(data),
        data=data,
    )
    db.add(attachment)
    return attachment


def conversation_attachment(db: Session, conversation: Conversation, attachment_id: uuid.UUID) -> MessageAttachment:
    """Load an attachment ensuring it belongs to the given conversation."""
    attachment = db.scalar(
        select(MessageAttachment)
        .join(Message, Message.id == MessageAttachment.message_id)
        .where(MessageAttachment.id == attachment_id, Message.conversation_id == conversation.id)
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


def attachment_response(attachment: MessageAttachment) -> Response:
    headers = {"Cache-Control": "private, max-age=3600"}
    if attachment.filename:
        headers["Content-Disposition"] = f'inline; filename="{attachment.filename}"'
    return Response(content=attachment.data, media_type=attachment.mime, headers=headers)


def llm_text(message: Message) -> str:
    """The text the LLM should see for a stored message."""
    return message.llm_content or message.content
