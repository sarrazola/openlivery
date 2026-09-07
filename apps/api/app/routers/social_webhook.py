"""Signed messaging callbacks and expiring attachment delivery URLs."""
import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Message, MessageAttachment, SocialChannel, now_utc
from ..ratelimit import whatsapp_cloud_webhook_rate_limit
from ..security import decrypt_secret
from ..services.social_connections import get_app_config
from ..services.social_graph import provider_name
from ..services.social_inbound import enqueue_webhook
from ..services.social_media import media_signature
from ..services.attachments import content_disposition

public_router = APIRouter(prefix="/public/social", tags=["Social messaging callbacks"])
MAX_WEBHOOK_BYTES = 2 * 1024 * 1024


def _challenge(token: str, mode: str, received: str, challenge: str):
    if mode != "subscribe" or not token or not hmac.compare_digest(token.encode("utf-8"), received.encode("utf-8")):
        raise HTTPException(403, "Verification failed")
    return PlainTextResponse(challenge)


async def _verified_payload(request: Request, secret: str) -> dict:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "The webhook payload is too large")
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature.encode("utf-8"), expected.encode("ascii")):
        raise HTTPException(403, "Invalid signature")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON payload") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("entry", []), list):
        raise HTTPException(400, "Invalid event envelope")
    return payload


def _channel(db: Session, channel_id: uuid.UUID) -> SocialChannel:
    channel = db.get(SocialChannel, channel_id)
    if not channel:
        raise HTTPException(404, "Unknown channel")
    return channel


@public_router.get("/channels/{channel_id}/webhook")
def verify_channel(channel_id: uuid.UUID, db: Session = Depends(get_db),
    mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge")):
    channel = _channel(db, channel_id)
    return _challenge(channel.webhook_verify_token, mode, token, challenge)


@public_router.post("/channels/{channel_id}/webhook", dependencies=[Depends(whatsapp_cloud_webhook_rate_limit)])
async def receive_channel(channel_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    channel = _channel(db, channel_id)
    secret = decrypt_secret(channel.encrypted_app_secret) if channel.encrypted_app_secret else ""
    payload = await _verified_payload(request, secret)
    enqueue_webhook(db, channel.provider, payload, channel)
    return {"status": "ok"}


@public_router.get("/{provider}/webhook")
def verify_app(provider: str, mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"), challenge: str = Query("", alias="hub.challenge")):
    config = get_app_config(provider_name(provider))
    if config.managed:
        raise HTTPException(404, "Use the configured callback address")
    return _challenge(config.verify_token, mode, token, challenge)


@public_router.post("/{provider}/webhook", dependencies=[Depends(whatsapp_cloud_webhook_rate_limit)])
async def receive_app(provider: str, request: Request, db: Session = Depends(get_db)):
    config = get_app_config(provider_name(provider))
    if config.managed:
        raise HTTPException(404, "Use the configured callback address")
    payload = await _verified_payload(request, config.app_secret)
    # Never route traffic authenticated by one app into an account configured
    # with another app secret, even if their external account ids coincide.
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        channel = db.scalar(select(SocialChannel).where(SocialChannel.provider == provider,
            SocialChannel.external_account_id == str(entry.get("id", ""))))
        if (not channel or channel.app_id != config.app_id or not channel.encrypted_app_secret
            or not hmac.compare_digest(decrypt_secret(channel.encrypted_app_secret).encode("utf-8"), config.app_secret.encode("utf-8"))):
            continue
        enqueue_webhook(db, provider, {"object": payload.get("object"), "entry": [entry]}, channel)
    return {"status": "ok"}


@public_router.get("/media/{channel_id}/{attachment_id}")
def media(channel_id: uuid.UUID, attachment_id: uuid.UUID, expires: int, signature: str,
          db: Session = Depends(get_db)):
    channel = _channel(db, channel_id)
    now = int(now_utc().timestamp())
    if (not channel.is_enabled or not channel.encrypted_app_secret or expires <= now or expires > now + 86400
            or not hmac.compare_digest(signature.encode("utf-8"), media_signature(channel, attachment_id, expires).encode("ascii"))):
        raise HTTPException(403, "This attachment link is invalid or expired")
    attachment = db.scalar(select(MessageAttachment).join(Message).join(Conversation).where(
        MessageAttachment.id == attachment_id, Conversation.social_channel_id == channel.id,
        Message.role == "assistant"))
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    return Response(attachment.data, media_type=attachment.mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "default-src 'none'; sandbox", "Referrer-Policy": "no-referrer",
                 "Content-Disposition": content_disposition(attachment.filename)})
