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
from .media import audio_filename, describe_image, transcribe_audio
from .model_catalog import DEFAULT_AUDIO_MODEL
from .providers import DEFAULT_PROVIDER, resolve_provider_credentials
from .usage import record_usage, schedule_generation_reconcile
from .whatsapp import send_channel_media
from .social_policy import SOCIAL_PROVIDERS


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
    db: Session, conversation: Conversation, message: Message, *, kind: str, data: bytes, mime: str, caption: str, filename: str | None
) -> str:
    """Marker plus a best-effort transcript/description, so the agent knows
    what the operator actually sent when the conversation returns to AI mode.
    The call is usage like any reply, recorded against the conversation and
    the operator's (pending) message."""
    detail = ""
    agent: Agent = conversation.agent
    enabled = (kind == "image" and agent.image_enabled) or (kind == "audio" and agent.audio_enabled)
    credentials = resolve_provider_credentials(db, agent.agency_id, DEFAULT_PROVIDER) if enabled else None
    if credentials:
        base_url, api_key = credentials
        try:
            if kind == "image":
                model = agent.image_model.strip() or agent.model.strip()
                instruction = (
                    "Describe brevemente el contenido de esta imagen que un operador humano envió al cliente,"
                    " para que el asistente tenga contexto de la conversación."
                )
                result = await describe_image(base_url, api_key, model, data, mime, instruction)
            else:
                model = agent.audio_model.strip() or DEFAULT_AUDIO_MODEL
                result = await transcribe_audio(base_url, api_key, model, data, filename or audio_filename(mime), mime)
            record = record_usage(db, agent.agency_id, agent.id, DEFAULT_PROVIDER, model, result, conversation=conversation, message=message)
            schedule_generation_reconcile(record, result, base_url, api_key)
            detail = result.text or ""
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
    portal_user_id=None,
) -> None:
    """Caller must have verified the conversation is in human mode."""
    from .phone_handover import cancel_phone_pause
    if cancel_phone_pause(conversation):
        db.commit()
    content_type = (file.content_type or "").lower() or "application/octet-stream"
    filename = file.filename
    kind = attachment_kind(content_type)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large (20 MB max)")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    caption = caption.strip()
    social = conversation.channel in SOCIAL_PROVIDERS
    if social:
        from .social_policy import require_reply
        from .social_media import converted_filename, prepare_media
        require_reply(conversation, human=True)
        data, content_type = await prepare_media(conversation.channel, data, content_type, kind)
        filename = converted_filename(filename, content_type)
        external_message_id = None
    else:
        external_message_id = await send_channel_media(
            db, conversation, kind=kind, data=data, mime=content_type, filename=file.filename, caption=caption
        )
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=caption,
        sender_type="human",
        sender_name=sender_name,
        portal_user_id=portal_user_id,
        external_message_id=external_message_id,
    )
    message.llm_content = await _operator_media_llm_text(
        db, conversation, message, kind=kind, data=data, mime=content_type, caption=caption, filename=filename
    )
    db.add(message)
    db.flush()
    attachment = store_attachment(db, message, data=data, mime=content_type, filename=filename, kind=kind)
    if social:
        from .social_delivery import queue_message
        queue_message(db, conversation, message, attachment=attachment)
    else:
        note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
