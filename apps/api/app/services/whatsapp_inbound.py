"""Channel-agnostic inbound WhatsApp pipeline.

Shared by the Baileys bridge endpoint and the Cloud API webhook: dedupe by
external message id, find or create the conversation, resolve media into text,
store the visitor message, and produce the AI reply unless a human operator has
taken over. The caller is responsible for actually delivering the reply.
"""

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import new_session
from .contacts import display_name, phone_from_chat_id, previous_conversation_recap, rename_conversations, resolve_contact
from .conversation_state import exchanged_only, note_inbound, note_reply
from ..models import Agent, Conversation, Message, now_utc
from .attachments import llm_text, store_attachment
from .knowledge import build_system_prompt, retrieve_knowledge
from .media import audio_filename, describe_image, transcribe_audio
from .notifications import notify_needs_human
from .providers import resolve_agent_credentials, resolve_provider_credentials
from .tools import run_completion
from .usage import record_usage
from .escalation import (
    active_rules as escalation_active_rules,
    apply_escalation,
    build_escalation_spec,
    escalation_enabled,
    escalation_prompt,
)
from .whatsapp import deliver_reaction, send_channel_message, signal_channel_read
from .whatsapp_format import parse_reply_directives


@dataclass
class InboundMessage:
    external_message_id: str
    external_chat_id: str
    sender_name: str | None = None
    text: str = ""
    media_kind: str | None = None
    media_bytes: bytes | None = None
    media_mime: str | None = None
    # External id of the message the visitor replied to (swipe-to-reply).
    quoted_external_id: str | None = None
    occurred_at: datetime | None = None


@dataclass
class InboundResult:
    accepted: bool
    reply: str | None = None
    conversation_id: uuid.UUID | None = None
    mode: str | None = None
    outbound_message_id: uuid.UUID | None = None
    # External id of the visitor message the reply quotes (swipe-to-reply).
    quote_external_id: str | None = None


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
        mime = inbound.media_mime or "audio/ogg"
        transcript = await transcribe_audio(base_url, api_key, model, data, audio_filename(mime), mime)
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
    defer_reply: bool = False,
) -> InboundResult:
    """Run the shared pipeline for one inbound message.

    ``channel`` is a WhatsAppChannel or WhatsAppCloudChannel; both expose the
    same fields used here. ``conversation_channel`` and ``channel_fk_field``
    select the Conversation channel label and FK column for the caller.
    """
    if conversation_channel == "whatsapp_cloud" and channel.coexistence:
        from .whatsapp_coexistence import lock_chats
        lock_chats(db, channel.id, [inbound.external_chat_id])
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

    # A message joins the chat's open conversation; once that is resolved the
    # next message starts a new case, so the same chat id can hold many.
    conversation = db.scalar(
        select(Conversation)
        .where(
            fk_column == channel.id,
            Conversation.external_chat_id == inbound.external_chat_id,
            Conversation.status != "resolved",
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if not conversation:
        if conversation_channel in ("instagram", "messenger"):
            contact = resolve_contact(db, channel.client_id, provider=conversation_channel,
                external_account_id=channel.external_account_id, external_user_id=inbound.external_chat_id,
                name=inbound.sender_name)
        else:
            phone = phone_from_chat_id(inbound.external_chat_id)
            contact = resolve_contact(db, channel.client_id, phone=phone, name=inbound.sender_name) if phone else None
        if contact:
            title = display_name(contact)[:240]
        else:
            title = (inbound.sender_name or inbound.external_chat_id.split("@")[0])[:240]
        conversation = Conversation(
            agency_id=channel.agency_id,
            client_id=channel.client_id,
            agent_id=channel.agent_id,
            external_chat_id=inbound.external_chat_id,
            contact_name=inbound.sender_name,
            contact_id=contact.id if contact else None,
            title=title,
            channel=conversation_channel,
            **{channel_fk_field: channel.id},
        )
        db.add(conversation)
        db.flush()
    elif inbound.sender_name:
        conversation.contact_name = inbound.sender_name
        contact = conversation.contact
        if contact and not contact.name.strip():
            contact.name = inbound.sender_name.strip()[:180]
            rename_conversations(db, contact)

    display_content, llm_content = await resolve_inbound_content(db, channel.agent, inbound)
    visitor_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=display_content,
        llm_content=llm_content if llm_content != display_content else None,
        sender_type="visitor",
        sender_name=inbound.sender_name or ("Contact" if conversation_channel in ("instagram", "messenger") else "WhatsApp contact"),
        external_message_id=inbound.external_message_id,
        **({"created_at": inbound.occurred_at} if inbound.occurred_at else {}),
    )
    if inbound.quoted_external_id:
        quoted = db.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.external_message_id == inbound.quoted_external_id,
            )
        )
        if quoted:
            visitor_message.quoted_message_id = quoted.id
    conversation.updated_at = now_utc()
    blocked = conversation.contact is not None and conversation.contact.blocked_at is not None
    if not blocked:
        note_inbound(db, conversation)
    if conversation_channel == "whatsapp_cloud" and channel.coexistence:
        occurred = inbound.occurred_at or now_utc()
        conversation.social_last_inbound_at = max(conversation.social_last_inbound_at or occurred, occurred)
    if conversation_channel in ("instagram", "messenger") and inbound.occurred_at:
        last = conversation.social_last_inbound_at
        if not last or inbound.occurred_at > last:
            conversation.social_last_inbound_at = inbound.occurred_at
        conversation.waiting_since = min(conversation.waiting_since, inbound.occurred_at)
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
    if defer_reply:
        db.flush()
        return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    db.commit()
    if blocked:
        # Kept for the record, answered by nobody, and no tokens spent: the
        # conversation stays out of the inboxes until the contact is unblocked.
        return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    if conversation.mode == "human":
        # An operator took this conversation over, so nothing will answer unless
        # a person sees it. This is the moment a phone should ring.
        await notify_needs_human(db, conversation, display_content or llm_content)
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="human")

    delay = reply_delay_seconds(channel.agent)
    if delay > 0:
        schedule_debounced_reply(conversation.id, delay)
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="ai")

    await _signal_read_and_typing(db, conversation, [inbound.external_message_id])
    return await _reply_with_ai(db, channel, conversation, llm_content, expected_last_message_id=visitor_message.id)


