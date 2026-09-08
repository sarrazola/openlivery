"""Process durable channel work with an overridable database scope runner."""
import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import or_, select

from ..config import get_settings
from ..database import new_session
from ..models import Conversation, EscalationRule, Message, SocialOutbox, now_utc
from .social_policy import require_reply

logger = logging.getLogger(__name__)
_task = None
_scope_runner = None


def install_scope_runner(runner) -> None:
    global _scope_runner
    _scope_runner = runner


async def hand_over_failed_reply(db, conversation, reason: str) -> None:
    """A failed model call needs a person, not a replay of tool side effects."""
    from .escalation import EscalationRequest, apply_escalation
    db.refresh(conversation)
    conversation.social_reply_due_at = None
    conversation.social_reply_claimed_until = None
    if conversation.status == "resolved" or conversation.mode == "human":
        db.commit()
        return
    await apply_escalation(db, conversation, conversation.agent,
                          EscalationRequest(reason=reason, trigger="cannot_solve"))


async def complete_escalations(db, *, limit: int = 25) -> int:
    """Deliver the AI farewell before changing the thread to human mode."""
    from .escalation import EscalationRequest, apply_escalation
    ids = db.scalars(select(Conversation.id).where(
        Conversation.social_pending_escalation.is_not(None),
    ).limit(limit)).all()
    completed = 0
    for conversation_id in ids:
        conversation = db.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.social_pending_escalation.is_not(None),
        ).with_for_update(skip_locked=True).execution_options(populate_existing=True))
        if not conversation:
            continue
        pending = conversation.social_pending_escalation
        if not pending:
            continue
        message_id = pending.get("message_id")
        if message_id and db.scalar(select(SocialOutbox.id).where(
            SocialOutbox.message_id == uuid.UUID(message_id),
            SocialOutbox.status.in_(("pending", "sending")),
        ).limit(1)):
            db.rollback()
            continue
        conversation.social_pending_escalation = None
        conversation.social_reply_due_at = None
        if conversation.mode == "human" or conversation.status == "resolved":
            db.commit()
            continue
        rule = db.get(EscalationRule, uuid.UUID(pending["rule_id"])) if pending.get("rule_id") else None
        if rule and (rule.agent_id != conversation.agent_id or not rule.is_active):
            rule = None
        await apply_escalation(db, conversation, conversation.agent, EscalationRequest(
            reason=pending.get("reason", ""), trigger=pending.get("trigger"), rule=rule))
        completed += 1
    db.commit()
    return completed


async def process_replies(db, *, limit: int = 10) -> int:
    from .whatsapp_inbound import _reply_with_ai
    processed = 0
    for _ in range(limit):
        now = now_utc()
        conversation = db.scalar(select(Conversation).where(
            Conversation.social_reply_due_at <= now,
            Conversation.social_pending_escalation.is_(None),
            or_(Conversation.social_reply_claimed_until.is_(None), Conversation.social_reply_claimed_until < now),
        ).order_by(Conversation.social_reply_due_at).with_for_update(skip_locked=True).limit(1))
        if not conversation:
            db.rollback()
            break
        last = db.scalar(select(Message).where(Message.conversation_id == conversation.id,
            Message.kind == "message", Message.is_historical.is_(False)).order_by(Message.created_at.desc()).limit(1))
        try:
            require_reply(conversation, human=False)
            ready = last and last.role == "user" and conversation.social_channel
        except Exception:
            ready = False
        if not ready:
            conversation.social_reply_due_at = None
            conversation.social_reply_claimed_until = None
            db.commit()
            continue
        trigger_id = last.id
        channel = conversation.social_channel
        conversation.social_reply_claimed_until = now + timedelta(minutes=5)
        db.commit()
        try:
            await _reply_with_ai(db, channel, conversation, last.llm_content or last.content,
                                 expected_last_message_id=trigger_id)
            db.refresh(conversation)
            latest_user = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
                Message.kind == "message", Message.role == "user").order_by(Message.created_at.desc()).limit(1))
            if latest_user == trigger_id:
                conversation.social_reply_due_at = None
            conversation.social_reply_claimed_until = None
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Social reply processing failed for %s (%s)", conversation.id, type(exc).__name__)
            await hand_over_failed_reply(db, conversation,
                "The agent could not complete its reply. A person must continue this conversation.")
        processed += 1
    return processed


async def run_scope(db) -> None:
    from .social_connections import refresh_due_channels
    from .social_delivery import process_outbox
    from .social_inbound import process_pending
    from .social_history import process_history_jobs
    await process_pending(db)
    await process_replies(db)
    await process_outbox(db)
    await complete_escalations(db)
    await refresh_due_channels(db)
    await process_history_jobs(db)


async def run_once() -> None:
    if _scope_runner:
        await _scope_runner(run_scope)
    else:
        with new_session() as db:
            await run_scope(db)


async def _loop() -> None:
    while True:
        await asyncio.sleep(max(0.5, get_settings().social_worker_interval_seconds))
        try:
            await run_once()
        except Exception as exc:
            logger.error("Social worker iteration failed (%s)", type(exc).__name__)


def start_worker() -> None:
    global _task
    if get_settings().social_worker_enabled and (_task is None or _task.done()):
        from . import whatsapp_coexistence
        whatsapp_coexistence.start_worker()
        _task = asyncio.create_task(_loop())


async def stop_worker() -> None:
    global _task
    from . import whatsapp_coexistence
    await whatsapp_coexistence.stop_worker()
    task, _task = _task, None
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
