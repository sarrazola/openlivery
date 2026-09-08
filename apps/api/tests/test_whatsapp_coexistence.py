import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, update

from app.models import Contact, Conversation, Message, WhatsAppCloudChannel, WhatsAppCoexistenceEvent, now_utc
from app.services import whatsapp_coexistence as coex, whatsapp_inbound
from app.services.ai import Completion
from app.routers import whatsapp_cloud_webhook
from conftest import TestingSession
from test_whatsapp_cloud import _setup_channel, _post_signed, _webhook_payload

BUSINESS = "15550783881"
PERSON = "16505551234"


@pytest.fixture
def channel(authenticated_client):
    _, _, data = _setup_channel(authenticated_client)
    with TestingSession() as db:
        channel = db.get(WhatsAppCloudChannel, uuid.UUID(data["id"]))
        channel.phone_number = BUSINESS
        channel.coexistence = True
        channel.status = "connected"
        channel.is_enabled = True
        channel.coexistence_sync = {"history": {"status": "pending"}, "contacts": {"status": "pending"}}
        db.commit()
    return uuid.UUID(data["id"])


def raw(mid, *, outgoing=False, age=60, kind="text"):
    return {"id": mid, "from": BUSINESS if outgoing else PERSON,
        "timestamp": str(int((now_utc() - timedelta(seconds=age)).timestamp())),
        "type": kind, "text": {"body": mid}}


def value(**parts):
    return {"metadata": {"phone_number_id": "111", "display_phone_number": BUSINESS}, **parts}


def receive(db, channel_id, field, body):
    return coex.accept_change(db, db.get(WhatsAppCloudChannel, channel_id), field, body, waba_id="waba-1")


def history(*messages, progress=100):
    return value(history=[{"metadata": {"phase": 2, "chunk_order": 1, "progress": progress},
        "threads": [{"id": PERSON, "messages": list(messages)}]}])


def test_history_is_durable_bounded_and_never_replies(channel, monkeypatch):
    ai = AsyncMock()
    monkeypatch.setattr(whatsapp_inbound, "run_completion", ai)
    payload = history(raw("old-in", age=86400), raw("old-out", outgoing=True, age=86000))
    with TestingSession() as db:
        receive(db, channel, "history", payload)
        receive(db, channel, "history", payload)
        assert len(db.scalars(select(WhatsAppCoexistenceEvent)).all()) == 1
        assert not db.scalars(select(Message)).all()
        asyncio.run(coex.process_pending(db, limit=1, batch_size=1))
        assert len(db.scalars(select(Message)).all()) == 1
        assert db.get(WhatsAppCloudChannel, channel).coexistence_sync["history"]["status"] == "pending"
        db.execute(update(WhatsAppCoexistenceEvent).values(available_at=now_utc()))
        db.commit()
    # A fresh process/session continues from the persisted offset.
    with TestingSession() as db:
        asyncio.run(coex.process_pending(db, limit=1, batch_size=1))
        messages = db.scalars(select(Message).order_by(Message.created_at)).all()
        assert [m.role for m in messages] == ["user", "assistant"]
        assert all(m.is_historical for m in messages)
        conv = db.scalar(select(Conversation))
        assert conv.status == "resolved" and conv.waiting_since is None
        assert conv.social_last_inbound_at is None
        assert db.get(WhatsAppCloudChannel, channel).coexistence_sync["history"]["progress"] == 100
        assert db.scalar(select(WhatsAppCoexistenceEvent)).payload == {}
    ai.assert_not_called()


def test_phone_reply_pauses_agent_and_duplicate_does_not_take_over_twice(channel):
    echo = raw("phone-reply", outgoing=True, age=0)
    echo["to"] = PERSON
    with TestingSession() as db:
        receive(db, channel, "smb_message_echoes", value(message_echoes=[echo]))
        conv = db.scalar(select(Conversation))
        assert conv.mode == "human" and conv.taken_over_at
        assert db.scalar(select(Message)).sender_type == "human"
        conv.mode = "ai"
        db.commit()
        receive(db, channel, "smb_message_echoes", value(message_echoes=[echo]))
        db.refresh(conv)
        assert conv.mode == "ai"
        assert len(db.scalars(select(Message)).all()) == 1


