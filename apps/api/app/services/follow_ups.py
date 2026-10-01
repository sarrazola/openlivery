"""Inactivity follow-ups, and the closing they end in.

When a contact stops answering, the agent that was talking to them writes
again: once after the first delay, optionally a second time, and a last time
to close the case. Every delay counts from the agent's last reply, so the
whole sequence is fixed the moment that reply is stored.

The clock lives on the conversation (``follow_up_*``), so it survives a
restart. ``run_due`` is the only reader: it claims one conversation at a time
under a lease, which keeps two workers from sending the same message. Whatever
ends the silence stops the clock where it happens (``cancel_follow_up`` in
``conversation_state``), and ``run_due`` looks again before anything leaves, so
a path that forgets to stop it still cannot send a message nobody wanted.

The same clock carries a pending resolution. A case the agent settled, or one
whose closing message is still on its way out, ends a short while later rather
than at once: the last message is delivered while the conversation is still
open, and a contact who writes back in that time simply keeps talking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Agent, Conversation, Message, now_utc
from .ai import Completion, chat_completion
from .capture import capture_context, field_definitions
from .conversation_state import cancel_follow_up, exchanged_only, hours_shown, resolve_without_a_person
from .knowledge import build_system_prompt, contact_context, llm_turns
from .providers import resolve_agent_credentials
from .usage import record_usage

logger = logging.getLogger(__name__)

# Channels a follow-up can go out on. The playground is a test bench, not a
# contact: nobody is waiting there.
FOLLOW_UP_CHANNELS = ("whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget")
MIN_MINUTES = 5
# Messaging channels accept free-form messages for 24 hours after the
# contact's last one. The whole sequence stays inside that, with room for the
# reply the delays count from.
MAX_MINUTES = 23 * 60
# How long a requested resolution waits before it is applied.
RESOLVE_GRACE = timedelta(minutes=2)
_LEASE = timedelta(minutes=5)
_HISTORY_LIMIT = 20

# LLM-facing text, in the language of the agent's prompt like the rest of it.
_TEXT = {
    "es": {
        "first": (
            "SEGUIMIENTO POR INACTIVIDAD: el cliente dejó de responder después de tu último mensaje y vas a "
            "escribirle de nuevo por iniciativa propia.\n"
            "- Escribe un solo mensaje, breve y natural, en el idioma del cliente, que retome lo último que estaban "
            "tratando: lo que quedó pendiente, la pregunta que le hiciste o el siguiente paso.\n"
            "- No repitas tu mensaje anterior ni saludes como si la conversación empezara. No presiones, no "
            "reproches el silencio y no inventes ofertas, precios ni datos.\n"
            "- Responde únicamente con el texto del mensaje."
        ),
        "second": (
            "SEGUIMIENTO POR INACTIVIDAD: el cliente sigue sin responder, tampoco a tu seguimiento anterior, y vas "
            "a escribirle una vez más por iniciativa propia.\n"
            "- Escribe un solo mensaje, más corto que el anterior y distinto, en el idioma del cliente, que le deje "
            "fácil retomar lo que estaban tratando.\n"
            "- No repitas lo que ya dijiste. No presiones, no reproches el silencio y no inventes ofertas, precios "
            "ni datos.\n"
            "- Responde únicamente con el texto del mensaje."
        ),
        "close": (
            "CIERRE POR INACTIVIDAD: el cliente no ha respondido y esta conversación se va a cerrar.\n"
            "- Escribe un solo mensaje breve de cierre, en el idioma del cliente y en contexto con lo que estaban "
            "tratando: dile con amabilidad que, como no has tenido respuesta, cierras la conversación por ahora, y "
            "que puede volver a escribir cuando quiera para retomarla.\n"
            "- Sin reproches y sin inventar ofertas, precios ni datos.\n"
            "- Responde únicamente con el texto del mensaje."
        ),
        "cue": "[Aviso automático, no es un mensaje del cliente: han pasado {elapsed} sin respuesta. Escribe ahora el mensaje de seguimiento.]",
        "cue_close": "[Aviso automático, no es un mensaje del cliente: han pasado {elapsed} sin respuesta. Escribe ahora el mensaje de cierre.]",
        "hour": "hora", "hours": "horas", "minute": "minuto", "minutes": "minutos", "and": "y",
    },
    "en": {
        "first": (
            "INACTIVITY FOLLOW-UP: the customer stopped answering after your last message and you are writing to "
            "them again on your own initiative.\n"
            "- Write a single message, short and natural, in the customer's language, that picks up what you were "
            "last dealing with: what was left pending, the question you asked or the next step.\n"
            "- Do not repeat your previous message or greet as if the conversation were starting. Do not push, do "
            "not reproach the silence and do not invent offers, prices or facts.\n"
            "- Reply with the text of the message only."
        ),
        "second": (
            "INACTIVITY FOLLOW-UP: the customer still has not answered, not even your previous follow-up, and you "
            "are writing once more on your own initiative.\n"
            "- Write a single message, shorter than the previous one and different from it, in the customer's "
            "language, that makes it easy to pick up what you were dealing with.\n"
            "- Do not repeat what you already said. Do not push, do not reproach the silence and do not invent "
            "offers, prices or facts.\n"
            "- Reply with the text of the message only."
        ),
        "close": (
            "CLOSING FOR INACTIVITY: the customer has not answered and this conversation is about to be closed.\n"
            "- Write a single short closing message, in the customer's language and in context with what you were "
            "dealing with: tell them kindly that, having had no answer, you are closing the conversation for now, "
            "and that they can write again whenever they like to pick it up.\n"
            "- No reproach, and no invented offers, prices or facts.\n"
            "- Reply with the text of the message only."
        ),
        "cue": "[Automatic notice, not a message from the customer: {elapsed} have passed without an answer. Write the follow-up message now.]",
        "cue_close": "[Automatic notice, not a message from the customer: {elapsed} have passed without an answer. Write the closing message now.]",
        "hour": "hour", "hours": "hours", "minute": "minute", "minutes": "minutes", "and": "and",
    },
}


@dataclass(frozen=True)
class Step:
    kind: str  # "first" | "second" | "close"
    minutes: int


def check_schedule(enabled: bool, first: int | None, second: int | None, close: int | None, channels: list[str]) -> None:
    """Raise ``ValueError`` unless the schedule can run as written."""
    unknown = [channel for channel in channels if channel not in FOLLOW_UP_CHANNELS]
    if unknown:
        raise ValueError(f"Unknown channel: {unknown[0]}")
    for value in (first, second, close):
        if value is not None and not MIN_MINUTES <= value <= MAX_MINUTES:
            raise ValueError(f"Each delay must be between {MIN_MINUTES} minutes and {MAX_MINUTES // 60} hours.")
    if second is not None and first is None:
        raise ValueError("Set the first follow-up before adding a second one.")
    if enabled and (first is None or close is None):
        raise ValueError("Set when the first follow-up goes out and when the conversation closes.")
    ordered = [value for value in (first, second, close) if value is not None]
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:])):
        raise ValueError("Each delay must be longer than the one before it.")


def steps_for(agent: Agent) -> list[Step]:
    """The agent's sequence, or nothing when it is off or incomplete."""
    first, second, close = agent.follow_up_first_minutes, agent.follow_up_second_minutes, agent.follow_up_close_minutes
    if not agent.follow_up_enabled or not first or not close:
        return []
    steps = [Step("first", first)]
    if second:
        steps.append(Step("second", second))
    steps.append(Step("close", close))
    return steps