# Injected into the system prompt for WhatsApp conversations on both channels
# (kept in the customer's language, like the rest of the LLM-facing
# scaffolding). The model decides IF and WHEN with conversational judgment; the
# code only executes.
WHATSAPP_GESTURE_RULES = (
    "GESTOS DE WHATSAPP (opcionales; úsalos con moderación y criterio, como lo haría una persona):\n"
    "- Cuando el último mensaje del cliente no necesite una respuesta en texto y un gesto baste — en cualquier "
    "idioma: un agradecimiento, una despedida, una confirmación breve, un elogio, algo gracioso, un emoji —, "
    "puedes responder solo con una reacción: escribe únicamente la línea [react: EMOJI], eligiendo el emoji que "
    "mejor exprese tu reacción a ese mensaje y su tono (👍 ❤️ 😂 🙌 🎉 o cualquier otro). También puedes poner esa "
    "línea primero y añadir texto debajo.\n"
    "- La mayoría de las respuestas no necesitan ningún gesto. Nunca reacciones dos veces seguidas."
)

WHATSAPP_QUOTE_RULE = (
    "- El cliente envió varios mensajes seguidos, numerados abajo. Si tu respuesta se centra en uno en "
    "particular, puedes comenzar con la línea [quote: N] para responder citándolo (como al deslizar un "
    "mensaje en WhatsApp). Cítalo solo cuando aclare a qué respondes:\n{listing}"
)


def _trailing_visitor_burst(history: list[Message]) -> list[Message]:
    """The consecutive visitor messages at the end of the history — the burst
    the agent is about to answer, oldest first."""
    burst: list[Message] = []
    for item in reversed(history):
        if item.role != "user":
            break
        burst.append(item)
    return list(reversed(burst))


