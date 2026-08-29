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


def _channel_for_user(db: Session, user: User, client_id: uuid.UUID) -> WhatsAppCloudChannel:
    channel = db.scalar(
        select(WhatsAppCloudChannel).where(
            WhatsAppCloudChannel.client_id == client_id,
            WhatsAppCloudChannel.agency_id == user.agency_id,
        )
    )
    if not channel:
        raise HTTPException(status_code=404, detail="This client does not have the WhatsApp API configured yet")
    return channel


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
        "phone_number_id": channel.phone_number_id,
        "waba_id": channel.waba_id,
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


@router.get("/channels/{client_id}", response_model=WhatsAppCloudChannelOut)
def get_channel(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _public_channel(_channel_for_user(db, user, client_id))


@router.put("/channels/{client_id}", response_model=WhatsAppCloudChannelOut)
def configure_channel(
    client_id: uuid.UUID,
    payload: WhatsAppCloudChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    agent = db.scalar(
        select(Agent).where(
            Agent.id == payload.agent_id,
            Agent.client_id == client.id,
            Agent.agency_id == user.agency_id,
        )
    )
    if not agent:
        raise HTTPException(status_code=400, detail="Select an agent that belongs to this client")
    # One number answers for one client. Saving the same one twice would give
    # two agents the same inbox, and each channel's webhook would accept the
    # other's traffic.
    number = (payload.phone_number_id or "").strip()
    if number and db.scalar(
        select(WhatsAppCloudChannel).where(
            WhatsAppCloudChannel.agency_id == user.agency_id,
            WhatsAppCloudChannel.phone_number_id == number,
            WhatsAppCloudChannel.client_id != client.id,
        )
    ):
        raise HTTPException(
            status_code=400, detail="That phone number is already connected to another client"
        )
    channel = db.scalar(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.client_id == client.id))
    if not channel:
        channel = WhatsAppCloudChannel(
            agency_id=user.agency_id,
            client_id=client.id,
            agent_id=agent.id,
            webhook_verify_token=new_public_id(),
        )
        db.add(channel)
    channel.agent_id = agent.id
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
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.post("/channels/{client_id}/connect", response_model=WhatsAppCloudChannelOut)
async def connect_channel(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, client_id)
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


@router.post("/channels/{client_id}/disconnect", response_model=WhatsAppCloudChannelOut)
def disconnect_channel(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, client_id)
    channel.status = "disconnected"
    channel.is_enabled = False
    channel.last_error = None
    channel.updated_at = now_utc()
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)
