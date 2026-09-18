import base64
import binascii
import hmac
import json
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, Client, Conversation, Message, User, WhatsAppChannel, now_utc
from ..schemas import (
    WhatsAppChannelOut,
    WhatsAppChannelUpdate,
    WhatsAppInbound,
    WhatsAppInboundReaction,
    WhatsAppInboundResult,
    WhatsAppInternalAuth,
    WhatsAppInternalStatus,
    WhatsAppOutboundConfirm,
    WhatsAppOutgoing,
)
from ..security import decrypt_secret, encrypt_secret
from ..services.whatsapp import bridge_command
from ..services.whatsapp_inbound import InboundMessage, process_inbound, send_reply_attachments


router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
internal_router = APIRouter(prefix="/internal/whatsapp", tags=["WhatsApp internal"])


def _channel_for_user(db: Session, user: User, ref: uuid.UUID) -> WhatsAppChannel:
    """``ref`` is a line id, or a client id for that client's first line (the
    shape these routes had while a client could only have one)."""
    channel = db.scalar(select(WhatsAppChannel).where(WhatsAppChannel.id == ref, WhatsAppChannel.agency_id == user.agency_id))
    if channel:
        return channel
    channel = db.scalar(
        select(WhatsAppChannel)
        .where(WhatsAppChannel.client_id == ref, WhatsAppChannel.agency_id == user.agency_id)
        .order_by(WhatsAppChannel.created_at)
        .limit(1)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="This client does not have WhatsApp configured yet")
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


def _apply_label(channel: WhatsAppChannel, payload: WhatsAppChannelUpdate) -> None:
    if "label" in payload.model_fields_set:
        channel.label = (payload.label or "").strip()[:80] or None


def _public_channel(channel: WhatsAppChannel) -> dict:
    qr_code = decrypt_secret(channel.encrypted_qr) if channel.encrypted_qr else None
    return {
        "id": channel.id,
        "client_id": channel.client_id,
        "agent_id": channel.agent_id,
        "status": channel.status,
        "phone_number": channel.phone_number,
        "display_name": channel.display_name,
        "label": channel.label,
        "qr_code": qr_code,
        "last_error": channel.last_error,
        "is_enabled": channel.is_enabled,
        "has_session": bool(channel.encrypted_auth_state),
        "last_connected_at": channel.last_connected_at,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }


