"""Channel-agnostic inbound WhatsApp pipeline.

Shared by the Baileys bridge endpoint and the Cloud API webhook: dedupe by
external message id, find or create the conversation, resolve media into text,
store the visitor message, and produce the AI reply unless a human operator has
taken over. The caller is responsible for actually delivering the reply.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Agent, Conversation, Message, now_utc
from .attachments import llm_text, store_attachment
from .knowledge import build_system_prompt, retrieve_knowledge
from .media import describe_image, transcribe_audio
from .notifications import notify_needs_human
from .providers import resolve_agent_credentials, resolve_provider_credentials
from .tools import run_completion
from .usage import record_usage


@dataclass
class InboundMessage:
    external_message_id: str
    external_chat_id: str
    sender_name: str | None = None
    text: str = ""
    media_kind: str | None = None
    media_bytes: bytes | None = None
    media_mime: str | None = None


@dataclass
class InboundResult:
    accepted: bool
    reply: str | None = None
    conversation_id: uuid.UUID | None = None
    mode: str | None = None
    outbound_message_id: uuid.UUID | None = None


def _media_placeholder(kind: str) -> str:
    if kind == "image":
        return "[El cliente envió una imagen]"
    if kind == "audio":
        return "[El cliente envió una nota de voz]"
    if kind == "video":
        return "[El cliente envió un video]"
    return "[El cliente envió un archivo]"


async def resolve_inbound_content(db: Session, agent: Agent, inbound: InboundMessage) -> tuple[str, str]:
    """Resolve what to store for the message as ``(display, llm)``: the visible
    chat text (the caption — the media file itself is kept as an attachment)
    and the text the LLM sees, transcribing/describing media when the agent's
    capabilities allow it. Best-effort: the LLM text falls back to a placeholder."""
    text = (inbound.text or "").strip()
    if not inbound.media_kind:
        return text, text
    if not inbound.media_bytes:
        return text, text or _media_placeholder(inbound.media_kind)
    enabled = (inbound.media_kind == "image" and agent.image_enabled) or (
        inbound.media_kind == "audio" and agent.audio_enabled
    )
    credentials = resolve_provider_credentials(db, agent.agency_id, "openai")
    if not enabled or not credentials:
        return text, text or _media_placeholder(inbound.media_kind)
    try:
        data = inbound.media_bytes
        base_url, api_key = credentials
        if inbound.media_kind == "image":
            model = agent.image_model.strip() or agent.model.strip()
            instruction = (
                "Describe con detalle el contenido de esta imagen para que un asistente pueda responder al cliente."
                + (f" El cliente escribió: {text}" if text else "")
            )
            description = await describe_image(base_url, api_key, model, data, inbound.media_mime or "image/jpeg", instruction)
            return text, (f"{text}\n\n" if text else "") + f"[Imagen recibida] {description}"
        model = agent.audio_model.strip() or "whisper-1"
        transcript = await transcribe_audio(base_url, api_key, model, data, "audio.ogg", inbound.media_mime or "audio/ogg")
        return text, (f"{text}\n\n" if text else "") + (transcript or _media_placeholder("audio"))
    except (HTTPException, ValueError):
        return text, text or _media_placeholder(inbound.media_kind)


async def process_inbound(
    db: Session,
    channel,
    inbound: InboundMessage,
    *,
    conversation_channel: str,
    channel_fk_field: str,
) -> InboundResult:
    """Run the shared pipeline for one inbound message.

    ``channel`` is a WhatsAppChannel or WhatsAppCloudChannel; both expose the
    same fields used here. ``conversation_channel`` and ``channel_fk_field``
    select the Conversation channel label and FK column for the caller.
    """
    fk_column = getattr(Conversation, channel_fk_field)

    existing = db.scalar(
        select(Message)
        .join(Conversation)
        .where(
            fk_column == channel.id,
            Message.external_message_id == inbound.external_message_id,
        )
    )
    if existing:
        return InboundResult(accepted=False, conversation_id=existing.conversation_id)

    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            fk_column == channel.id,
            Conversation.external_chat_id == inbound.external_chat_id,
        )
    )
    if not conversation:
        title = (inbound.sender_name or inbound.external_chat_id.split("@")[0])[:240]
        conversation = Conversation(
            agency_id=channel.agency_id,
            client_id=channel.client_id,
            agent_id=channel.agent_id,
            external_chat_id=inbound.external_chat_id,
            contact_name=inbound.sender_name,
            title=title,
            channel=conversation_channel,
            **{channel_fk_field: channel.id},
        )
        db.add(conversation)
        db.flush()
    elif inbound.sender_name:
        conversation.contact_name = inbound.sender_name

    display_content, llm_content = await resolve_inbound_content(db, channel.agent, inbound)
    visitor_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=display_content,
        llm_content=llm_content if llm_content != display_content else None,
        sender_type="visitor",
        sender_name=inbound.sender_name or "WhatsApp contact",
        external_message_id=inbound.external_message_id,
    )
    conversation.updated_at = now_utc()
    db.add(visitor_message)
    if inbound.media_kind and inbound.media_bytes:
        db.flush()
        store_attachment(
            db,
            visitor_message,
            data=inbound.media_bytes,
            mime=inbound.media_mime or ("image/jpeg" if inbound.media_kind == "image" else "audio/ogg"),
            kind=inbound.media_kind,
        )
    db.commit()
    if conversation.mode == "human":
        # An operator took this conversation over, so nothing will answer unless
        # a person sees it. This is the moment a phone should ring.
        await notify_needs_human(db, conversation, display_content or llm_content)
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="human")

    agent = channel.agent
    credentials = resolve_agent_credentials(db, agent)
    if not agent.is_active or not credentials or not agent.model.strip():
        channel.last_error = "A message was received, but the assigned agent is not ready (model or provider key missing)."
        channel.updated_at = now_utc()
        db.commit()
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="ai")

    knowledge = await retrieve_knowledge(db, agent, llm_content)
    db.refresh(conversation)
    history = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(agent.memory_limit)
    ).all()
    history = list(reversed(history))
    messages = [
        {"role": "system", "content": build_system_prompt(agent, knowledge.text)},
        *[{"role": item.role, "content": llm_text(item)} for item in history],
    ]
    base_url, api_key = credentials
    try:
        completion = await run_completion(
            db,
            agent,
            base_url,
            api_key,
            messages,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )
    except Exception as exc:
        channel.last_error = f"Message received, but the agent could not reply: {str(exc)[:400]}"
        channel.updated_at = now_utc()
        db.commit()
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="ai")

    outbound = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=completion.text,
        sources=knowledge.sources,
        tool_calls=completion.tool_calls,
        sender_type="ai",
        sender_name=agent.name,
    )
    record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
    conversation.updated_at = now_utc()
    channel.last_error = None
    db.add(outbound)
    db.commit()
    return InboundResult(
        accepted=True,
        reply=completion.text,
        conversation_id=conversation.id,
        mode="ai",
        outbound_message_id=outbound.id,
    )