def test_manual_routes_cannot_replace_or_locally_offboard_a_business_app_number(channel, authenticated_client):
    with TestingSession() as db:
        stored = db.get(WhatsAppCloudChannel, channel)
        client_id, agent_id = str(stored.client_id), str(stored.agent_id)
    url = f"/api/whatsapp-cloud/channels/{client_id}"
    assert authenticated_client.put(url, json={"agent_id": agent_id, "phone_number_id": "222"}).status_code == 409
    assert authenticated_client.post(f"{url}/disconnect").status_code == 409
    assert authenticated_client.put(url, json={"agent_id": agent_id}).status_code == 200
    with TestingSession() as db:
        stored = db.get(WhatsAppCloudChannel, channel)
        stored.is_enabled = False
        stored.status = "disconnected"
        db.commit()
    assert authenticated_client.put(url, json={"agent_id": agent_id}).json()["is_enabled"] is False


def test_failed_import_is_visible_and_does_not_erase_accepted_messages(channel, monkeypatch):
    with TestingSession() as db:
        receive(db, channel, "history", history(raw("bad-chunk")))
        db.execute(update(WhatsAppCoexistenceEvent).values(attempts=7))
        db.commit()
        def fail(*args, **kwargs):
            raise ValueError("Invalid import")
        monkeypatch.setattr(coex, "_messages", fail)
        asyncio.run(coex.process_pending(db))
        assert db.get(WhatsAppCloudChannel, channel).coexistence_sync["history"]["status"] == "error"
        receipt = db.scalar(select(WhatsAppCoexistenceEvent))
        assert receipt.attempts == 8 and receipt.payload


def test_phone_reply_received_during_generation_suppresses_ai(channel, authenticated_client, monkeypatch):
    async def complete(*args, **kwargs):
        echo = raw("person-took-over", outgoing=True, age=0)
        echo["to"] = PERSON
        with TestingSession() as other:
            receive(other, channel, "smb_message_echoes", value(message_echoes=[echo]))
        return Completion(text="This must not be sent")
    monkeypatch.setattr(whatsapp_inbound, "run_completion", complete)
    monkeypatch.setattr(whatsapp_inbound, "_signal_read_and_typing", AsyncMock())
    send = AsyncMock()
    monkeypatch.setattr(whatsapp_cloud_webhook, "send_text", send)
    response = _post_signed(authenticated_client, str(channel), _webhook_payload([raw("new-inbound", age=0)]))
    assert response.status_code == 200
    send.assert_not_called()
    with TestingSession() as db:
        assert db.scalar(select(Conversation)).mode == "human"
        assert not db.scalars(select(Message).where(Message.sender_type == "ai")).all()


def test_history_does_not_duplicate_live_message_or_overwrite_its_role(channel):
    echo = raw("same-id", outgoing=True)
    echo["to"] = PERSON
    with TestingSession() as db:
        receive(db, channel, "smb_message_echoes", value(message_echoes=[echo]))
        receive(db, channel, "history", history(echo))
        asyncio.run(coex.process_pending(db))
        message = db.scalar(select(Message))
        assert not message.is_historical and message.role == "assistant"
        assert len(db.scalars(select(Message)).all()) == 1


def test_other_number_and_forged_signature_are_rejected(channel, authenticated_client):
    with TestingSession() as db:
        other = history(raw("wrong-number"))
        other["metadata"]["phone_number_id"] = "222"
        assert receive(db, channel, "history", other) is False
    payload = {"entry": [{"id": "waba-1", "changes": [{"field": "history", "value": history(raw("forged"))}]}]}
    assert _post_signed(authenticated_client, str(channel), payload, secret="wrong").status_code == 403
    with TestingSession() as db:
        assert not db.scalars(select(WhatsAppCoexistenceEvent)).all()


def test_history_declined_is_a_supported_choice(channel):
    with TestingSession() as db:
        receive(db, channel, "history", value(history=[{"errors": [{"code": 2593109}]}]))
        asyncio.run(coex.process_pending(db))
        row = db.get(WhatsAppCloudChannel, channel)
        assert row.coexistence_sync["history"]["status"] == "declined"
        assert row.status == "connected"


def test_sync_requests_are_once_only_and_store_meta_request_ids(channel, monkeypatch):
    send = AsyncMock(side_effect=[httpx.Response(200, json={"request_id": "contacts-1"}), httpx.Response(200, json={"request_id": "history-1"})])
    monkeypatch.setattr(coex, "_graph_request", send)
    with TestingSession() as db:
        row = db.get(WhatsAppCloudChannel, channel)
        asyncio.run(coex.request_sync(db, row))
        asyncio.run(coex.request_sync(db, row))
        assert row.coexistence_sync["contacts"]["request_id"] == "contacts-1"
        assert row.coexistence_sync["history"]["request_id"] == "history-1"
    assert send.await_count == 2
    assert send.call_args_list[0].kwargs["json"]["sync_type"] == "smb_app_state_sync"


