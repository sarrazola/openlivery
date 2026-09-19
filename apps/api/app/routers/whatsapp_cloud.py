import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, Client, User, WhatsAppCloudChannel, new_public_id, now_utc
from ..schemas_whatsapp_cloud import WhatsAppCloudChannelOut, WhatsAppCloudChannelUpdate
from ..security import decrypt_secret, encrypt_secret
from ..services.whatsapp_cloud import verify_phone_number


router = APIRouter(prefix="/whatsapp-cloud", tags=["WhatsApp Cloud"])


def _channel_for_user(db: Session, user: User, ref: uuid.UUID) -> WhatsAppCloudChannel:
    """``ref`` is a channel id, or a client id for that client's first number
    (the shape these routes had while a client could only have one)."""
    channel = db.scalar(
        select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == ref, WhatsAppCloudChannel.agency_id == user.agency_id)
    )
    if channel:
        return channel
    channel = db.scalar(
        select(WhatsAppCloudChannel)
        .where(WhatsAppCloudChannel.client_id == ref, WhatsAppCloudChannel.agency_id == user.agency_id)
        .order_by(WhatsAppCloudChannel.created_at)
        .limit(1)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="This client does not have the WhatsApp API configured yet")
    return channel


def _owned_client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _client_agent(db: Session, user: User, client_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    agent = db.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.client_id == client_id,
            Agent.agency_id == user.agency_id,
            Agent.deleted_at.is_(None),
        )
    )
    if not agent:
        raise HTTPException(status_code=400, detail="Select an agent that belongs to this client")
    return agent


def _public_channel(channel: WhatsAppCloudChannel) -> dict:
    webhook_url = (
        f"{get_settings().frontend_url.rstrip('/')}/api/public/whatsapp-cloud/channels/{channel.id}/webhook"
    )
    return {
        "id": channel.id,
        "client_id": channel.client_id,
        "agent_id": channel.agent_id,
        "status": channel.status,
        "phone_number": channel.phone_number,
        "display_name": channel.display_name,
        "label": channel.label,
        "phone_number_id": channel.phone_number_id,
        "waba_id": channel.waba_id,
        "coexistence": channel.coexistence,
        "coexistence_sync": channel.coexistence_sync,
        "quality_rating": channel.quality_rating,
        "messaging_limit": channel.messaging_limit,
        "has_access_token": bool(channel.encrypted_access_token),
        "has_app_secret": bool(channel.encrypted_app_secret),
        "webhook_url": webhook_url,
        "webhook_verify_token": channel.webhook_verify_token,
        "last_error": channel.last_error,
        "is_enabled": channel.is_enabled,
        "last_connected_at": channel.last_connected_at,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }


