"""A summary of a conversation, on request.

Nothing summarizes on its own: a person asks for it from the conversation, so
no tokens are spent on conversations nobody reads that way. The call goes
through the conversation agent's model and provider key, is recorded as usage
like any reply (``purpose="summary"``), and the result is stored on the
conversation for the team. It is never sent to the contact. Asking again
before new messages arrive returns the stored summary without calling the
model.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Conversation, Message, now_utc
from .ai import chat_completion
from .attachments import llm_text
from .conversation_state import exchanged_only
from .providers import resolve_agent_credentials
from .usage import record_usage, schedule_generation_reconcile

# The newest messages the summary reads, and how much of each.
MAX_MESSAGES = 300
MAX_MESSAGE_CHARS = 1500
LANGUAGES = {"es": "Spanish", "en": "English"}

SYSTEM_PROMPT = """You summarize a customer service conversation for the team that handles it. Write {language}.
Return 3 to 6 short bullet lines, each starting with "- ", and nothing else:
- what the customer wants or asked for;
- what was answered or done;
- what is still pending, or the next step, if anything;
- details the customer gave that the team needs (name, order, address, date), if any.
Use only what is in the conversation. Do not invent facts, prices or promises. Keep it under 120 words."""


class SummaryUnavailable(Exception):
    """The summary cannot be written: nothing to summarize, or no model to write it."""


def exchanged_count(db: Session, conversation: Conversation) -> int:
    return db.scalar(
        exchanged_only(select(func.count(Message.id)).where(Message.conversation_id == conversation.id))
    ) or 0


def summary_out(db: Session, conversation: Conversation) -> dict:
    """The stored summary and whether messages arrived after it."""
    count = exchanged_count(db, conversation)
    return {
        "summary": conversation.summary,
        "summary_at": conversation.summary_at,
        "summary_by": conversation.summary_by,
        "message_count": conversation.summary_message_count or 0,
        "current_message_count": count,
        "stale": bool(conversation.summary) and count != (conversation.summary_message_count or 0),
    }


def _transcript(db: Session, conversation: Conversation) -> str:
    rows = db.scalars(
        exchanged_only(select(Message).where(Message.conversation_id == conversation.id))
        .order_by(Message.created_at.desc())
        .limit(MAX_MESSAGES)
    ).all()
    lines = []
    for message in reversed(rows):
        who = "Customer" if message.role == "user" else (message.sender_name or "Agent")
        text = " ".join(llm_text(message).split())[:MAX_MESSAGE_CHARS]
        if text:
            lines.append(f"[{message.created_at:%Y-%m-%d %H:%M}] {who}: {text}")
    return "\n".join(lines)


async def summarize(db: Session, conversation: Conversation, language: str = "es", *, requested_by: str | None = None) -> dict:
    """Write (or return the still-current) summary of the conversation."""
    count = exchanged_count(db, conversation)
    if count == 0:
        raise SummaryUnavailable("There are no messages to summarize yet.")
    if conversation.summary and conversation.summary_message_count == count:
        return summary_out(db, conversation)
    agent = conversation.agent
    credentials = resolve_agent_credentials(db, agent) if agent is not None else None
    if agent is None or not credentials or not (agent.model or "").strip():
        raise SummaryUnavailable("The conversation's agent has no model or AI provider key to write the summary.")
    base_url, api_key = credentials
    model = agent.model.strip()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(language=f"in {LANGUAGES.get(language, 'Spanish')}")},
        {"role": "user", "content": _transcript(db, conversation)},
    ]
    started = time.perf_counter()
    completion = await chat_completion(agent.provider, base_url, api_key, model, messages, temperature=0.2, max_tokens=800)
    completion.duration_ms = int((time.perf_counter() - started) * 1000)
    record = record_usage(db, agent.agency_id, agent.id, agent.provider, model, completion, conversation=conversation, purpose="summary")
    text = (completion.text or "").strip()
    if not text:
        db.commit()
        raise SummaryUnavailable("The model returned an empty summary. Try again.")
    # Written past the ORM so ``updated_at`` keeps its value: a summary is not
    # activity, and the inbox must not move the conversation to the top.
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(summary=text, summary_at=now_utc(), summary_message_count=count, summary_by=(requested_by or None) and requested_by[:160],
                updated_at=Conversation.updated_at)
    )
    db.commit()
    db.refresh(conversation)
    schedule_generation_reconcile(record, completion, base_url, api_key)
    return summary_out(db, conversation)
