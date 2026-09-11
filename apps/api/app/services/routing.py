"""Who gets the next conversation in a team.

Routing is deliberately decoupled from escalation: anything that leaves an
open, human-mode conversation unassigned inside a team - the AI escalating, a
person moving it between trays, an assignee releasing it - can call
``route_conversation`` and the team's strategy picks a member.

Eligibility is the member's own word: active and toggled ``online`` in the
portal. No presence heuristics; a small team knows who is in. When nobody is
eligible the conversation stays in the tray unassigned and the caller decides
how loudly to say so.

``round_robin`` hands it to the eligible member who has waited longest since
their last assignment (never-assigned first), so members who were away are
skipped without losing their turn. ``least_busy`` hands it to whoever holds
the fewest open human conversations, using the rotation clock as tie-break.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Contact, ContactTag, Conversation, PortalUser, Team, TeamMember, now_utc
from .conversation_state import assign, record_activity, set_team

_NEVER = datetime.min.replace(tzinfo=timezone.utc)


def _eligible(team: Team) -> list[TeamMember]:
    return [
        member
        for member in team.members
        if member.portal_user and member.portal_user.is_active and member.portal_user.availability == "online"
    ]


def _open_counts(db: Session, member_ids: list) -> dict:
    rows = db.execute(
        select(Conversation.assignee_id, func.count(Conversation.id))
        .where(
            Conversation.assignee_id.in_(member_ids),
            Conversation.status == "open",
            Conversation.mode == "human",
        )
        .group_by(Conversation.assignee_id)
    ).all()
    return {assignee_id: count for assignee_id, count in rows}


def pick_member(db: Session, team: Team) -> TeamMember | None:
    """The member the team's strategy would hand the next conversation to."""
    members = _eligible(team)
    if not members:
        return None
    if team.strategy == "least_busy":
        counts = _open_counts(db, [member.portal_user_id for member in members])
        return min(
            members,
            key=lambda member: (counts.get(member.portal_user_id, 0), member.last_assigned_at or _NEVER),
        )
    return min(members, key=lambda member: member.last_assigned_at or _NEVER)


def route_conversation(db: Session, conversation: Conversation, *, actor: str) -> PortalUser | None:
    """Assign the conversation to a member of its team, if one is eligible.

    Only acts on open, human-mode, unassigned conversations that sit in a
    team; anything else returns None without touching the row.
    """
    team = conversation.team
    if (
        team is None
        or conversation.assignee_id is not None
        or conversation.mode != "human"
        or conversation.status == "resolved"
    ):
        return None
    member = pick_member(db, team)
    if member is None:
        return None
    member.last_assigned_at = now_utc()
    assign(db, conversation, member.portal_user, actor=actor)
    return member.portal_user


def route_new_conversation_by_tags(db: Session, conversation: Conversation, contact: Contact | None) -> Team | None:
    """Hand a brand-new conversation to a team when the contact carries a
    routed tag. Runs before any AI reply and ahead of the agent's escalation
    rules; nothing happens for contacts without a routed tag. When several of
    the contact's tags route somewhere, the oldest tag wins so the outcome is
    stable. Returns the team, or None when the conversation was left alone."""
    if contact is None or conversation.mode == "human":
        return None
    routed = [tag for tag in contact.tags if tag.route_team_id or tag.route_assignee_id]
    if not routed:
        return None
    tag = min(routed, key=lambda item: (item.created_at, item.name))
    team = db.get(Team, tag.route_team_id) if tag.route_team_id else None
    person = db.get(PortalUser, tag.route_assignee_id) if tag.route_assignee_id else None
    if team is not None and team.client_id != conversation.client_id:
        team = None
    if person is not None and person.client_id != conversation.client_id:
        person = None
    if team is None and person is None:
        return None
    conversation.mode = "human"
    conversation.taken_over_at = now_utc()
    actor = f"Tag {tag.name}"
    target = person.name if person else team.name  # type: ignore[union-attr]
    record_activity(db, conversation, "routed_by_tag", actor=actor, details={"target": target, "tag": tag.name})
    if person is not None:
        assign(db, conversation, person, actor=actor)
        return None
    set_team(db, conversation, team, actor=actor)
    route_conversation(db, conversation, actor=actor)
    return team
