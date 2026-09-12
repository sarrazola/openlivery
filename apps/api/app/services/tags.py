"""Contact tags: the client's catalog, managed from the portal and from the
agency's client page. Routing (where a tag sends new conversations) is the
agency's call and stays in its router; everything else is shared here."""

import re
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import TAG_COLOR_PATTERN, TAG_COLORS, Client, ContactTag, ContactTagLink
from ..schemas import ContactTagOut


def get_tag(db: Session, client: Client, tag_id: uuid.UUID) -> ContactTag:
    tag = db.scalar(select(ContactTag).where(ContactTag.id == tag_id, ContactTag.client_id == client.id))
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def assert_tag_name_free(db: Session, client: Client, name: str, *, except_id: uuid.UUID | None = None) -> None:
    query = select(ContactTag.id).where(ContactTag.client_id == client.id, func.lower(ContactTag.name) == name.lower())
    if except_id:
        query = query.where(ContactTag.id != except_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="A tag with this name already exists")


def tag_color(color: str | None, fallback: str) -> str:
    """A lowercase #rrggbb, or the fallback when none was sent."""
    if color is None:
        return fallback
    value = color.strip().lower()
    if not re.match(TAG_COLOR_PATTERN, value):
        raise HTTPException(status_code=422, detail="Use a hex color like #3b82f6")
    return value


def tag_out(tag: ContactTag, count: int = 0) -> ContactTagOut:
    team = tag.route_team if tag.route_team_id else None
    person = tag.route_assignee if tag.route_assignee_id else None
    return ContactTagOut(
        id=tag.id, name=tag.name, color=tag.color, contact_count=count,
        route_team_id=tag.route_team_id, route_team_name=team.name if team else None,
        route_assignee_id=tag.route_assignee_id, route_assignee_name=(person.name.strip() or person.email) if person else None,
    )


def tag_count(db: Session, tag: ContactTag) -> int:
    return int(db.scalar(select(func.count(ContactTagLink.contact_id)).where(ContactTagLink.tag_id == tag.id)) or 0)


def list_tags(db: Session, client: Client) -> list[ContactTagOut]:
    counts = (
        select(ContactTagLink.tag_id, func.count(ContactTagLink.contact_id).label("n"))
        .group_by(ContactTagLink.tag_id)
        .subquery()
    )
    rows = db.execute(
        select(ContactTag, counts.c.n).outerjoin(counts, counts.c.tag_id == ContactTag.id)
        .where(ContactTag.client_id == client.id)
        .order_by(func.lower(ContactTag.name))
    ).all()
    return [tag_out(tag, int(n or 0)) for tag, n in rows]


def create_tag(db: Session, client: Client, name: str, color: str | None) -> ContactTag:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the tag a name")
    assert_tag_name_free(db, client, name)
    # Without a chosen color, rotate through the palette so neighbours differ.
    existing = db.scalar(select(func.count(ContactTag.id)).where(ContactTag.client_id == client.id)) or 0
    tag = ContactTag(client_id=client.id, name=name, color=tag_color(color, TAG_COLORS[existing % len(TAG_COLORS)]))
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def rename_tag(db: Session, client: Client, tag: ContactTag, name: str | None, color: str | None) -> None:
    """Apply a new name and/or color; the caller commits."""
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Give the tag a name")
        assert_tag_name_free(db, client, name, except_id=tag.id)
        tag.name = name
    if color is not None:
        tag.color = tag_color(color, tag.color)


def delete_tag(db: Session, client: Client, tag_id: uuid.UUID) -> None:
    tag = get_tag(db, client, tag_id)
    db.delete(tag)  # links go with it (ON DELETE CASCADE)
    db.commit()
