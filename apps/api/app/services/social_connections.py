"""Connection lifecycle and configurable application credentials."""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, Client, SocialChannel, SocialOAuthState, User, new_public_id, now_utc
from ..security import decrypt_secret, encrypt_secret
from . import social_graph as graph


@dataclass(frozen=True)
class SocialAppConfig:
    provider: str
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    webhook_url: str = ""
    verify_token: str = ""
    source: str = "operator"
    login_config_id: str = ""
    frontend_url: str = ""
    human_agent_enabled: bool = False

    @property
    def callback_url(self):
        return self.redirect_uri

    @property
    def managed(self):
        return self.source == "managed"

    @property
    def ready(self):
        return bool(self.app_id and self.app_secret and self.verify_token and _https_origin(self.redirect_uri))


_app_resolver: Callable | None = None
_connection_hooks: list[Callable] = []
_state_hooks: list[Callable] = []


def register_app_config_resolver(resolver: Callable | None) -> None:
    global _app_resolver
    _app_resolver = resolver


def register_connection_hook(hook: Callable) -> None:
    if hook not in _connection_hooks:
        _connection_hooks.append(hook)


def register_oauth_state_hook(hook: Callable) -> None:
    if hook not in _state_hooks:
        _state_hooks.append(hook)


def _https_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def get_app_config(provider: str) -> SocialAppConfig:
    graph.provider_name(provider)
    if _app_resolver:
        return _app_resolver(provider)
    settings = get_settings()
    origin = (settings.social_public_url or settings.frontend_url).rstrip("/")
    return SocialAppConfig(
        provider=provider, app_id=getattr(settings, f"{provider}_app_id"),
        app_secret=getattr(settings, f"{provider}_app_secret"),
        verify_token=getattr(settings, f"{provider}_webhook_verify_token"),
        redirect_uri=f"{origin}/api/social/oauth/callback/{provider}",
        webhook_url=f"{origin}/api/public/social/{provider}/webhook",
        login_config_id=settings.messenger_login_config_id if provider == "messenger" else "",
        frontend_url=settings.frontend_url,
        human_agent_enabled=getattr(settings, f"{provider}_human_agent_enabled"),
    )


def owned_client(db: Session, user: User, client_id, agent_id=None):
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(404, "Client not found")
    if agent_id is not None and not db.scalar(select(Agent.id).where(Agent.id == agent_id, Agent.client_id == client.id, Agent.agency_id == user.agency_id)):
        raise HTTPException(400, "Select an agent that belongs to this client")
    return client


def owned_channel(db: Session, user: User, client_id, provider: str):
    graph.provider_name(provider)
    owned_client(db, user, client_id)
    channel = db.scalar(select(SocialChannel).where(SocialChannel.client_id == client_id, SocialChannel.agency_id == user.agency_id, SocialChannel.provider == provider))
    if not channel:
        raise HTTPException(404, "This messaging channel has not been configured")
    return channel


def public_channel(channel: SocialChannel) -> dict:
    config = get_app_config(channel.provider)
    parsed = urlsplit(config.redirect_uri)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    webhook = config.webhook_url if channel.connection_source != "manual" else f"{origin}/api/public/social/channels/{channel.id}/webhook"
    keys = ("id", "client_id", "agent_id", "provider", "external_account_id", "app_id", "display_name", "username", "status", "is_enabled", "token_expires_at", "last_error", "human_agent_enabled", "connection_source", "granted_scopes", "last_connected_at", "created_at", "updated_at")
    return {**{key: getattr(channel, key) for key in keys}, "webhook_url": webhook,
            "webhook_verify_token": channel.webhook_verify_token if channel.connection_source == "manual" else (None if config.managed else config.verify_token),
            "has_access_token": bool(channel.encrypted_access_token), "has_app_secret": bool(channel.encrypted_app_secret)}


def _parse_expiry(value):
    return datetime.fromisoformat(value) if value else None