def _require_bridge(x_bridge_token: str | None = Header(default=None)) -> None:
    expected = get_settings().whatsapp_bridge_token
    if not x_bridge_token or not hmac.compare_digest(x_bridge_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal token")


def _internal_channel(db: Session, channel_id: uuid.UUID) -> WhatsAppChannel:
    channel = db.scalar(
        select(WhatsAppChannel)
        .options(joinedload(WhatsAppChannel.agent).joinedload(Agent.client))
        .where(WhatsAppChannel.id == channel_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.get("/clients/{client_id}/channels", response_model=list[WhatsAppChannelOut])
def list_channels(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every QR line of the client, oldest first."""
    client = _owned_client(db, user, client_id)
    rows = db.scalars(
        select(WhatsAppChannel).where(WhatsAppChannel.client_id == client.id).order_by(WhatsAppChannel.created_at)
    ).all()
    return [_public_channel(item) for item in rows]


@router.post("/clients/{client_id}/channels", response_model=WhatsAppChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(
    client_id: uuid.UUID,
    payload: WhatsAppChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add another line to the client. It is linked afterwards by scanning its QR."""
    client = _owned_client(db, user, client_id)
    agent = _client_agent(db, user, client.id, payload.agent_id)
    channel = WhatsAppChannel(agency_id=user.agency_id, client_id=client.id, agent_id=agent.id)
    _apply_label(channel, payload)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.get("/channels/{ref}", response_model=WhatsAppChannelOut)
def get_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _public_channel(_channel_for_user(db, user, ref))


@router.put("/channels/{ref}", response_model=WhatsAppChannelOut)
def configure_channel(
    ref: uuid.UUID,
    payload: WhatsAppChannelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change the agent or the name of a line. Called with a client id it
    configures that client's first line, creating it when there is none."""
    channel = db.scalar(select(WhatsAppChannel).where(WhatsAppChannel.id == ref, WhatsAppChannel.agency_id == user.agency_id))
    if not channel:
        client = _owned_client(db, user, ref)
        channel = db.scalar(
            select(WhatsAppChannel).where(WhatsAppChannel.client_id == client.id).order_by(WhatsAppChannel.created_at).limit(1)
        )
        if not channel:
            agent = _client_agent(db, user, client.id, payload.agent_id)
            channel = WhatsAppChannel(agency_id=user.agency_id, client_id=client.id, agent_id=agent.id)
            db.add(channel)
    agent = _client_agent(db, user, channel.client_id, payload.agent_id)
    channel.agent_id = agent.id
    channel.is_enabled = True
    _apply_label(channel, payload)
    db.commit()
    db.refresh(channel)
    return _public_channel(channel)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Remove a line. The phone is logged out first (best effort) and the
    line's conversations stay as history."""
    channel = db.scalar(select(WhatsAppChannel).where(WhatsAppChannel.id == channel_id, WhatsAppChannel.agency_id == user.agency_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Line not found")
    if channel.encrypted_auth_state:
        try:
            await bridge_command("POST", f"/channels/{channel.id}/disconnect")
        except HTTPException:
            pass
    db.delete(channel)
    db.commit()


@router.post("/channels/{ref}/connect", response_model=WhatsAppChannelOut)
async def connect_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, ref)
    channel.status = "connecting"
    channel.last_error = None
    channel.is_enabled = True
    db.commit()
    try:
        await bridge_command("POST", f"/channels/{channel.id}/connect")
    except HTTPException as exc:
        channel.status = "error"
        channel.last_error = exc.detail
        db.commit()
        raise
    db.refresh(channel)
    return _public_channel(channel)


@router.post("/channels/{ref}/disconnect", response_model=WhatsAppChannelOut)
async def disconnect_channel(ref: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _channel_for_user(db, user, ref)
    await bridge_command("POST", f"/channels/{channel.id}/disconnect")
    db.refresh(channel)
    return _public_channel(channel)


@internal_router.get("/channels", dependencies=[Depends(_require_bridge)])
def restorable_channels(db: Session = Depends(get_db)):
    channels = db.scalars(
        select(WhatsAppChannel).where(
            WhatsAppChannel.is_enabled.is_(True),
            WhatsAppChannel.encrypted_auth_state.is_not(None),
        )
    ).all()
    return [{"id": str(item.id)} for item in channels]


@internal_router.get("/channels/{channel_id}", dependencies=[Depends(_require_bridge)])
def internal_channel(channel_id: uuid.UUID, db: Session = Depends(get_db)):
    channel = _internal_channel(db, channel_id)
    auth_state = json.loads(decrypt_secret(channel.encrypted_auth_state)) if channel.encrypted_auth_state else None
    return {
        "id": str(channel.id),
        "client_id": str(channel.client_id),
        "agent_id": str(channel.agent_id),
        "enabled": channel.is_enabled,
        "auth_state": auth_state,
    }


@internal_router.put("/channels/{channel_id}/auth", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_bridge)])
def save_auth(channel_id: uuid.UUID, payload: WhatsAppInternalAuth, db: Session = Depends(get_db)):
    channel = _internal_channel(db, channel_id)
    channel.encrypted_auth_state = encrypt_secret(json.dumps(payload.auth_state, separators=(",", ":")))
    channel.updated_at = now_utc()
    db.commit()


@internal_router.delete("/channels/{channel_id}/auth", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_bridge)])
def clear_auth(channel_id: uuid.UUID, db: Session = Depends(get_db)):
    channel = _internal_channel(db, channel_id)
    channel.encrypted_auth_state = None
    channel.encrypted_qr = None
    channel.phone_number = None
    channel.display_name = None
    channel.status = "disconnected"
    channel.last_error = None
    channel.is_enabled = False
    channel.updated_at = now_utc()
    db.commit()


@internal_router.put("/channels/{channel_id}/status", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_bridge)])
def update_status(channel_id: uuid.UUID, payload: WhatsAppInternalStatus, db: Session = Depends(get_db)):
    channel = _internal_channel(db, channel_id)
    channel.status = payload.status
    if payload.phone_number is not None:
        channel.phone_number = payload.phone_number
    if payload.display_name is not None:
        channel.display_name = payload.display_name
    if payload.qr_code:
        channel.encrypted_qr = encrypt_secret(payload.qr_code)
    elif payload.status in {"connected", "disconnected", "error"}:
        channel.encrypted_qr = None
    channel.last_error = payload.error
    if payload.status == "connected":
        # The same phone scanned on two lines would answer every message
        # twice. The second line is refused; the operator disconnects it.
        twin = db.scalar(
            select(WhatsAppChannel.id).where(
                WhatsAppChannel.agency_id == channel.agency_id,
                WhatsAppChannel.id != channel.id,
                WhatsAppChannel.phone_number == channel.phone_number,
                WhatsAppChannel.is_enabled.is_(True),
                WhatsAppChannel.encrypted_auth_state.is_not(None),
            )
        ) if channel.phone_number else None
        if twin:
            channel.status = "error"
            channel.last_error = "This number is already connected on another line. Disconnect this one."
            channel.is_enabled = False
        else:
            channel.last_connected_at = now_utc()
            channel.is_enabled = True
    channel.updated_at = now_utc()
    db.commit()


@internal_router.post(
    "/channels/{channel_id}/inbound",
    response_model=WhatsAppInboundResult,
    dependencies=[Depends(_require_bridge)],
)
async def inbound_message(channel_id: uuid.UUID, payload: WhatsAppInbound, db: Session = Depends(get_db)):
    channel = _internal_channel(db, channel_id)
    if not channel.is_enabled:
        raise HTTPException(status_code=409, detail="The channel is disconnected")

    media_bytes = None
    if payload.media_base64:
        try:
            media_bytes = base64.b64decode(payload.media_base64)
        except (binascii.Error, ValueError):
            media_bytes = None
    result = await process_inbound(
        db,
        channel,
        InboundMessage(
            external_message_id=payload.external_message_id,
            external_chat_id=payload.remote_jid,
            sender_name=payload.sender_name,
            text=payload.text,
            media_kind=payload.media_kind,
            media_bytes=media_bytes,
            media_mime=payload.media_mime,
            quoted_external_id=payload.quoted_external_id,
        ),
        conversation_channel="whatsapp",
        channel_fk_field="whatsapp_channel_id",
    )
    # The bridge sends result.reply as text; tool-produced files are sent here as
    # attachments (only the synchronous path populates these; a debounced reply
    # sends its own from the timer task).
    if result.attachment_message_ids and result.conversation_id:
        conversation = db.get(Conversation, result.conversation_id)
        if conversation:
            await send_reply_attachments(db, conversation, result.attachment_message_ids)
    return asdict(result)


@internal_router.post("/channels/{channel_id}/reaction", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_bridge)])
def inbound_reaction(channel_id: uuid.UUID, payload: WhatsAppInboundReaction, db: Session = Depends(get_db)):
    """The visitor reacted to a message (or removed the reaction)."""
    message = db.scalar(
        select(Message)
        .join(Conversation)
        .where(
            Conversation.whatsapp_channel_id == channel_id,
            Conversation.external_chat_id == payload.remote_jid,
            Message.external_message_id == payload.target_external_id,
        )
    )
    if not message:
        return
    message.incoming_reaction = payload.emoji or None
    db.commit()


@internal_router.post("/channels/{channel_id}/outbound-confirm", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_bridge)])
def confirm_outbound(channel_id: uuid.UUID, payload: WhatsAppOutboundConfirm, db: Session = Depends(get_db)):
    message = db.scalar(
        select(Message)
        .join(Conversation)
        .where(Message.id == payload.message_id, Conversation.whatsapp_channel_id == channel_id)
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.external_message_id = payload.external_message_id
    db.commit()


@internal_router.post("/channels/{channel_id}/outgoing", status_code=204)
def outgoing_message(channel_id: uuid.UUID, payload: WhatsAppOutgoing,
                     x_bridge_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _require_bridge(x_bridge_token)
    channel = _internal_channel(db, channel_id)
    if not channel.is_enabled:
        raise HTTPException(status_code=409, detail="WhatsApp is disconnected")
    from ..services.phone_handover import record_outgoing
    record_outgoing(db, channel, payload)
