"""Telegram bots connected to a client, one row per bot."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas_social import TelegramChannelCreate, TelegramChannelOut, TelegramChannelUpdate
from ..services import social_connections, telegram

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.get("/clients/{client_id}/channels", response_model=list[TelegramChannelOut])
def list_channels(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every bot connected to the client, oldest first."""
    return [telegram.public_channel(db, item) for item in telegram.client_channels(db, user, client_id)]


@router.post("/clients/{client_id}/channels", response_model=TelegramChannelOut, status_code=201)
async def connect_channel(client_id: uuid.UUID, payload: TelegramChannelCreate,
                          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Connect a bot with its token. The same bot connected again to this
    client updates its row instead of adding another."""
    channel = await telegram.connect_bot(db, user, client_id, payload.agent_id, payload.token, label=payload.label)
    return telegram.public_channel(db, channel)


@router.get("/channels/{channel_id}", response_model=TelegramChannelOut)
def get_channel(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return telegram.public_channel(db, telegram.owned_channel(db, user, channel_id))


@router.patch("/channels/{channel_id}", response_model=TelegramChannelOut)
async def update_channel(channel_id: uuid.UUID, payload: TelegramChannelUpdate,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = telegram.owned_channel(db, user, channel_id)
    if payload.agent_id is not None:
        social_connections.owned_client(db, user, channel.client_id, payload.agent_id)
    if payload.token:
        channel = await telegram.connect_bot(
            db, user, channel.client_id, payload.agent_id or channel.agent_id, payload.token,
            label=payload.label if "label" in payload.model_fields_set else None, channel=channel)
        return telegram.public_channel(db, channel)
    if payload.agent_id is not None:
        channel.agent_id = payload.agent_id
    if "label" in payload.model_fields_set:
        channel.label = (payload.label or "").strip()[:80] or None
    db.commit()
    db.refresh(channel)
    return telegram.public_channel(db, channel)


@router.post("/channels/{channel_id}/connect", response_model=TelegramChannelOut)
async def reconnect_channel(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Check the stored token and point the bot's webhook here again."""
    channel = await telegram.reconnect(db, user, telegram.owned_channel(db, user, channel_id))
    return telegram.public_channel(db, channel)


@router.post("/channels/{channel_id}/disconnect", status_code=204)
async def disconnect_channel(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Stop the bot's webhook and remove it; its conversations stay as history."""
    await social_connections.disconnect_account(db, telegram.owned_channel(db, user, channel_id))