def test_ambiguous_sync_response_is_not_retried(channel, monkeypatch):
    send = AsyncMock(side_effect=HTTPException(status_code=502))
    monkeypatch.setattr(coex, "_graph_request", send)
    with TestingSession() as db:
        row = db.get(WhatsAppCloudChannel, channel)
        asyncio.run(coex.request_sync(db, row))
        asyncio.run(coex.request_sync(db, row))
        assert row.coexistence_sync["history"]["status"] == "unknown"
    assert send.await_count == 2


def test_media_history_can_arrive_before_the_message(channel, monkeypatch):
    media = raw("photo", kind="image")
    media["image"] = {"id": "asset-1", "caption": "A photo"}
    monkeypatch.setattr(coex, "fetch_media", AsyncMock(return_value=(b"image bytes", "image/jpeg")))
    with TestingSession() as db:
        receive(db, channel, "history", value(messages=[media]))
        asyncio.run(coex.process_pending(db))
        receive(db, channel, "history", history(raw("photo", kind="media_placeholder")))
        asyncio.run(coex.process_pending(db))
        db.execute(update(WhatsAppCoexistenceEvent).values(available_at=now_utc()))
        db.commit()
        asyncio.run(coex.process_pending(db))
        message = db.scalar(select(Message))
        assert message.content == "A photo" and len(message.attachments) == 1
        assert message.is_historical


def test_offboarding_stops_messages_and_drops_credentials(channel):
    with TestingSession() as db:
        receive(db, channel, "account_update", {"event": "PARTNER_REMOVED", "phone_number": BUSINESS})
        row = db.get(WhatsAppCloudChannel, channel)
        assert row.status == "disconnected" and not row.is_enabled and not row.encrypted_access_token
        assert row.coexistence_sync["offboarded_at"]


def test_import_query_count_does_not_grow_per_message(channel):
    with TestingSession() as db:
        receive(db, channel, "history", history(*[raw(f"history-{i}", age=1000-i) for i in range(100)]))
        calls = []
        engine = db.get_bind()
        def count(*args): calls.append(1)
        event.listen(engine, "before_cursor_execute", count)
        try:
            asyncio.run(coex.process_pending(db, limit=1))
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert len(calls) < 25, len(calls)
        assert len(db.scalars(select(Message)).all()) == 100


def test_contacts_name_history_placeholders_and_ignore_out_of_order_changes(channel):
    def contact(action, age, name=""):
        return {"type": "contact", "action": action, "metadata": {"timestamp": str(int((now_utc()-timedelta(seconds=age)).timestamp()))},
                "contact": {"phone_number": PERSON, "full_name": name}}
    with TestingSession() as db:
        receive(db, channel, "history", history(raw("old-contact")))
        asyncio.run(coex.process_pending(db))
        receive(db, channel, "smb_app_state_sync", value(state_sync=[contact("add", 500, "Sam")]))
        asyncio.run(coex.process_pending(db))
        db.expire_all()
        person = db.scalar(select(Contact))
        assert person.name == "Sam"
        receive(db, channel, "smb_app_state_sync", value(state_sync=[contact("remove", 100)]))
        asyncio.run(coex.process_pending(db))
        receive(db, channel, "smb_app_state_sync", value(state_sync=[contact("add", 300, "Stale name")]))
        asyncio.run(coex.process_pending(db))
        db.refresh(person)
        assert person.name == ""
        assert len(db.scalars(select(Message)).all()) == 1
        person.name = "My customer label"
        db.commit()
        receive(db, channel, "smb_app_state_sync", value(state_sync=[contact("add", 0, "Phone label")]))
        asyncio.run(coex.process_pending(db))
        db.refresh(person)
        assert person.name == "My customer label"


def test_history_does_not_open_the_api_reply_window(channel):
    with TestingSession() as db:
        receive(db, channel, "history", history(raw("recent-but-imported", age=30)))
        asyncio.run(coex.process_pending(db))
        conv = db.scalar(select(Conversation))
        conv.status = "open"
        assert coex.window_fields(conv)["reply_block_reason"] == "reply_window_closed"
        with pytest.raises(HTTPException):
            coex.require_reply(conv)


def test_restart_does_not_repeat_an_inflight_sync(channel, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(coex, "_graph_request", send)
    with TestingSession() as db:
        row = db.get(WhatsAppCloudChannel, channel)
        row.coexistence_sync = {part: {"status": "requesting", "requested_at": (now_utc()-timedelta(minutes=10)).isoformat()}
                                for part in ("history", "contacts")}
        db.commit()
        asyncio.run(coex.run_scope(db))
        assert row.coexistence_sync["history"]["status"] == "unknown"
    send.assert_not_called()