def applies_to(agent: Agent, conversation: Conversation) -> bool:
    if conversation.channel not in FOLLOW_UP_CHANNELS:
        return False
    chosen = agent.follow_up_channels or []
    return not chosen or conversation.channel in chosen


def arm(conversation: Conversation, agent: Agent) -> bool:
    """Start the clock from the reply the agent just gave."""
    steps = steps_for(agent)
    if (not steps or not applies_to(agent, conversation) or conversation.status != "open"
            or conversation.mode != "ai" or conversation.phone_pause_until is not None):
        cancel_follow_up(conversation)
        return False
    now = now_utc()
    conversation.pending_resolution = None
    conversation.follow_up_anchor_at = now
    conversation.follow_up_due_at = now + timedelta(minutes=steps[0].minutes)
    conversation.follow_up_step = 0
    conversation.follow_up_claimed_until = None
    return True


def request_resolution(
    conversation: Conversation, event: str, *, actor: str | None = None, details: dict | None = None
) -> None:
    """Leave the case to be resolved once the grace period passes in silence."""
    now = now_utc()
    conversation.pending_resolution = {
        "event": event, "actor": actor, "details": details or {}, "requested_at": now.isoformat(),
    }
    conversation.follow_up_anchor_at = now
    conversation.follow_up_due_at = now + RESOLVE_GRACE
    conversation.follow_up_step = 0
    conversation.follow_up_claimed_until = None