def _gesture_rules(burst: list[Message]) -> str:
    rules = WHATSAPP_GESTURE_RULES
    if len(burst) > 1:
        listing = "\n".join(f"[{index}] {llm_text(item)[:160]}" for index, item in enumerate(burst, start=1))
        rules += "\n" + WHATSAPP_QUOTE_RULE.format(listing=listing)
    return rules


async def _apply_gestures(
    db: Session, conversation: Conversation, completion_text: str, burst: list[Message]
) -> tuple[str, uuid.UUID | None, str | None]:
    """Execute the reply's leading gesture directives (react/quote) and strip
    them. Returns ``(clean_text, quoted_message_id, quote_external_id)``."""
    clean_text, emoji, quote_index = parse_reply_directives(completion_text)
    quoted_id: uuid.UUID | None = None
    quote_external: str | None = None
    if emoji and burst and burst[-1].external_message_id:
        target = burst[-1]
        try:
            await deliver_reaction(db, conversation, target, emoji)
            target.reaction = emoji
        except HTTPException:
            # A reaction is a gesture, never worth failing the reply over.
            pass
    if quote_index and 1 <= quote_index <= len(burst) and burst[quote_index - 1].external_message_id:
        quoted = burst[quote_index - 1]
        quoted_id = quoted.id
        quote_external = quoted.external_message_id
    return clean_text, quoted_id, quote_external


async def _signal_read_and_typing(db: Session, conversation: Conversation, message_external_ids: list[str]) -> None:
    """Blue-tick the visitor's burst and show "typing..." while the AI reply is
    generated — the moment the quiet window closes is when a human would have
    read the messages. Works on both WhatsApp channels; best-effort."""
    await signal_channel_read(db, conversation, message_external_ids, typing=True)


