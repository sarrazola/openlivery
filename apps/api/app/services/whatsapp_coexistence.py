"""Mirror Business app activity without replaying it through the agent.

History is a durable, bounded import. Phone replies take over immediately in
the receipt transaction; downloading their attachments is separate work.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import case, delete, literal, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..database import new_session
from ..models import Contact, Conversation, Message, WhatsAppCloudChannel, WhatsAppCoexistenceEvent, new_uuid, now_utc
from ..security import decrypt_secret
from .attachments import ensure_uploadable, store_attachment
from .contacts import normalize_phone
from .social_inbound import event_time
from .whatsapp_cloud import _graph_request, _graph_url, fetch_media

logger = logging.getLogger(__name__)
FIELDS = frozenset({"history", "smb_app_state_sync", "smb_message_echoes", "account_update"})
_task = None
_scope_runner = None


def lock_chats(db, channel_id, peers):
    keys = sorted({int.from_bytes(hashlib.sha256(f"{channel_id}:{peer}".encode()).digest()[:8], "big", signed=True) for peer in peers})
    if keys:
        db.execute(text("SELECT pg_advisory_xact_lock(key) FROM unnest(CAST(:keys AS bigint[])) AS key ORDER BY key"), {"keys": keys})


def window_fields(conversation):
    channel = conversation.whatsapp_cloud_channel
    last = conversation.social_last_inbound_at
    until = last + timedelta(hours=24) if last else None
    reason = None
    if not channel or not channel.is_enabled or channel.status != "connected":
        reason = "channel_disconnected"
    elif conversation.status == "resolved":
        reason = "conversation_resolved"
    elif not until or until <= now_utc():
        reason = "reply_window_closed"
    return {"reply_window_until": until, "reply_window_open": reason is None,
            "human_reply_window_until": until, "human_reply_window_open": reason is None, "reply_block_reason": reason}


def require_reply(conversation):
    channel = conversation.whatsapp_cloud_channel
    if channel and channel.coexistence and not window_fields(conversation)["reply_window_open"]:
        raise HTTPException(status_code=409, detail="Wait for a new customer message before replying from the Inbox, or reply from WhatsApp Business on your phone.")


def sync_state(db, channel, section: str, **values):
    # Another transaction may have received progress while a Graph call ran.
    channel = db.scalar(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == channel.id)
                        .with_for_update().execution_options(populate_existing=True))
    state = dict(channel.coexistence_sync or {})
    state[section] = {**state.get(section, {}), **values}
    channel.coexistence_sync = state
    db.flush()
    return channel


def _enqueue(db, channel, field, value):
    key = hashlib.sha256(json.dumps([field, value], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    db.execute(insert(WhatsAppCoexistenceEvent).values(
        id=new_uuid(), channel_id=channel.id, field=field, event_key=key, payload=value,
        cursor=0, attempts=0, available_at=now_utc(), created_at=now_utc(),
    ).on_conflict_do_nothing(constraint="uq_whatsapp_coexistence_event"))


def _text(raw):
    kind = raw.get("type", "unsupported")
    content = raw.get(kind) or {}
    if kind == "text":
        return str(content.get("body") or "")
    if kind == "location":
        return str(content.get("name") or content.get("address") or "[Location]")
    if kind == "contacts":
        return "[Contact]"
    return str(content.get("caption") or content.get("filename") or f"[{kind.replace('_', ' ').capitalize()}]")


def _messages(db, channel, rows, *, historical):
    """Bulk lookups keep a large history chunk from issuing queries per message."""
    rows = [(peer, raw) for peer, raw in rows if normalize_phone(peer) and raw.get("id") and event_time(raw.get("timestamp"))]
    if not rows:
        return
    peers = {peer for peer, _ in rows}
    lock_chats(db, channel.id, peers)
    existing = {m.external_message_id: m for m in db.scalars(select(Message).join(Conversation).where(
        Conversation.whatsapp_cloud_channel_id == channel.id,
        Message.external_message_id.in_([str(raw["id"]) for _, raw in rows]))).all()}
    contacts = {c.phone: c for c in db.scalars(select(Contact).where(Contact.client_id == channel.client_id, Contact.phone.in_(peers)))}
    missing = peers - contacts.keys()
    if missing:
        db.execute(insert(Contact).values([dict(id=new_uuid(), client_id=channel.client_id, phone=peer, name="") for peer in missing])
                   .on_conflict_do_nothing(index_elements=["client_id", "phone"], index_where=Contact.phone.is_not(None)))
        contacts = {c.phone: c for c in db.scalars(select(Contact).where(Contact.client_id == channel.client_id, Contact.phone.in_(peers)))}
    conversations = db.scalars(select(Conversation).where(Conversation.whatsapp_cloud_channel_id == channel.id,
        Conversation.external_chat_id.in_(peers)).order_by(Conversation.created_at.desc())).all()
    by_peer = {}
    for conversation in conversations:
        wanted = conversation.id == uuid.uuid5(channel.id, "history:" + conversation.external_chat_id) if historical else conversation.status != "resolved"
        if wanted:
            by_peer.setdefault(conversation.external_chat_id, conversation)
    business = normalize_phone(channel.phone_number)
    for peer, raw in rows:
        mid = str(raw["id"])
        if mid in existing:
            continue
        occurred = event_time(raw["timestamp"])
        outgoing = not historical or normalize_phone(raw.get("from")) == business or raw.get("to") == peer
        contact = contacts[peer]
        conversation = by_peer.get(peer)
        if not conversation:
            conversation = Conversation(id=uuid.uuid5(channel.id, "history:" + peer) if historical else new_uuid(),
                agency_id=channel.agency_id, client_id=channel.client_id, agent_id=channel.agent_id,
                channel="whatsapp_cloud", whatsapp_cloud_channel_id=channel.id, external_chat_id=peer,
                title=(contact.name or "+" + peer)[:240], contact_id=contact.id, contact_name=contact.name or None,
                mode="human", status="resolved" if historical else "open", created_at=occurred, updated_at=occurred,
                resolved_at=occurred if historical else None)
            db.add(conversation)
            by_peer[peer] = conversation
        if historical:
            conversation.created_at = min(conversation.created_at, occurred)
            conversation.resolved_at = max(conversation.resolved_at or occurred, occurred)
        else:
            # A retry is deduplicated above, so it cannot take over again after
            # an operator has explicitly returned the conversation to the AI.
            conversation.mode = "human"
            conversation.taken_over_at = now_utc()
            conversation.social_reply_due_at = None
            conversation.social_reply_claimed_until = None
            if not conversation.waiting_since or occurred + timedelta(seconds=1) >= conversation.waiting_since:
                conversation.waiting_since = None
            conversation.first_reply_at = conversation.first_reply_at or occurred
        conversation.updated_at = max(conversation.updated_at, occurred)
        state = str((raw.get("history_context") or {}).get("status", "sent")).lower()
        message = Message(id=new_uuid(), conversation_id=conversation.id, external_message_id=mid,
            role="assistant" if outgoing else "user", content=_text(raw), is_historical=historical,
            sender_type="human" if outgoing else "visitor", sender_name="WhatsApp Business" if outgoing else contact.name,
            delivery_status={"played": "read", "error": "failed", "pending": "pending"}.get(state, state) if outgoing else None,
            created_at=occurred)
        db.add(message)
        existing[mid] = message
    db.flush()
    for peer, raw in rows:
        media = raw.get(raw.get("type")) or {}
        if isinstance(media, dict) and media.get("id") and raw.get("type") in {"image", "audio", "video", "document", "sticker"}:
            _enqueue(db, channel, "media", {"message_id": str(raw["id"]), "raw": raw})


def accept_change(db, channel, field: str, value: dict, *, waba_id: str = "") -> bool:
    """Caller must verify the signature. Failure to commit must cause a retry."""
    if field not in FIELDS or not channel.coexistence:
        return False
    delivered = (value.get("metadata") or {}).get("phone_number_id")
    if field == "account_update":
        if not waba_id or waba_id != channel.waba_id:
            return False
        phone = normalize_phone(value.get("phone_number"))
        if phone and phone != normalize_phone(channel.phone_number):
            return False
        if value.get("event") in {"PARTNER_REMOVED", "ACCOUNT_OFFBOARDED"}:
            channel.status = "disconnected"
            channel.is_enabled = False
            channel.encrypted_access_token = None
            channel.last_error = "WhatsApp Business disconnected this number. Connect it again to resume."
            channel.coexistence_sync = {**(channel.coexistence_sync or {}), "offboarded_at": now_utc().isoformat()}
        db.commit()
        return True
    if delivered != channel.phone_number_id or not channel.is_enabled:
        return False
    if field == "smb_message_echoes":
        business = normalize_phone(channel.phone_number)
        rows = [(normalize_phone(raw.get("to")), raw) for raw in value.get("message_echoes", [])
                if business and normalize_phone(raw.get("from")) == business]
        _messages(db, channel, rows, historical=False)
    else:
        _enqueue(db, channel, field, value)
    db.commit()
    return True


async def request_sync(db, channel):
    """Persist intent before either one-shot request. Never retry an unknown send."""
    for section, sync_type in (("contacts", "smb_app_state_sync"), ("history", "history")):
        channel = db.scalar(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == channel.id)
                            .with_for_update().execution_options(populate_existing=True))
        state = (channel.coexistence_sync or {}).get(section, {})
        if not channel.is_enabled or not channel.encrypted_access_token or state.get("status") != "pending":
            db.rollback()
            continue
        started = event_time((channel.coexistence_sync or {}).get("started_at"))
        if started and now_utc() - started >= timedelta(hours=24):
            sync_state(db, channel, section, status="error", error="The synchronization window expired. Disconnect in WhatsApp Business before onboarding again.")
            db.commit()
            continue
        sync_state(db, channel, section, status="requesting", requested_at=now_utc().isoformat())
        access_token = decrypt_secret(channel.encrypted_access_token)
        phone = channel.phone_number_id
        db.commit()
        try:
            response = await _graph_request("POST", _graph_url(f"{phone}/smb_app_data"), access_token,
                json={"messaging_product": "whatsapp", "sync_type": sync_type})
            result = response.json()
            if response.status_code >= 400 or not result.get("request_id"):
                sync_state(db, channel, section, status="error", error="Meta did not accept the synchronization request.")
            else:
                current = db.scalar(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.id == channel.id)
                                    .with_for_update().execution_options(populate_existing=True))
                status = (current.coexistence_sync or {}).get(section, {}).get("status")
                sync_state(db, channel, section, status="requested" if status == "requesting" else status,
                           request_id=str(result["request_id"]))
        except (HTTPException, ValueError):
            sync_state(db, channel, section, status="unknown", error="Meta's response was not received. Do not repeat onboarding until the synchronization status is checked.")
        db.commit()


def _history_rows(value):
    for batch in value.get("history", []):
        for thread in batch.get("threads", []):
            peer = normalize_phone(thread.get("id"))
            if peer:
                for raw in thread.get("messages", []):
                    yield peer, raw


def _contacts(db, channel, rows):
    latest = {}
    for row in rows:
        if row.get("type") != "contact" or row.get("action") not in {"add", "remove"}:
            continue
        raw = row.get("contact") or {}
        phone = normalize_phone(raw.get("phone_number"))
        occurred = event_time((row.get("metadata") or {}).get("timestamp"))
        if not phone or not occurred or (phone in latest and latest[phone][0] >= occurred):
            continue
        name = str(raw.get("full_name") or raw.get("first_name") or "")[:180] if row["action"] == "add" else ""
        latest[phone] = (occurred, name)
    if not latest:
        return
    statement = insert(Contact).values([dict(id=new_uuid(), client_id=channel.client_id, phone=phone, name=name,
        whatsapp_contact_name=name, whatsapp_contact_updated_at=occurred)
        for phone, (occurred, name) in latest.items()])
    # A phone-book removal removes only the synchronized label. Local names,
    # notes, blocked status and conversations remain owned by the operator.
    db.execute(statement.on_conflict_do_update(index_elements=["client_id", "phone"], index_where=Contact.phone.is_not(None),
        set_={"name": case((or_(Contact.name == "", Contact.name == Contact.whatsapp_contact_name), statement.excluded.name), else_=Contact.name),
              "whatsapp_contact_name": statement.excluded.whatsapp_contact_name,
              "whatsapp_contact_updated_at": statement.excluded.whatsapp_contact_updated_at},
        where=or_(Contact.whatsapp_contact_updated_at.is_(None), Contact.whatsapp_contact_updated_at < statement.excluded.whatsapp_contact_updated_at)))
    db.execute(update(Conversation).where(Conversation.contact_id == Contact.id, Contact.client_id == channel.client_id,
        Contact.phone.in_(latest)).values(contact_name=Contact.name,
        title=case((Contact.name != "", Contact.name), else_=literal("+") + Contact.phone)))
    db.flush()


async def process_pending(db, *, limit=2, batch_size=100):
    for _ in range(limit):
        item = db.scalar(select(WhatsAppCoexistenceEvent).where(WhatsAppCoexistenceEvent.processed_at.is_(None),
            WhatsAppCoexistenceEvent.available_at <= now_utc(), WhatsAppCoexistenceEvent.attempts < 8)
            .order_by(WhatsAppCoexistenceEvent.available_at).with_for_update(skip_locked=True).limit(1))
        if not item:
            db.rollback()
            break
        item_id = item.id
        try:
            channel = db.get(WhatsAppCloudChannel, item.channel_id)
            if not channel or not channel.coexistence or not channel.is_enabled:
                item.payload = {}
                item.processed_at = now_utc()
                db.commit()
                continue
            value = item.payload
            done = True
            if item.field == "history":
                rows = list(_history_rows(value))
                _messages(db, channel, rows[item.cursor:item.cursor + batch_size], historical=True)
                item.cursor += batch_size
                done = item.cursor >= len(rows)
                if done:
                    for batch in value.get("history", []):
                        for error in batch.get("errors", []):
                            sync_state(db, channel, "history", status="declined" if error.get("code") == 2593109 else "error")
                        progress = (batch.get("metadata") or {}).get("progress")
                        if isinstance(progress, int) and not batch.get("errors"):
                            prior = (channel.coexistence_sync or {}).get("history", {}).get("progress", 0)
                            progress = min(100, max(prior, progress))
                            other_pending = db.scalar(select(WhatsAppCoexistenceEvent.id).where(
                                WhatsAppCoexistenceEvent.channel_id == channel.id, WhatsAppCoexistenceEvent.id != item.id,
                                WhatsAppCoexistenceEvent.field == "history", WhatsAppCoexistenceEvent.processed_at.is_(None)).limit(1))
                            sync_state(db, channel, "history", progress=progress,
                                       status="complete" if progress == 100 and not other_pending else "syncing")
                    # Media-only history envelopes can precede their text chunk.
                    for raw in value.get("messages", []):
                        _enqueue(db, channel, "media", {"message_id": str(raw.get("id", "")), "raw": raw})
            elif item.field == "smb_app_state_sync":
                rows = value.get("state_sync", [])
                _contacts(db, channel, rows[item.cursor:item.cursor + batch_size])
                item.cursor += batch_size
                done = item.cursor >= len(rows)
                if done:
                    sync_state(db, channel, "contacts", status="syncing", last_received_at=now_utc().isoformat())
            elif item.field == "media":
                message = db.scalar(select(Message).join(Conversation).where(
                    Conversation.whatsapp_cloud_channel_id == channel.id, Message.external_message_id == value["message_id"])
                    .options(selectinload(Message.attachments)))
                if not message:
                    raise ValueError("Waiting for the corresponding history message")
                if not message.attachments:
                    raw = value["raw"]
                    media = raw.get(raw.get("type")) or {}
                    data, mime = await fetch_media(decrypt_secret(channel.encrypted_access_token), media["id"])
                    ensure_uploadable(mime)
                    store_attachment(db, message, data=data, mime=mime, filename=media.get("filename"))
                    if message.content == "[Media placeholder]":
                        message.content = _text(raw)
            if done:
                item.processed_at = now_utc()
                item.payload = {}
            else:
                # Other accounts and small media jobs get a turn between chunks.
                item.available_at = now_utc() + timedelta(seconds=1)
            db.commit()
        except Exception as exc:
            db.rollback()
            attempts = db.execute(update(WhatsAppCoexistenceEvent).where(WhatsAppCoexistenceEvent.id == item_id).values(
                attempts=WhatsAppCoexistenceEvent.attempts + 1, available_at=now_utc() + timedelta(seconds=60),
                last_error=type(exc).__name__).returning(WhatsAppCoexistenceEvent.attempts)).scalar_one()
            if attempts >= 8:
                failed = db.get(WhatsAppCoexistenceEvent, item_id)
                channel = db.get(WhatsAppCloudChannel, failed.channel_id)
                section = "contacts" if failed.field == "smb_app_state_sync" else failed.field
                sync_state(db, channel, section, status="error", error="Some synchronization data could not be processed. Contact support.")
            db.commit()
            logger.warning("WhatsApp synchronization deferred for %s (%s)", item_id, type(exc).__name__)


async def run_scope(db):
    ids = db.scalars(select(WhatsAppCloudChannel.id).where(WhatsAppCloudChannel.coexistence.is_(True),
        WhatsAppCloudChannel.is_enabled.is_(True))).all()
    for channel_id in ids:
        channel = db.get(WhatsAppCloudChannel, channel_id)
        for part in ("contacts", "history"):
            state = (channel.coexistence_sync or {}).get(part, {})
            requested_at = event_time(state.get("requested_at"))
            if state.get("status") == "requesting" and requested_at and now_utc() - requested_at > timedelta(minutes=5):
                sync_state(db, channel, part, status="unknown", error="The server restarted before Meta's response was recorded. Check synchronization before reconnecting.")
                db.commit()
        if any((channel.coexistence_sync or {}).get(part, {}).get("status") == "pending" for part in ("contacts", "history")):
            await request_sync(db, channel)
    await process_pending(db)
    db.execute(delete(WhatsAppCoexistenceEvent).where(or_(
        WhatsAppCoexistenceEvent.processed_at < now_utc() - timedelta(days=30),
        (WhatsAppCoexistenceEvent.attempts >= 8) & (WhatsAppCoexistenceEvent.created_at < now_utc() - timedelta(days=30)))))
    db.commit()


def install_scope_runner(runner):
    global _scope_runner
    _scope_runner = runner


async def _loop():
    while True:
        await asyncio.sleep(max(0.5, get_settings().social_worker_interval_seconds))
        try:
            if _scope_runner:
                await _scope_runner(run_scope)
            else:
                with new_session() as db:
                    await run_scope(db)
        except Exception as exc:
            logger.warning("WhatsApp synchronization worker failed (%s)", type(exc).__name__)


def start_worker():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_worker():
    global _task
    task, _task = _task, None
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
