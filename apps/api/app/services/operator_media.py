"""Operator media replies, shared by the agency inbox and the client portal:
deliver an image/audio/video/file through the conversation's channel and store
the message together with its attachment.

Like visitor media, the file is resolved into LLM-visible text (transcript or
description) stored in ``Message.llm_content`` so the agent keeps full context
of what happened while a human was handling the conversation."""

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .conversation_state import note_reply
from ..models import Agent, Conversation, Message, now_utc
from .attachments import MAX_ATTACHMENT_BYTES, attachment_kind, store_attachment
from .media import describe_image, transcribe_audio
from .providers import resolve_provider_credentials
from .whatsapp import send_channel_media


def _operator_media_marker(kind: str) -> str:
    """LLM-visible note for an operator media message (kept in the customer's
    language, like the rest of the LLM-facing markers)."""
    if kind == "image":
        return "[El operador envió una imagen]"
    if kind == "audio":
        return "[El operador envió un audio]"
    if kind == "video":
        return "[El operador envió un video]"
    return "[El operador envió un archivo]"


async def _operator_media_llm_text(
    db: Session, agent: Agent, *, kind: str, data: bytes, mime: str, caption: str, filename: str | None
) -> str:
    """Marker plus a best-effort transcript/description, so the agent knows
    what the operator actually sent when the conversation returns to AI mode."""
    detail = ""
    enabled = (kind == "image" and agent.image_enabled) or (kind == "audio" and agent.audio_enabled)
    credentials = resolve_provider_credentials(db, agent.agency_id, "openai") if enabled else None
    if credentials:
        base_url, api_key = credentials
        try:
            if kind == "image":
                model = agent.image_model.strip() or agent.model.strip()
                instruction = (
                    "Describe brevemente el contenido de esta imagen que un operador humano envió al cliente,"
                    " para que el asistente tenga contexto de la conversación."
                )
                detail = await describe_image(base_url, api_key, model, data, mime, instruction)
            else:
                model = agent.audio_model.strip() or "whisper-1"
                detail = await transcribe_audio(base_url, api_key, model, data, filename or "audio.ogg", mime) or ""
        except (HTTPException, ValueError):
            detail = ""
    if kind == "file" and filename:
        detail = filename
    parts = [_operator_media_marker(kind)]
    if detail:
        parts.append(detail)
    if caption:
        parts.append(caption)
    return " ".join(parts)


async def store_operator_media_reply(
    db: Session,
    conversation: Conversation,
    *,
    file: UploadFile,
    caption: str,
    sender_name: str,
) -> None:
    """Caller must have verified the conversation is in human mode."""
    content_type = (file.content_type or "").lower() or "application/octet-stream"
    kind = attachment_kind(content_type)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large (20 MB max)")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    caption = caption.strip()

    external_message_id = await send_channel_media(
        db, conversation, kind=kind, data=data, mime=content_type, filename=file.filename, caption=caption
    )
    llm_content = await _operator_media_llm_text(
        db, conversation.agent, kind=kind, data=data, mime=content_type, caption=caption, filename=file.filename
    )
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=caption,
        llm_content=llm_content,
        sender_type="human",
        sender_name=sender_name,
        external_message_id=external_message_id,
    )
    db.add(message)
    db.flush()
    store_attachment(db, message, data=data, mime=content_type, filename=file.filename, kind=kind)
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
