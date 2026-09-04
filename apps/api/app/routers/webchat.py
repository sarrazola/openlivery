"""The web chat widget as a channel of the client: one per client, answered
by an agent of that client, embedded with the public id it carries."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, Client, User, WidgetChannel
from ..schemas import WidgetChannelOut, WidgetChannelUpdate

router = APIRouter(prefix="/webchat", tags=["Web chat"])


def _client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/channels/{client_id}", response_model=WidgetChannelOut)
def get_channel(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    channel = db.scalar(select(WidgetChannel).where(WidgetChannel.client_id == client.id))
    if not channel:
        raise HTTPException(status_code=404, detail="This client has no web chat yet")
    return channel


@router.put("/channels/{client_id}", response_model=WidgetChannelOut)
def configure_channel(
    client_id: uuid.UUID,
    payload: WidgetChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create or update the client's web chat. The public id never changes,
    so a snippet embedded on a website survives every edit."""
    client = _client(db, user, client_id)
    agent = db.scalar(
        select(Agent).where(Agent.id == payload.agent_id, Agent.client_id == client.id, Agent.agency_id == user.agency_id)
    )
    if not agent:
        raise HTTPException(status_code=400, detail="Select an agent that belongs to this client")
    channel = db.scalar(select(WidgetChannel).where(WidgetChannel.client_id == client.id))
    if not channel:
        channel = WidgetChannel(agency_id=user.agency_id, client_id=client.id, agent_id=agent.id)
        db.add(channel)
    channel.agent_id = agent.id
    channel.is_enabled = payload.is_enabled
    channel.greeting = payload.greeting.strip()
    channel.color = payload.color.strip()
    channel.position = payload.position
    db.commit()
    db.refresh(channel)
    return channel
