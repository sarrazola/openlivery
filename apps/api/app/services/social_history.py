"""Bounded, resumable imports of history still exposed by the provider."""

import asyncio
import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import SocialChannel, now_utc
from ..security import decrypt_secret
from . import social_graph as graph
from .social_connections import owned_channel
from .social_inbound import enqueue_webhook, event_time

MAX_CONVERSATIONS = 20
MAX_MESSAGES = 20


def public_job(job):
    fields = ("id", "status", "conversations_count", "messages_count", "max_conversations", "last_error", "created_at", "updated_at")
    return {**{field: getattr(job, field) for field in fields}, "limited": True, "has_more": bool(job.cursor)}


def latest_job(db, channel):
    from ..models import SocialHistoryImport
    return db.scalar(select(SocialHistoryImport).where(SocialHistoryImport.channel_id == channel.id)
                     .order_by(SocialHistoryImport.created_at.desc()).limit(1))


def request_import(db, user, client_id, provider):
    from ..models import SocialHistoryImport
    channel = owned_channel(db, user, client_id, provider)
    if not channel.is_enabled or channel.status != "connected" or not channel.last_connected_at:
        raise HTTPException(409, "Connect this account before importing history")
    prior = latest_job(db, channel)
    if prior and prior.status in {"pending", "processing"}:
        return prior
    # A subsequent batch continues from the checkpoint of the prior batch.
    resume = bool(prior and prior.cursor)
    job = SocialHistoryImport(channel_id=channel.id, requested_by=user.id,
        cutoff_at=min(prior.cutoff_at, channel.last_connected_at) if resume else channel.last_connected_at,
        cursor=prior.cursor if resume else None, max_conversations=MAX_CONVERSATIONS)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = latest_job(db, channel)
        if active and active.status in {"pending", "processing"}:
            return active
        raise HTTPException(409, "A history import is already being scheduled") from None
    db.refresh(job)
    return job


def normalize_message(channel, detail: dict, cutoff) -> dict | None:
    """Only import one-to-one messages addressing this receiving account."""
    occurred = event_time(detail.get("created_time"))
    mid = detail.get("id")
    sender = detail.get("from") or {}
    recipients = (detail.get("to") or {}).get("data") or []
    if not occurred or occurred > cutoff or not isinstance(mid, str) or not re.fullmatch(r"[\x21-\x7e]{1,1024}", mid) or not isinstance(sender, dict) or len(recipients) != 1:
        return None
    recipient = recipients[0]
    if not isinstance(recipient, dict):
        return None
    sender_id, recipient_id = str(sender.get("id") or ""), str(recipient.get("id") or "")
    account_id = channel.external_account_id
    if sender_id != account_id and recipient_id != account_id:
        return None
    person = recipient_id if sender_id == account_id else sender_id
    if not person or person == account_id or not person.isdigit():
        return None
    message = {"mid": mid, "text": str(detail.get("message") or "")}
    if sender_id == account_id:
        message["is_echo"] = True
    if not message["text"]:
        message["is_unsupported"] = True
    # The basic detail endpoint may omit expired attachments. Preserve the
    # timestamped record without inventing its original contents.
    return {"sender": {"id": sender_id, "name": sender.get("name"), "username": sender.get("username")},
            "recipient": {"id": recipient_id}, "timestamp": int(occurred.timestamp() * 1000),
            "message": message, "_historical": True}


