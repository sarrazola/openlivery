"""Public webhook for the WhatsApp Cloud API channel.

Meta calls these endpoints directly: a GET handshake when the webhook is
registered, and signed POSTs for inbound traffic. POST bodies are verified
with HMAC-SHA256 over the raw bytes using the channel's app secret, so the
payload is parsed only after the signature check passes.
"""

import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Message, WhatsAppCloudChannel, now_utc
from ..ratelimit import whatsapp_cloud_webhook_rate_limit
from ..security import decrypt_secret
from ..services.whatsapp_cloud import fetch_media, send_text
from ..services.whatsapp_format import markdown_to_whatsapp
from ..services.whatsapp_inbound import InboundMessage, process_inbound


public_router = APIRouter(prefix="/public/whatsapp-cloud", tags=["WhatsApp Cloud public"])

logger = logging.getLogger("openlivery.whatsapp_cloud")


def _channel(db: Session, channel_id: uuid.UUID) -> WhatsAppCloudChannel:
    channel = db.get(WhatsAppCloudChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Unknown channel")
    return channel


@public_router.get("/channels/{channel_id}/webhook")
def verify_webhook(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    channel = _channel(db, channel_id)
    if (
        hub_mode != "subscribe"
        or not channel.webhook_verify_token
        or not hmac.compare_digest(hub_verify_token, channel.webhook_verify_token)
    ):
        raise HTTPException(status_code=403, detail="Verification failed")
    return PlainTextResponse(hub_challenge)


def _parse_message(message: dict, contacts: dict[str, str]) -> InboundMessage | None:
    """Map one Cloud API message to the shared inbound shape; None to skip."""
    kind = message.get("type")
    sender = message.get("from") or ""
    base = {
        "external_message_id": message.get("id") or "",
        "external_chat_id": sender,
        "sender_name": contacts.get(sender),
    }
    if not base["external_message_id"] or not sender:
        return None
    if kind == "text":
        return InboundMessage(**base, text=message.get("text", {}).get("body") or "")
    if kind in {"image", "audio", "video"}:
        media = message.get(kind) or {}
        return InboundMessage(
            **base,
            text=media.get("caption") or "",
            media_kind=kind,
            media_mime=(media.get("mime_type") or "").split(";")[0] or None,
        )
    return None


@public_router.post(
    "/channels/{channel_id}/webhook",
    dependencies=[Depends(whatsapp_cloud_webhook_rate_limit)],
)
async def receive_webhook(channel_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    channel = _channel(db, channel_id)
    if not channel.encrypted_app_secret:
        raise HTTPException(status_code=403, detail="Channel is not configured")
    raw = await request.body()
    app_secret = decrypt_secret(channel.encrypted_app_secret)
    expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    signature = request.headers.get("X-Hub-Signature-256") or ""
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # From here on always acknowledge with 200: Meta retries non-2xx responses,
    # and a payload that fails once will fail on every retry.
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"status": "ok"}
    if not channel.is_enabled:
        return {"status": "ok"}

    access_token = decrypt_secret(channel.encrypted_access_token) if channel.encrypted_access_token else None
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            for status in value.get("statuses") or []:
                _record_status(db, channel, status)
            contacts = {
                contact.get("wa_id"): (contact.get("profile") or {}).get("name")
                for contact in value.get("contacts") or []
            }
            for raw_message in value.get("messages") or []:
                inbound = _parse_message(raw_message, contacts)
                if not inbound:
                    continue
                await _handle_message(db, channel, inbound, raw_message, access_token)
    return {"status": "ok"}


_DELIVERY_ORDER = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}


def _apply_delivery_status(db: Session, channel: WhatsAppCloudChannel, status: dict, error: str | None) -> None:
    """Stamp the receipt on the message it concerns. Receipts can arrive out
    of order, so a later stage is never downgraded by an earlier one."""
    state = status.get("status")
    wamid = status.get("id")
    if state not in _DELIVERY_ORDER or not wamid:
        return
    message = db.scalar(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.external_message_id == wamid, Conversation.whatsapp_cloud_channel_id == channel.id)
    )
    if not message:
        return
    if _DELIVERY_ORDER[state] < _DELIVERY_ORDER.get(message.delivery_status or "", 0):
        return
    message.delivery_status = state
    message.delivery_error = error
    db.commit()


def _record_status(db: Session, channel: WhatsAppCloudChannel, status: dict) -> None:
    """Keep each outbound message's delivery state, and surface failures on
    the channel too, so a message Meta accepted (wamid returned) but dropped
    at delivery leaves a trace of the reason."""
    state = status.get("status")
    if state in ("sent", "delivered", "read"):
        _apply_delivery_status(db, channel, status, None)
        # A delivery error is transient state: clear it once traffic flows again
        # so the channel UI stops showing a stale failure.
        if channel.last_error and channel.last_error.startswith("Meta could not deliver"):
            channel.last_error = None
            channel.updated_at = now_utc()
            db.commit()
        return
    if state != "failed":
        return
    parts = []
    for error in status.get("errors") or []:
        detail = (error.get("error_data") or {}).get("details") or error.get("message") or error.get("title") or ""
        parts.append(f"{error.get('code')}: {detail}".strip(": "))
    summary = "; ".join(parts) or "no error detail provided"
    _apply_delivery_status(db, channel, status, summary[:400])
    logger.warning(
        "WhatsApp Cloud delivery failed for %s: %s",
        status.get("id") or "unknown message",
        summary,
    )
    channel.last_error = f"Meta could not deliver a message ({summary})"[:400]
    channel.updated_at = now_utc()
    db.commit()


async def _handle_message(
    db: Session,
    channel: WhatsAppCloudChannel,
    inbound: InboundMessage,
    raw_message: dict,
    access_token: str | None,
) -> None:
    if inbound.media_kind and access_token:
        media_id = (raw_message.get(inbound.media_kind) or {}).get("id")
        if media_id:
            try:
                inbound.media_bytes, mime = await fetch_media(access_token, media_id)
                inbound.media_mime = inbound.media_mime or mime
            except HTTPException:
                inbound.media_bytes = None
    try:
        result = await process_inbound(
            db,
            channel,
            inbound,
            conversation_channel="whatsapp_cloud",
            channel_fk_field="whatsapp_cloud_channel_id",
        )
    except Exception as exc:
        channel.last_error = f"An inbound message could not be processed: {str(exc)[:400]}"
        channel.updated_at = now_utc()
        db.commit()
        return
    if not result.reply or not access_token or not channel.phone_number_id:
        return
    try:
        wamid = await send_text(
            access_token,
            channel.phone_number_id,
            inbound.external_chat_id,
            markdown_to_whatsapp(result.reply),
            context_message_id=result.quote_external_id,
        )
    except HTTPException as exc:
        channel.last_error = f"The reply could not be sent: {exc.detail}"
        channel.updated_at = now_utc()
        db.commit()
        return
    if wamid and result.outbound_message_id:
        message = db.get(Message, result.outbound_message_id)
        if message:
            message.external_message_id = wamid
            db.commit()