async def connect_account(db: Session, user: User, client_id, agent_id, provider: str, account: dict, config: SocialAppConfig, *, source: str, human_agent_enabled=False, activate=True) -> SocialChannel:
    """Check ownership first; persist credentials only after remote validation."""
    owned_client(db, user, client_id, agent_id)
    account_id = graph.object_id(account["id"])
    app_id = graph.object_id(config.app_id)
    collision = db.scalar(select(SocialChannel.id).where(SocialChannel.provider == provider, SocialChannel.external_account_id == account_id, SocialChannel.client_id != client_id))
    if collision:
        raise HTTPException(409, "This account is already connected to another client")
    channel = db.scalar(select(SocialChannel).where(SocialChannel.client_id == client_id, SocialChannel.agency_id == user.agency_id, SocialChannel.provider == provider).with_for_update())
    if channel and channel.external_account_id and channel.external_account_id != account_id:
        raise HTTPException(409, "An existing channel cannot be reassigned to a different account. Create a separate client to preserve conversation routing")
    token = account["access_token"]
    token_changed = not channel or not channel.encrypted_access_token or decrypt_secret(channel.encrypted_access_token) != token
    profile = await graph.verify_account(provider, token, account_id, app_id, config.app_secret, scopes=account.get("scopes"))
    newly_subscribed = False
    try:
        if not channel:
            channel = SocialChannel(agency_id=user.agency_id, client_id=client_id, agent_id=agent_id, provider=provider, webhook_verify_token=new_public_id())
            db.add(channel)
        channel.agent_id = agent_id
        channel.external_account_id = account_id
        channel.app_id = app_id
        channel.display_name = profile["name"]
        channel.username = profile.get("username")
        channel.encrypted_access_token = encrypt_secret(token)
        channel.encrypted_app_secret = encrypt_secret(config.app_secret)
        channel.token_expires_at = _parse_expiry(profile.get("expires_at") or account.get("expires_at"))
        channel.token_refreshed_at = now_utc() if token_changed or not channel.token_refreshed_at else channel.token_refreshed_at
        if token_changed:
            channel.token_refresh_attempted_at = None
        channel.granted_scopes = profile.get("scopes") or account.get("scopes") or []
        channel.connection_source = source
        channel.status = "connected" if activate else "disconnected"
        channel.is_enabled = activate
        channel.human_agent_enabled = human_agent_enabled
        channel.last_connected_at = now_utc() if activate else channel.last_connected_at
        channel.updated_at = now_utc()
        channel.last_error = None
        db.flush()
        if activate:
            for hook in _connection_hooks:
                hook(db, channel, "linked")
            newly_subscribed = await graph.subscribe(provider, token, account_id, app_id, config.app_secret)
        db.commit()
    except Exception as exc:
        db.rollback()
        if newly_subscribed:
            try:
                await graph.unsubscribe(provider, token, account_id, config.app_secret)
            except HTTPException:
                pass
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "This account is already connected") from None
        raise
    db.refresh(channel)
    return channel


async def disconnect_account(db: Session, channel: SocialChannel) -> SocialChannel:
    remote_error = None
    if channel.encrypted_access_token and channel.encrypted_app_secret and channel.external_account_id:
        try:
            await graph.unsubscribe(channel.provider, decrypt_secret(channel.encrypted_access_token), channel.external_account_id, decrypt_secret(channel.encrypted_app_secret))
        except HTTPException:
            remote_error = "Disconnected locally. Remove the application from the account settings if its remote authorization is still present"
    for hook in _connection_hooks:
        hook(db, channel, "unlinked")
    channel.status = "disconnected"
    channel.is_enabled = False
    channel.encrypted_access_token = None
    channel.encrypted_app_secret = None
    channel.token_expires_at = None
    channel.last_error = remote_error
    channel.updated_at = now_utc()
    db.commit()
    db.refresh(channel)
    return channel


def _payload(state: SocialOAuthState) -> dict:
    try:
        return json.loads(decrypt_secret(state.encrypted_payload))
    except (ValueError, TypeError):
        raise HTTPException(400, "This connection request is invalid") from None