async def _reply_with_ai(db: Session, channel, conversation: Conversation, retrieval_query: str,
                         *, expected_last_message_id: uuid.UUID | None = None) -> InboundResult:
    """Generate and store the AI reply for the conversation's current history.

    ``retrieval_query`` drives knowledge retrieval: the triggering message's
    text on the synchronous path, or the whole visitor burst when debounced.
    """
    agent = channel.agent
    db.refresh(conversation)
    if conversation.mode == "human" or conversation.status == "resolved" or not channel.is_enabled:
        return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    if conversation.channel == "whatsapp_cloud" and channel.coexistence:
        from .whatsapp_coexistence import require_reply
        try:
            require_reply(conversation)
        except HTTPException:
            return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    if not channel.client.is_active:
        # An inactive client is switched off everywhere: the message is kept
        # for the record, nobody answers it and no tokens are spent.
        channel.last_error = "A message was received, but the client is inactive. Reactivate the client so its agent answers again."
        channel.updated_at = now_utc()
        db.commit()
        return InboundResult(accepted=True, conversation_id=conversation.id, mode="ai")
    credentials = resolve_agent_credentials(db, agent)
    if not agent.is_active or not credentials or not agent.model.strip():
        channel.last_error = "A message was received, but the assigned agent is not ready (model or provider key missing)."
        channel.updated_at = now_utc()
        db.commit()
        if conversation.channel in ("instagram", "messenger"):
            from .social_worker import hand_over_failed_reply
            await hand_over_failed_reply(db, conversation, channel.last_error)
        return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)

    knowledge = await retrieve_knowledge(db, agent, retrieval_query)
    db.refresh(conversation)
    history = db.scalars(
        exchanged_only(select(Message).where(Message.conversation_id == conversation.id))
        .order_by(Message.created_at.desc())
        .limit(agent.memory_limit)
    ).all()
    history = list(reversed(history))
    burst = _trailing_visitor_burst(history)
    system_content = build_system_prompt(agent, knowledge.text)
    recap = previous_conversation_recap(db, conversation)
    if recap:
        system_content += "\n\n" + recap
    escalation_specs = None
    escalation_holder: list = []
    if conversation.channel in ("whatsapp", "whatsapp_cloud"):
        system_content += "\n\n" + _gesture_rules(burst)
    if conversation.channel in ("whatsapp", "whatsapp_cloud", "instagram", "messenger"):
        rules = escalation_active_rules(db, agent)
        if escalation_enabled(db, agent, rules):
            system_content += "\n\n" + escalation_prompt(rules, builtin_enabled=agent.escalation_builtin_enabled)
            escalation_specs = [
                build_escalation_spec(rules, escalation_holder, builtin_enabled=agent.escalation_builtin_enabled)
            ]
    messages = [
        {"role": "system", "content": system_content},
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
            extra_specs=escalation_specs,
        )
    except Exception as exc:
        channel.last_error = ("Message received, but the agent could not reply. A person must continue this conversation."
                              if conversation.channel in ("instagram", "messenger")
                              else f"Message received, but the agent could not reply: {str(exc)[:400]}")
        channel.updated_at = now_utc()
        db.commit()
        if conversation.channel in ("instagram", "messenger"):
            from .social_worker import hand_over_failed_reply
            await hand_over_failed_reply(db, conversation, channel.last_error)
        return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)

    reply_text = completion.text
    if conversation.channel in ("whatsapp", "whatsapp_cloud"):
        # A Business app echo or an operator may take over during generation.
        # Re-read persisted state; cancelling an in-process timer is not enough
        # when the webhook was received by another process or event loop.
        db.refresh(conversation)
        db.refresh(channel)
        last_message = db.scalar(select(Message).where(Message.conversation_id == conversation.id,
            Message.kind == "message", Message.is_historical.is_(False)).order_by(Message.created_at.desc()).limit(1))
        if (conversation.mode == "human" or conversation.status == "resolved" or not channel.is_enabled
                or (last_message and last_message.role != "user")
                or (expected_last_message_id and (not last_message or last_message.id != expected_last_message_id))):
            record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
            db.commit()
            return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    if conversation.channel in ("instagram", "messenger"):
        from .social_policy import require_reply
        db.refresh(conversation)
        last_message = db.scalar(select(Message).where(Message.conversation_id == conversation.id,
            Message.kind == "message").order_by(Message.created_at.desc()).limit(1))
        try:
            require_reply(conversation, human=False)
            if expected_last_message_id and (not last_message or last_message.id != expected_last_message_id):
                raise HTTPException(status_code=409, detail="The conversation changed while generating the reply.")
        except HTTPException:
            record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
            db.commit()
            return InboundResult(accepted=True, conversation_id=conversation.id, mode=conversation.mode)
    quoted_message_id: uuid.UUID | None = None
    quote_external_id: str | None = None
    if conversation.channel in ("whatsapp", "whatsapp_cloud"):
        reply_text, quoted_message_id, quote_external_id = await _apply_gestures(
            db, conversation, completion.text, burst
        )

    outbound = None
    if reply_text:
        if conversation.channel not in ("instagram", "messenger"):
            note_reply(conversation)
        outbound = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=reply_text,
            sources=knowledge.sources,
            tool_calls=completion.tool_calls,
            sender_type="ai",
            sender_name=agent.name,
            quoted_message_id=quoted_message_id,
        )
        db.add(outbound)
        if conversation.channel in ("instagram", "messenger"):
            from .social_delivery import queue_message
            queue_message(db, conversation, outbound)
    record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
    conversation.updated_at = now_utc()
    channel.last_error = None
    if escalation_holder and conversation.channel in ("instagram", "messenger"):
        request = escalation_holder[-1]
        conversation.social_pending_escalation = {
            "message_id": str(outbound.id) if outbound else None,
            "reason": request.reason, "trigger": request.trigger,
            "rule_id": str(request.rule.id) if request.rule else None,
        }
    db.commit()
    if escalation_holder and conversation.channel not in ("instagram", "messenger"):
        # After the farewell is stored, so the thread reads chronologically:
        # the AI says goodbye, then the hand-over happens.
        await apply_escalation(db, conversation, agent, escalation_holder[-1])
    elif not reply_text and not escalation_holder and conversation.channel in ("instagram", "messenger"):
        from .social_worker import hand_over_failed_reply
        await hand_over_failed_reply(db, conversation,
            "The agent returned no reply. A person must continue this conversation.")
    return InboundResult(
        accepted=True,
        reply=reply_text or None,
        conversation_id=conversation.id,
        mode=conversation.mode,
        outbound_message_id=outbound.id if outbound else None,
        quote_external_id=quote_external_id,
    )


