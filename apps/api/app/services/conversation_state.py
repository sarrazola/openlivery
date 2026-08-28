"""Conversation lifecycle: status changes, reply timing and the activity
events that narrate them inside the thread.

``mode`` (who answers) and ``status`` (where the case stands) are kept apart
on purpose: resolving does not hand the conversation back to the AI, and
taking control does not reopen a resolved case. What links them is the
activity trail, so a person reading the thread sees both.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Conversation, Message, PortalUser, now_utc


STATUSES = ("open", "resolved")

# English fallbacks for clients that do not translate events themselves.
_ACTIVITY_TEXT = {
    "resolved": "{actor} resolved the conversation",
    "reopened": "{actor} reopened the conversation",
    "reopened_by_contact": "Reopened: the contact wrote again",
    "taken_over": "{actor} took over the conversation",
    "returned_to_ai": "{actor} returned the conversation to the AI",
    "auto_resolved": "Resolved automatically after {hours} h without activity",
    "self_assigned": "{actor} is now handling the conversation",
    "assigned": "{actor} assigned the conversation to {assignee}",
    "transferred": "{actor} transferred the conversation to {assignee}",
    "unassigned": "{actor} released the conversation",
}


def record_activity(
    db: Session, conversation: Conversation, event: str, *, actor: str | None = None, details: dict | None = None
) -> Message:
    """Append an activity event to the thread. Never sent out, never fed to the model."""
    text = _ACTIVITY_TEXT[event].format(actor=actor or "Someone", **(details or {}))
    message = Message(
        conversation_id=conversation.id,
        role="system",
        kind="activity",
        activity={"event": event, **(details or {})},
        content=text,
        sender_type="system",
        sender_name=actor,
    )
    db.add(message)
    conversation.updated_at = now_utc()
    return message


def set_status(db: Session, conversation: Conversation, status: str, *, actor: str | None = None) -> bool:
    """Move the conversation to ``status`` if it is not there already.

    Returns whether anything changed, so callers can skip a commit and avoid
    a duplicate activity line when a button is pressed twice.
    """
    if status not in STATUSES:
        raise ValueError(f"Unknown conversation status: {status}")
    if conversation.status == status:
        return False
    now = now_utc()
    conversation.status = status
    conversation.status_changed_at = now
    if status == "resolved":
        conversation.resolved_at = now
        conversation.waiting_since = None
        record_activity(db, conversation, "resolved", actor=actor)
    else:
        conversation.resolved_at = None
        record_activity(db, conversation, "reopened", actor=actor)
    return True


def set_mode(
    db: Session, conversation: Conversation, mode: str, *, actor: str | None = None, user: PortalUser | None = None
) -> bool:
    """Switch who answers, and leave a trace of it in the thread.

    Taking over from the portal also hands the conversation to that person;
    giving it back to the AI releases it, since nobody is handling it now.
    """
    if conversation.mode == mode:
        return False
    conversation.mode = mode
    now = now_utc()
    if mode == "human":
        conversation.taken_over_at = now
        if user:
            conversation.assignee_id = user.id
            conversation.assigned_at = now
    else:
        conversation.assignee_id = None
        conversation.assigned_at = None
    record_activity(db, conversation, "taken_over" if mode == "human" else "returned_to_ai", actor=actor)
    return True


def assign(
    db: Session,
    conversation: Conversation,
    assignee: PortalUser | None,
    *,
    actor: str | None = None,
    actor_user: PortalUser | None = None,
) -> bool:
    """Hand the conversation to ``assignee`` (None releases it).

    Assigning a person means a person answers, so the AI steps aside. The
    thread says what happened in the words people use: took it, assigned
    it, transferred it, released it.
    """
    new_id = assignee.id if assignee else None
    if conversation.assignee_id == new_id and (assignee is None or conversation.mode == "human"):
        return False
    previous = conversation.assignee
    now = now_utc()
    conversation.assignee_id = new_id
    conversation.assigned_at = now if assignee else None
    if assignee and conversation.mode != "human":
        conversation.mode = "human"
        conversation.taken_over_at = now
    if assignee is None:
        event, details = "unassigned", None
    elif actor_user and assignee.id == actor_user.id:
        event, details = "self_assigned", {"assignee": assignee.name}
    elif previous and previous.id != assignee.id:
        event, details = "transferred", {"assignee": assignee.name, "from": previous.name}
    else:
        event, details = "assigned", {"assignee": assignee.name}
    record_activity(db, conversation, event, actor=actor, details=details)
    return True


def note_inbound(db: Session, conversation: Conversation) -> None:
    """A contact wrote: they are waiting, and a resolved case is open again."""
    now = now_utc()
    if conversation.waiting_since is None:
        conversation.waiting_since = now
    if conversation.status == "resolved":
        conversation.status = "open"
        conversation.status_changed_at = now
        conversation.resolved_at = None
        record_activity(db, conversation, "reopened_by_contact")


def note_reply(conversation: Conversation) -> None:
    """Something answered the contact, whether the AI or a person."""
    now = now_utc()
    if conversation.first_reply_at is None:
        conversation.first_reply_at = now
    conversation.waiting_since = None


def resolve_idle_ai_conversations(db: Session, *, hours: float, now: datetime | None = None) -> int:
    """Resolve open AI-handled conversations idle for ``hours``.

    Idle means no exchanged message from either side, so a case the AI
    answered and the contact never followed up on leaves the open list on
    its own. Human-held conversations are left alone on purpose: the person
    who took them over is the only one who closes them.
    """
    if hours <= 0:
        return 0
    cutoff = (now or now_utc()) - timedelta(hours=hours)
    last_message_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id, Message.kind == "message")
        .correlate(Conversation)
        .scalar_subquery()
    )
    idle = db.scalars(
        select(Conversation).where(
            Conversation.status == "open",
            Conversation.mode == "ai",
            func.coalesce(last_message_at, Conversation.created_at) < cutoff,
        )
    ).all()
    shown = int(hours) if float(hours).is_integer() else hours
    for conversation in idle:
        stamp = now_utc()
        conversation.status = "resolved"
        conversation.status_changed_at = stamp
        conversation.resolved_at = stamp
        conversation.waiting_since = None
        record_activity(db, conversation, "auto_resolved", details={"hours": shown})
    if idle:
        db.commit()
    return len(idle)


def exchanged_only(query):
    """Restrict a Message query to what was exchanged with the contact."""
    return query.where(Message.kind == "message")