def after_agent_reply(conversation: Conversation, agent: Agent, resolution=None, *, replied: bool = True) -> None:
    """What the agent's turn leaves on the clock: the resolution it asked
    for, or the follow-up schedule counting from the reply it just gave."""
    if conversation.status != "open" or conversation.mode != "ai":
        return
    if resolution is not None:
        request_resolution(conversation, "resolved_by_agent", actor=agent.name, details={"reason": resolution.reason})
    elif replied:
        arm(conversation, agent)


def _elapsed(minutes: int, lang: str) -> str:
    words = _TEXT[lang]
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} {words['hour'] if hours == 1 else words['hours']}")
    if rest:
        parts.append(f"{rest} {words['minute'] if rest == 1 else words['minutes']}")
    return f" {words['and']} ".join(parts)


def _last_message(db: Session, conversation: Conversation) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.kind == "message", Message.is_historical.is_(False))
        .order_by(Message.created_at.desc())
        .limit(1)
    )


def _agent_holds_it(conversation: Conversation) -> bool:
    return conversation.status == "open" and conversation.mode == "ai" and conversation.phone_pause_until is None


def _silent(conversation: Conversation, last: Message | None) -> bool:
    """The agent spoke last and nobody else has stepped in."""
    return bool(_agent_holds_it(conversation) and last and last.role == "assistant" and last.sender_type == "ai")


def _reachable(db: Session, conversation: Conversation) -> bool:
    """Whether a message can go out now, checked before paying for one."""
    kind = conversation.channel
    if kind == "widget":
        return bool(conversation.widget_channel and conversation.widget_channel.is_enabled)
    if kind in ("instagram", "messenger"):
        from .social_policy import window_fields
        return bool(conversation.social_channel_id and conversation.external_chat_id
                    and window_fields(conversation)["reply_window_open"])
    channel = conversation.whatsapp_channel or conversation.whatsapp_cloud_channel
    if not channel or not channel.is_enabled or channel.status != "connected" or not conversation.external_chat_id:
        return False
    if kind == "whatsapp_cloud":
        if channel.coexistence:
            from .whatsapp_coexistence import window_fields as coexistence_window
            return bool(coexistence_window(conversation)["reply_window_open"])
        from .reply_window import last_inbound_at
        from .whatsapp_templates import window_is_open
        return window_is_open(last_inbound_at(db, conversation))
    return True


async def _compose(db: Session, conversation: Conversation, agent: Agent, step: Step) -> Completion | None:
    """Ask the model for the message, with the thread it continues. No tools:
    a follow-up only speaks."""
    credentials = resolve_agent_credentials(db, agent)
    if not credentials or not agent.model.strip():
        return None
    lang = agent.prompt_language if agent.prompt_language in _TEXT else "es"
    text = _TEXT[lang]
    history = db.scalars(
        exchanged_only(select(Message).where(Message.conversation_id == conversation.id))
        .order_by(Message.created_at.desc())
        .limit(agent.memory_limit or _HISTORY_LIMIT)
    ).all()
    definitions = field_definitions(db, agent.client_id, agent.prompt_language)
    system = build_system_prompt(agent, "", capture_context(agent, conversation, definitions, agent.prompt_language))
    contact = contact_context(conversation, agent.prompt_language, definitions)
    if contact:
        system += "\n\n" + contact
    system += "\n\n" + text[step.kind]
    cue = text["cue_close" if step.kind == "close" else "cue"].format(elapsed=_elapsed(step.minutes, lang))
    messages = [
        {"role": "system", "content": system},
        *llm_turns(list(reversed(history)), agent.prompt_language),
        {"role": "user", "content": cue},
    ]
    base_url, api_key = credentials
    started = time.perf_counter()
    completion = await chat_completion(
        agent.provider, base_url, api_key, agent.model.strip(), messages,
        temperature=agent.temperature, max_tokens=agent.max_tokens,
    )
    completion.duration_ms = int((time.perf_counter() - started) * 1000)
    return completion


async def _deliver(db: Session, conversation: Conversation, agent: Agent, text: str) -> Message | None:
    """Send the message through the conversation's channel and store it.
    Returns None when the channel refused it: nothing is kept then."""
    message = Message(
        conversation_id=conversation.id, role="assistant", content=text, sender_type="ai", sender_name=agent.name,
    )
    try:
        if conversation.channel in ("instagram", "messenger"):
            from .social_delivery import queue_message
            db.add(message)
            queue_message(db, conversation, message)
        elif conversation.channel in ("whatsapp", "whatsapp_cloud"):
            from .whatsapp import send_channel_message
            message.external_message_id = await send_channel_message(db, conversation, text)
            db.add(message)
        else:
            db.add(message)
    except HTTPException as exc:
        if message in db:
            db.expunge(message)
        logger.warning("Follow-up for %s was not delivered (%s)", conversation.id, exc.status_code)
        return None
    conversation.updated_at = now_utc()
    return message