_pending_replies: dict[uuid.UUID, "asyncio.Task[None]"] = {}


def reply_delay_seconds(agent: Agent) -> float:
    """How long to wait before answering, drawn between the agent's bounds.

    A fresh draw per inbound message, so the pace varies within the range the
    operator chose. 0 (both bounds at zero) means answer synchronously.
    """
    low = float(agent.reply_delay_min_seconds)
    high = float(agent.reply_delay_max_seconds)
    if high <= 0:
        return 0.0
    if high < low:
        high = low
    return random.uniform(low, high)


def schedule_debounced_reply(conversation_id: uuid.UUID, delay: float) -> None:
    """(Re)start the conversation's quiet-window timer.

    Every inbound message cancels the previous timer, so the reply fires only
    once the window passes with no new visitor message, answering the whole
    burst as a single reply built from the stored history. Timers are
    in-process; a DB re-check when the timer fires keeps a stale one harmless.
    """
    previous = _pending_replies.pop(conversation_id, None)
    if previous is not None and not previous.done():
        previous.cancel()
    task = asyncio.get_running_loop().create_task(_debounced_reply(conversation_id, delay))
    _pending_replies[conversation_id] = task

    def _cleanup(finished: "asyncio.Task[None]") -> None:
        if _pending_replies.get(conversation_id) is finished:
            _pending_replies.pop(conversation_id, None)

    task.add_done_callback(_cleanup)


async def _debounced_reply(conversation_id: uuid.UUID, delay: float) -> None:
    await asyncio.sleep(delay)
    db = new_session()
    try:
        conversation = db.get(Conversation, conversation_id)
        if not conversation or conversation.mode == "human":
            return
        channel = conversation.whatsapp_channel or conversation.whatsapp_cloud_channel
        if not channel:
            return
        last = db.scalar(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.kind == "message")
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        if not last or last.role != "user":
            # A newer timer, another worker, or an operator already answered.
            return
        history = db.scalars(
            exchanged_only(select(Message).where(Message.conversation_id == conversation_id))
            .order_by(Message.created_at.desc())
            .limit(channel.agent.memory_limit)
        ).all()
        burst: list[str] = []
        burst_external_ids: list[str] = []
        for item in history:
            if item.role != "user":
                break
            burst.append(llm_text(item))
            if item.external_message_id:
                burst_external_ids.append(item.external_message_id)
        # The loop walks newest-first; read receipts go oldest-first.
        await _signal_read_and_typing(db, conversation, list(reversed(burst_external_ids)))
        try:
            result = await _reply_with_ai(db, channel, conversation, "\n".join(reversed(burst)), expected_last_message_id=last.id)
        except Exception as exc:
            channel.last_error = f"Message received, but the agent could not reply: {str(exc)[:400]}"
            channel.updated_at = now_utc()
            db.commit()
            return
        if not result.reply:
            return
        try:
            external_id = await send_channel_message(
                db, conversation, result.reply, quoted_external_id=result.quote_external_id
            )
        except HTTPException as exc:
            channel.last_error = f"The reply could not be sent: {exc.detail}"
            channel.updated_at = now_utc()
            db.commit()
            return
        if external_id and result.outbound_message_id:
            outbound = db.get(Message, result.outbound_message_id)
            if outbound:
                outbound.external_message_id = external_id
                db.commit()
    finally:
        db.close()