@router.get("/clients/{client_id}/channels", response_model=list[WhatsAppCloudChannelOut])
def list_channels(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every WhatsApp API number of the client, oldest first."""
    client = _owned_client(db, user, client_id)
    rows = db.scalars(
        select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.client_id == client.id).order_by(WhatsAppCloudChannel.created_at)
    ).all()
    return [_public_channel(item) for item in rows]


def _apply_update(db: Session, user: User, channel: WhatsAppCloudChannel, payload: WhatsAppCloudChannelUpdate) -> None:
    agent = _client_agent(db, user, channel.client_id, payload.agent_id)
    # One number answers on one line. Saving the same one twice would give two
    # agents the same inbox, and each channel's webhook would accept the
    # other's traffic.
    number = (payload.phone_number_id or "").strip()
    if number and db.scalar(
        select(WhatsAppCloudChannel.id).where(
            WhatsAppCloudChannel.agency_id == user.agency_id,
            WhatsAppCloudChannel.phone_number_id == number,
            WhatsAppCloudChannel.id != channel.id,
        )
    ):
        raise HTTPException(status_code=400, detail="That phone number is already connected to another line")
    if channel.coexistence and (
        payload.phone_number_id is not None or payload.waba_id is not None
        or payload.access_token or payload.app_secret
    ):
        raise HTTPException(status_code=409, detail="Use the WhatsApp Business app connection flow to change this number or its authorization.")
    channel.agent_id = agent.id
    if "label" in payload.model_fields_set:
        channel.label = (payload.label or "").strip()[:80] or None
    if not channel.coexistence:
        channel.is_enabled = True
    if payload.phone_number_id is not None:
        channel.phone_number_id = number
    if payload.waba_id is not None:
        channel.waba_id = payload.waba_id.strip() or None
    # Blank secrets keep the stored values, so the form can resubmit safely.
    if payload.access_token:
        channel.encrypted_access_token = encrypt_secret(payload.access_token.strip())
    if payload.app_secret:
        channel.encrypted_app_secret = encrypt_secret(payload.app_secret.strip())
    channel.updated_at = now_utc()


@router.post("/clients/{client_id}/channels", response_model=WhatsAppCloudChannelOut, status_code=201)
def create_channel(
    client_id: uuid.UUID,
    payload: WhatsAppCloudChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add another WhatsApp API number to the client."""
    client = _owned_client(db, user, client_id)
    channel = WhatsAppCloudChannel(
        agency_id=user.agency_id, client_id=client.id, agent_id=payload.agent_id, webhook_verify_token=new_public_id()
    )
    _apply_update(db, user, channel, payload)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.get("/channels/{ref}", response_model=WhatsAppCloudChannelOut)
def get_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _public_channel(_channel_for_user(db, user, ref))


@router.post("/channels/{ref}/refresh", response_model=WhatsAppCloudChannelOut)
async def refresh_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.whatsapp_coexistence import refresh_connection

    channel = _channel_for_user(db, user, ref)
    await refresh_connection(db, channel)
    db.refresh(channel)
    return _public_channel(channel)


@router.put("/channels/{ref}", response_model=WhatsAppCloudChannelOut)
def configure_channel(
    ref: uuid.UUID,
    payload: WhatsAppCloudChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save a number's agent, name and credentials. Called with a client id it
    configures that client's first number, creating it when there is none."""
    channel = db.scalar(
        select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == ref, WhatsAppCloudChannel.agency_id == user.agency_id)
    )
    if not channel:
        client = _owned_client(db, user, ref)
        channel = db.scalar(
            select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.client_id == client.id)
            .order_by(WhatsAppCloudChannel.created_at).limit(1)
        )
        if not channel:
            channel = WhatsAppCloudChannel(
                agency_id=user.agency_id, client_id=client.id, agent_id=payload.agent_id, webhook_verify_token=new_public_id()
            )
            db.add(channel)
    _apply_update(db, user, channel, payload)
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.delete("/channels/{channel_id}", status_code=204)
def remove_channel(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Remove a number. Its conversations stay as history."""
    channel = db.scalar(
        select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == channel_id, WhatsAppCloudChannel.agency_id == user.agency_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Number not found")
    if channel.coexistence and channel.is_enabled and channel.status == "connected":
        raise HTTPException(status_code=409, detail="Disconnect this number in WhatsApp Business first: Settings > Account > Business Platform > Disconnect account.")
    db.delete(channel)
    db.commit()


@router.post("/channels/{ref}/connect", response_model=WhatsAppCloudChannelOut)
async def connect_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, ref)
    if not channel.encrypted_access_token or not channel.encrypted_app_secret or not channel.phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Save the phone number ID, access token and app secret before connecting",
        )
    try:
        profile = await verify_phone_number(
            decrypt_secret(channel.encrypted_access_token), channel.phone_number_id
        )
    except HTTPException as exc:
        channel.status = "error"
        channel.last_error = str(exc.detail)
        channel.updated_at = now_utc()
        db.commit()
        db.refresh(channel)
        return _public_channel(channel)
    channel.status = "connected"
    channel.phone_number = profile.get("display_phone_number")
    channel.display_name = profile.get("verified_name")
    channel.last_error = None
    channel.is_enabled = True
    channel.last_connected_at = now_utc()
    channel.updated_at = now_utc()
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.post("/channels/{ref}/disconnect", response_model=WhatsAppCloudChannelOut)
def disconnect_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, ref)
    if channel.coexistence:
        raise HTTPException(status_code=409, detail="Disconnect this number in WhatsApp Business: Settings > Account > Business Platform > Disconnect account.")
    channel.status = "disconnected"
    channel.is_enabled = False
    channel.last_error = None
    channel.updated_at = now_utc()
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)