def _requested_at(pending: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(pending.get("requested_at") or "")
    except ValueError:
        return None


def _resolve_pending(db: Session, conversation: Conversation, last: Message | None) -> None:
    pending = conversation.pending_resolution or {}
    requested = _requested_at(pending)
    answered = bool(last and last.role == "user" and (requested is None or last.created_at > requested))
    if not _agent_holds_it(conversation) or answered or not pending.get("event"):
        cancel_follow_up(conversation)
        return
    resolve_without_a_person(
        db, conversation, pending["event"], actor=pending.get("actor"), details=pending.get("details") or None
    )


async def _run_step(db: Session, conversation: Conversation, now: datetime) -> None:
    last = _last_message(db, conversation)
    if conversation.pending_resolution:
        _resolve_pending(db, conversation, last)
        db.commit()
        return
    agent = conversation.agent
    steps = steps_for(agent)
    index = conversation.follow_up_step
    anchor = conversation.follow_up_anchor_at
    blocked = conversation.contact is not None and conversation.contact.blocked_at is not None
    if (not _silent(conversation, last) or anchor is None or index >= len(steps) or blocked
            or not applies_to(agent, conversation) or not agent.is_active or not agent.client.is_active):
        cancel_follow_up(conversation)
        db.commit()
        return
    step = steps[index]
    due = anchor + timedelta(minutes=step.minutes)
    if due > now:
        # The schedule was edited after the clock started.
        conversation.follow_up_due_at = due
        db.commit()
        return
    conversation.follow_up_claimed_until = now + _LEASE
    db.commit()

    completion = None
    if _reachable(db, conversation):
        try:
            completion = await _compose(db, conversation, agent, step)
        except HTTPException:
            completion = None
    db.refresh(conversation)
    latest = _last_message(db, conversation)
    if (conversation.follow_up_anchor_at != anchor or conversation.follow_up_step != index
            or not _silent(conversation, latest) or latest.id != last.id):
        # The contact or a person spoke while the message was being written.
        if completion:
            record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion, conversation=conversation)
        if conversation.follow_up_anchor_at == anchor:
            cancel_follow_up(conversation)
        db.commit()
        return

    # The step counts as taken before anything leaves, so a crash cannot send it twice.
    upcoming = index + 1
    conversation.follow_up_step = upcoming
    conversation.follow_up_claimed_until = None
    conversation.follow_up_due_at = anchor + timedelta(minutes=steps[upcoming].minutes) if upcoming < len(steps) else None
    db.commit()

    text = (completion.text or "").strip() if completion else ""
    message = await _deliver(db, conversation, agent, text) if text else None
    if completion:
        record_usage(
            db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion,
            conversation=conversation, message=message,
        )
    if step.kind == "close":
        details = {"hours": hours_shown(step.minutes)}
        if message is not None and conversation.channel in ("instagram", "messenger"):
            # Queued, not sent yet: the outbox refuses a resolved conversation.
            request_resolution(conversation, "closed_unanswered", details=details)
        else:
            resolve_without_a_person(db, conversation, "closed_unanswered", details=details)
    db.commit()


async def run_due(db: Session, *, limit: int = 20) -> int:
    """Run every follow-up and pending resolution that is due, up to ``limit``."""
    processed = 0
    for _ in range(limit):
        now = now_utc()
        conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.follow_up_due_at <= now,
                or_(Conversation.follow_up_claimed_until.is_(None), Conversation.follow_up_claimed_until <= now),
            )
            .order_by(Conversation.follow_up_due_at)
            .with_for_update(skip_locked=True)
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if not conversation:
            db.rollback()
            break
        conversation_id = conversation.id
        try:
            await _run_step(db, conversation, now)
        except Exception as exc:  # noqa: BLE001 - one conversation must not stop the rest
            db.rollback()
            logger.error("Follow-up failed for %s (%s)", conversation_id, type(exc).__name__)
            # Stop this clock rather than retry: the idle sweep still closes the case.
            stuck = db.get(Conversation, conversation_id)
            if stuck is not None:
                db.refresh(stuck)
                cancel_follow_up(stuck)
                db.commit()
        processed += 1
    return processed