def _new_state(db, user, client_id, agent_id, provider, config, next_url, payload):
    raw = secrets.token_urlsafe(32)
    state = SocialOAuthState(id=hashlib.sha256(raw.encode()).hexdigest(), agency_id=user.agency_id,
        user_id=user.id, client_id=client_id, agent_id=agent_id, provider=provider,
        redirect_uri=config.redirect_uri, next_url=next_url,
        encrypted_payload=encrypt_secret(json.dumps(payload)),
        expires_at=now_utc() + timedelta(minutes=max(1, min(get_settings().social_oauth_state_minutes, 30))))
    db.add(state)
    db.flush()
    for hook in _state_hooks:
        hook(db, state)
    db.commit()
    return raw, state


def begin_oauth(db: Session, user: User, provider: str, client_id, agent_id, next_path: str | None) -> str:
    owned_client(db, user, client_id, agent_id)
    config = get_app_config(provider)
    if not config.ready:
        raise HTTPException(503, "The operator must configure application credentials, HTTPS callbacks and webhook verification first")
    path = next_path or f"/clients/{client_id}/channels/{provider}"
    # Return only to the connection screen of the client bound into this state.
    if path != f"/clients/{client_id}/channels/{provider}":
        raise HTTPException(400, "Use this client's messaging connection page as the return path")
    origin = config.frontend_url or get_settings().frontend_url
    parsed = urlsplit(origin)
    if not _https_origin(origin):
        raise HTTPException(503, "Configure an HTTPS application origin before connecting")
    next_url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    raw, _ = _new_state(db, user, client_id, agent_id, provider, config, next_url,
                        {"phase": "oauth", "app_id": config.app_id})
    query = {"client_id": config.app_id, "redirect_uri": config.redirect_uri, "response_type": "code", "state": raw,
             "scope": ",".join(sorted(graph.SCOPES[provider]))}
    if provider == "instagram":
        query.update({"enable_fb_login": "0", "force_authentication": "1"})
        return "https://www.instagram.com/oauth/authorize?" + urlencode(query)
    if config.login_config_id:
        query["config_id"] = config.login_config_id
        query["override_default_response_type"] = "true"
    return f"https://www.facebook.com/{get_settings().social_graph_version}/dialog/oauth?" + urlencode(query)


async def finish_oauth(db: Session, provider: str, raw_state: str, code: str | None, error: str | None) -> str:
    graph.provider_name(provider)
    if not raw_state or len(raw_state) > 256:
        raise HTTPException(400, "This connection request is invalid or expired")
    state = db.scalar(select(SocialOAuthState).where(SocialOAuthState.id == hashlib.sha256(raw_state.encode()).hexdigest(), SocialOAuthState.provider == provider).with_for_update())
    if not state or state.used_at or state.expires_at <= now_utc() or _payload(state).get("phase") != "oauth":
        raise HTTPException(400, "This connection request is invalid or expired")
    config = get_app_config(provider)
    if _payload(state).get("app_id") != config.app_id or state.redirect_uri != config.redirect_uri:
        raise HTTPException(400, "The application configuration changed. Start the connection again")
    state.used_at = now_utc()
    db.commit()
    target = state.next_url
    if error or not code or len(code) > 8192:
        return target + "?social_status=error"
    try:
        user = db.get(User, state.user_id)
        if not user or user.agency_id != state.agency_id:
            raise HTTPException(403, "The account owner no longer has access")
        owned_client(db, user, state.client_id, state.agent_id)
        accounts = await graph.exchange_code(provider, code, config)
        _new_state(db, user, state.client_id, state.agent_id, provider, config, target,
            {"phase": "pending", "app_id": config.app_id, "accounts": accounts})
    except HTTPException:
        db.rollback()
        return target + "?social_status=error"
    return target + "?social_status=ready"


