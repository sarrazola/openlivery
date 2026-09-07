"""Authenticated channel administration and one-use OAuth callbacks."""

import uuid
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import SocialChannel, User
from ..schemas_social import SocialChannelOut, SocialChannelUpdate, SocialOAuthComplete, SocialOAuthStart
from ..security import decrypt_secret
from ..services import social_connections as connections
from ..services.social_graph import PROVIDERS, provider_name

router = APIRouter(prefix="/social", tags=["Messaging channels"])


@router.get("/config")
def configuration(user: User = Depends(get_current_user)):
    result = {}
    for provider in sorted(PROVIDERS):
        config = connections.get_app_config(provider)
        result[provider] = {"oauth_ready": config.ready, "manual_available": not config.managed,
                            "source": config.source, "webhook_url": config.webhook_url}
    return result


@router.get("/{provider}/channels/{client_id}", response_model=SocialChannelOut)
def get_channel(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return connections.public_channel(connections.owned_channel(db, user, client_id, provider))


@router.put("/{provider}/channels/{client_id}", response_model=SocialChannelOut)
async def configure_channel(provider: str, client_id: uuid.UUID, payload: SocialChannelUpdate,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    provider_name(provider)
    connections.owned_client(db, user, client_id, payload.agent_id)
    channel = db.scalar(select(SocialChannel).where(SocialChannel.client_id == client_id,
        SocialChannel.agency_id == user.agency_id, SocialChannel.provider == provider))
    config = connections.get_app_config(provider)
    if config.managed and (not channel or payload.access_token or payload.app_secret or
                           payload.external_account_id != channel.external_account_id or
                           (payload.app_id and payload.app_id != channel.app_id)):
        raise HTTPException(403, "Use the account authorization flow to connect this channel")
    access_token = (payload.access_token or "").strip() or (decrypt_secret(channel.encrypted_access_token) if channel and channel.encrypted_access_token else "")
    secret = (payload.app_secret or "").strip() or (decrypt_secret(channel.encrypted_app_secret) if channel and channel.encrypted_app_secret else config.app_secret)
    app_id = payload.app_id or (channel.app_id if channel else None) or config.app_id
    if not access_token or not secret or not app_id:
        raise HTTPException(400, "Provide an application ID, access token and application secret before connecting")
    config = replace(config, app_id=app_id, app_secret=secret)
    account = {"id": payload.external_account_id, "access_token": access_token}
    source = channel.connection_source if channel and not payload.access_token and not payload.app_secret else "manual"
    if channel and not payload.access_token:
        account.update({"expires_at": channel.token_expires_at.isoformat() if channel.token_expires_at else None, "scopes": channel.granted_scopes})
    human_agent = config.human_agent_enabled if config.managed else (payload.human_agent_enabled if payload.human_agent_enabled is not None else bool(channel and channel.human_agent_enabled))
    channel = await connections.connect_account(db, user, client_id, payload.agent_id, provider, account, config,
        source=source, human_agent_enabled=human_agent, activate=bool(channel and channel.status == "connected"))
    return connections.public_channel(channel)


@router.post("/{provider}/channels/{client_id}/connect", response_model=SocialChannelOut)
async def connect_channel(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = connections.owned_channel(db, user, client_id, provider)
    if not channel.encrypted_access_token or not channel.encrypted_app_secret:
        raise HTTPException(400, "Authorize this account or provide credentials before connecting")
    config = replace(connections.get_app_config(provider), app_id=channel.app_id,
                     app_secret=decrypt_secret(channel.encrypted_app_secret))
    account = {"id": channel.external_account_id, "access_token": decrypt_secret(channel.encrypted_access_token),
               "expires_at": channel.token_expires_at.isoformat() if channel.token_expires_at else None, "scopes": channel.granted_scopes}
    return connections.public_channel(await connections.connect_account(db, user, client_id, channel.agent_id, provider,
        account, config, source=channel.connection_source, human_agent_enabled=channel.human_agent_enabled))


@router.post("/{provider}/channels/{client_id}/disconnect", response_model=SocialChannelOut)
async def disconnect_channel(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return connections.public_channel(await connections.disconnect_account(db, connections.owned_channel(db, user, client_id, provider)))


@router.post("/{provider}/oauth/start")
def start_oauth(provider: str, payload: SocialOAuthStart, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    provider_name(provider)
    return {"authorization_url": connections.begin_oauth(db, user, provider, payload.client_id, payload.agent_id, payload.next_path)}


@router.get("/oauth/callback/{provider}")
async def oauth_callback(provider: str, state: str = Query(max_length=256), code: str | None = Query(default=None, max_length=8192),
                         error: str | None = Query(default=None, max_length=256), db: Session = Depends(get_db)):
    target = await connections.finish_oauth(db, provider, state, code, error)
    return RedirectResponse(target, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/{provider}/oauth/pending")
def pending_oauth(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    provider_name(provider)
    return connections.pending_oauth(db, user, provider, client_id)


@router.post("/{provider}/oauth/complete", response_model=SocialChannelOut)
async def complete_oauth(provider: str, payload: SocialOAuthComplete, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    provider_name(provider)
    return connections.public_channel(await connections.complete_oauth(db, user, provider, payload.setup_id, payload.external_account_id))


@router.post("/{provider}/channels/{client_id}/import-history", status_code=202)
def import_history(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.social_history import public_job, request_import
    return public_job(request_import(db, user, client_id, provider))


@router.get("/{provider}/channels/{client_id}/import-history")
def history_import_status(provider: str, client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.social_history import latest_job, public_job
    channel = connections.owned_channel(db, user, client_id, provider)
    job = latest_job(db, channel)
    if not job:
        raise HTTPException(404, "No history import has been requested for this channel")
    return public_job(job)
