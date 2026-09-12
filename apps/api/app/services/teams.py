"""Teams: the trays a client's conversations are routed to.

Shared by the client portal and the agency's client page, which manage the
same rows from two doors. Both routers resolve the client their own way and
hand it here.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Client, Conversation, PortalUser, Team, TeamMember, now_utc
from ..schemas import TeamUpsert

TEAM_CHANNELS = {"whatsapp", "whatsapp_cloud", "widget", "instagram", "messenger"}


def get_team(db: Session, client: Client, team_id: uuid.UUID) -> Team:
    team = db.scalar(select(Team).where(Team.id == team_id, Team.client_id == client.id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def list_teams(db: Session, client: Client) -> list[Team]:
    return db.scalars(select(Team).where(Team.client_id == client.id).order_by(Team.name)).all()


def team_out(db: Session, team: Team) -> dict:
    open_count, unassigned_count = db.execute(
        select(
            func.count(Conversation.id),
            func.count(Conversation.id).filter(Conversation.assignee_id.is_(None)),
        ).where(Conversation.team_id == team.id, Conversation.status == "open")
    ).one()
    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "strategy": team.strategy,
        "channels": list(team.channels or []),
        "is_default": team.is_default,
        "members": [
            {
                "id": member.portal_user.id,
                "name": member.portal_user.name.strip() or member.portal_user.email,
                "email": member.portal_user.email,
                "availability": member.portal_user.availability,
            }
            for member in team.members
            if member.portal_user
        ],
        "open_count": int(open_count),
        "unassigned_count": int(unassigned_count),
    }


def _apply_payload(db: Session, client: Client, team: Team, payload: TeamUpsert) -> None:
    if set(payload.channels) - TEAM_CHANNELS:
        raise HTTPException(status_code=422, detail="Unknown channel for a team")
    duplicate = db.scalar(
        select(Team.id).where(Team.client_id == client.id, Team.name == payload.name.strip(), Team.id != team.id)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    team.name = payload.name.strip()
    team.description = payload.description.strip()
    team.strategy = payload.strategy
    team.channels = sorted(set(payload.channels))
    if payload.is_default and not team.is_default:
        for other in db.scalars(select(Team).where(Team.client_id == client.id, Team.is_default.is_(True))):
            other.is_default = False
    team.is_default = payload.is_default
    team.updated_at = now_utc()

    wanted = set(payload.member_ids)
    if wanted:
        users = db.scalars(
            select(PortalUser).where(PortalUser.client_id == client.id, PortalUser.id.in_(wanted))
        ).all()
        if len(users) != len(wanted):
            raise HTTPException(status_code=422, detail="Every member must be a portal user of this client")
    existing = {member.portal_user_id: member for member in team.members}
    for portal_user_id, member in existing.items():
        if portal_user_id not in wanted:
            db.delete(member)
    for portal_user_id in wanted - set(existing):
        db.add(TeamMember(team_id=team.id, portal_user_id=portal_user_id))


def create_team(db: Session, client: Client, payload: TeamUpsert) -> Team:
    # Checked before the row exists so a duplicate is a clean 409, not a
    # constraint blowup at flush time.
    if db.scalar(select(Team.id).where(Team.client_id == client.id, Team.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    team = Team(client_id=client.id, name=payload.name.strip())
    db.add(team)
    db.flush()
    _apply_payload(db, client, team, payload)
    db.commit()
    db.refresh(team)
    return team


def update_team(db: Session, client: Client, team_id: uuid.UUID, payload: TeamUpsert) -> Team:
    team = get_team(db, client, team_id)
    _apply_payload(db, client, team, payload)
    db.commit()
    db.refresh(team)
    return team


def delete_team(db: Session, client: Client, team_id: uuid.UUID) -> None:
    # Conversations keep living; the FK sets their tray to NULL.
    team = get_team(db, client, team_id)
    db.delete(team)
    db.commit()


def members_out(db: Session, client: Client) -> list[dict]:
    """The people a conversation can be handed to, and a team can hold."""
    rows = db.scalars(
        select(PortalUser).where(PortalUser.client_id == client.id, PortalUser.is_active.is_(True)).order_by(PortalUser.name, PortalUser.email)
    ).all()
    return [{"id": row.id, "name": row.name.strip() or row.email, "email": row.email, "availability": row.availability} for row in rows]