def pending_oauth(db: Session, user: User, provider: str, client_id) -> dict:
    owned_client(db, user, client_id)
    rows = db.scalars(select(SocialOAuthState).where(SocialOAuthState.provider == provider, SocialOAuthState.agency_id == user.agency_id,
        SocialOAuthState.user_id == user.id, SocialOAuthState.client_id == client_id,
        SocialOAuthState.used_at.is_(None), SocialOAuthState.expires_at > now_utc()).order_by(SocialOAuthState.created_at.desc()).limit(20))
    for state in rows:
        payload = _payload(state)
        if payload.get("phase") == "pending":
            return {"setup_id": state.id, "accounts": [{key: account.get(key) for key in ("id", "name", "username")} for account in payload["accounts"]]}
    raise HTTPException(404, "No pending connection was found. Start the connection again")


async def complete_oauth(db: Session, user: User, provider: str, setup_id: str, account_id: str) -> SocialChannel:
    state = db.scalar(select(SocialOAuthState).where(SocialOAuthState.id == setup_id, SocialOAuthState.provider == provider,
        SocialOAuthState.agency_id == user.agency_id, SocialOAuthState.user_id == user.id).with_for_update())
    if not state or state.used_at or state.expires_at <= now_utc():
        raise HTTPException(400, "This connection request is invalid or expired")
    payload = _payload(state)
    config = get_app_config(provider)
    if payload.get("phase") != "pending" or payload.get("app_id") != config.app_id:
        raise HTTPException(400, "Start the connection again with the current application")
    account = next((account for account in payload.get("accounts", []) if account["id"] == account_id), None)
    if not account:
        raise HTTPException(400, "Select one of the accounts authorized by this connection")
    state.used_at = now_utc()
    state.encrypted_payload = encrypt_secret(json.dumps({"phase": "completed"}))
    # The channel commit also consumes and scrubs the locked setup atomically.
    channel = await connect_account(db, user, state.client_id, state.agent_id, provider, account, config,
                                    source="managed" if config.managed else "oauth", human_agent_enabled=config.human_agent_enabled)
    return channel


async def refresh_due_channels(db: Session) -> None:
    """Refresh renewable tokens and detect expired or revoked Page access."""
    current = now_utc()
    db.execute(delete(SocialOAuthState).where(SocialOAuthState.expires_at <= current))
    db.commit()
    channels = db.scalars(select(SocialChannel).where(SocialChannel.is_enabled.is_(True), SocialChannel.status == "connected",
        or_(SocialChannel.token_expires_at.is_(None), SocialChannel.token_expires_at <= current + timedelta(days=7),
            SocialChannel.provider == "messenger"))).all()
    for channel in channels:
        if channel.token_expires_at and channel.token_expires_at <= current:
            channel.status = "reauthorization_required"
            channel.last_error = "The messaging authorization expired. Reconnect this account"
            channel.updated_at = current
            db.commit()
            continue
        interval = timedelta(hours=24 if channel.provider == "messenger" else 1)
        if channel.token_refresh_attempted_at and channel.token_refresh_attempted_at > current - interval:
            continue
        if channel.provider == "instagram" and channel.token_refreshed_at and channel.token_refreshed_at > current - timedelta(hours=24):
            continue
        channel.token_refresh_attempted_at = current
        db.commit()
        try:
            token = decrypt_secret(channel.encrypted_access_token)
            if channel.provider == "instagram":
                data = await graph.refresh_instagram(token)
                channel.encrypted_access_token = encrypt_secret(data["access_token"])
                channel.token_expires_at = _parse_expiry(data["expires_at"])
                channel.token_refreshed_at = current
            else:
                profile = await graph.verify_account(channel.provider, token, channel.external_account_id,
                    channel.app_id, decrypt_secret(channel.encrypted_app_secret))
                channel.token_expires_at = _parse_expiry(profile.get("expires_at"))
                channel.granted_scopes = profile.get("scopes") or []
            channel.last_error = None
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                channel.status = "reauthorization_required"
            channel.last_error = str(exc.detail)
        channel.updated_at = current
        db.commit()


# The lifecycle name is also used by resource deletion handlers.
disconnect_channel = disconnect_account