async def _read_page(channel, cursor: str | None, cutoff):
    token = decrypt_secret(channel.encrypted_access_token)
    secret = decrypt_secret(channel.encrypted_app_secret)
    common = {"appsecret_proof": graph._proof(token, secret)}
    params = {**common, "limit": 1}
    if channel.provider == "instagram":
        params["platform"] = "instagram"
    if cursor:
        params["after"] = cursor
    # Separate this lookup from authorization probes in the same worker pass.
    await asyncio.sleep(0.51)
    page = await graph.request(channel.provider, "GET", f"{graph.object_id(channel.external_account_id)}/conversations", token, params=params)
    items = page.get("data") or []
    if not isinstance(items, list):
        raise HTTPException(502, "The provider returned an invalid conversation list")
    if not items:
        return [], None, False
    item = items[0]
    if not isinstance(item, dict) or not item.get("id"):
        raise HTTPException(502, "The provider returned an invalid conversation identifier")
    # Conversations API calls have a separate two-per-second rate limit.
    await asyncio.sleep(0.51)
    thread = await graph.request(channel.provider, "GET", graph.path_component(str(item["id"])), token,
                                 params={**common, "fields": "messages.limit(20)"})
    messages = (thread.get("messages") or {}).get("data") or []
    if not isinstance(messages, list):
        raise HTTPException(502, "The provider returned an invalid message list")
    semaphore = asyncio.Semaphore(4)

    async def read_message(message):
        if not isinstance(message, dict) or not message.get("id"):
            return None
        async with semaphore:
            try:
                detail = await graph.request(channel.provider, "GET", graph.path_component(str(message["id"])), token,
                    params={**common, "fields": "id,created_time,from,to,message"})
            except HTTPException as exc:
                if exc.status_code in {400, 404}:
                    # Individual history entries can be deleted or unavailable.
                    return None
                raise
        return normalize_message(channel, detail, cutoff)

    details = await asyncio.gather(*(read_message(message) for message in messages[:MAX_MESSAGES]), return_exceptions=True)
    for result in details:
        if isinstance(result, BaseException):
            raise result
    events = sorted((event for event in details if event), key=lambda event: event["timestamp"])
    paging = page.get("paging") or {}
    after = (paging.get("cursors") or {}).get("after") if paging.get("next") else None
    if after is not None and (not isinstance(after, str) or len(after) > 8192):
        raise HTTPException(502, "The provider returned an invalid continuation cursor")
    return events, after, True


async def process_history_jobs(db, *, limit: int = 1) -> int:
    """One bounded conversation per lease; restart resumes its committed cursor."""
    from ..models import SocialHistoryImport
    processed = 0
    for _ in range(limit):
        current = now_utc()
        job = db.scalar(select(SocialHistoryImport).where(
            SocialHistoryImport.status.in_(("pending", "processing")),
            (SocialHistoryImport.locked_until.is_(None)) | (SocialHistoryImport.locked_until <= current),
        ).order_by(SocialHistoryImport.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            db.rollback()
            break
        job.status = "processing"
        job.locked_until = current + timedelta(minutes=5)
        job.updated_at = current
        db.commit()
        channel = db.get(SocialChannel, job.channel_id)
        try:
            if not channel or not channel.is_enabled or channel.status != "connected" or not channel.last_connected_at:
                raise HTTPException(409, "The messaging channel was disconnected. Reconnect it before importing history")
            events, cursor, had_conversation = await _read_page(channel, job.cursor, min(job.cutoff_at, channel.last_connected_at))
            count = enqueue_webhook(db, channel.provider, {"object": "instagram" if channel.provider == "instagram" else "page",
                "entry": [{"id": channel.external_account_id, "messaging": events}]}, channel, commit=False)
            job.cursor = cursor
            job.messages_count += count
            job.conversations_count += int(had_conversation)
            job.status = "completed" if not cursor or job.conversations_count >= job.max_conversations else "pending"
            job.last_error = None
        except HTTPException as exc:
            db.rollback()
            job.status = "failed"
            job.last_error = str(exc.detail)
            if channel and exc.status_code in {401, 403}:
                channel.status = "reauthorization_required"
                channel.last_error = str(exc.detail)
        except Exception:
            db.rollback()
            job.status = "failed"
            job.last_error = "The available history could not be imported. Retry from the last saved checkpoint"
        job.locked_until = None
        job.updated_at = now_utc()
        db.commit()
        processed += 1
    return processed
