"""Messaging runtime contracts exercised against disposable PostgreSQL and stubbed providers."""
import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Agent, Contact, ContactIdentity, Conversation, Message, MessageAttachment, ProviderCredential, SocialChannel, SocialOutbox, SocialWebhookEvent, Team, now_utc
from app.security import encrypt_secret
from app.services import escalation, notifications, social_connections, social_delivery, social_graph, social_inbound, social_policy, social_worker, whatsapp_inbound
from app.services.ai import Completion
from app.services.contacts import merge_contacts, resolve_contact
from app.services.conversation_state import set_status
from conftest import TestingSession


SECRET = "runtime-test-app-secret"
PERSON = "123456789012345"


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    monkeypatch.setattr(social_connections, "_app_resolver", None)
    monkeypatch.setattr(social_connections, "_connection_hooks", [])
    monkeypatch.setattr(social_connections, "_state_hooks", [])
    monkeypatch.setattr(social_graph, "verify_account", AsyncMock(return_value={"id": "111", "name": "Shop", "scopes": ["instagram_business_basic", "instagram_business_manage_messages"]}))
    monkeypatch.setattr(social_graph, "subscribe", AsyncMock(return_value=True))
    monkeypatch.setattr(social_graph, "unsubscribe", AsyncMock())
    monkeypatch.setattr(social_graph, "send_text", AsyncMock(side_effect=lambda *args, **kwargs: f"sent.{uuid.uuid4().hex}"))
    monkeypatch.setattr(social_graph, "send_media", AsyncMock(side_effect=AssertionError("Unexpected media network call")))
    monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(return_value=Completion(text="We can help.")))
    monkeypatch.setattr(notifications, "notify_needs_human", AsyncMock(return_value=0))
    monkeypatch.setattr(escalation, "notify_needs_human", notifications.notify_needs_human)
    monkeypatch.setattr(social_inbound, "reply_delay_seconds", lambda agent: 0)


def resources(client, *, provider="instagram", account="111", human_agent=True):
    customer_response = client.post("/api/clients", json={"name": f"Shop {account}", "is_active": True})
    assert customer_response.status_code == 201, customer_response.text
    customer = customer_response.json()
    assert client.put("/api/providers/openai", json={"api_key": "test-key"}).status_code == 200
    agent_response = client.post("/api/agents", json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Support", "instructions": "", "personality": "", "is_active": True, "reply_delay_min_seconds": 0, "reply_delay_max_seconds": 0})
    assert agent_response.status_code == 201, agent_response.text
    with TestingSession() as db:
        agent = db.get(Agent, agent_response.json()["id"])
        channel = SocialChannel(agency_id=agent.agency_id, client_id=agent.client_id, agent_id=agent.id,
            provider=provider, app_id="999", external_account_id=account, display_name="Shop", status="connected",
            encrypted_access_token=encrypt_secret("test-token"), encrypted_app_secret=encrypt_secret(SECRET),
            is_enabled=True, human_agent_enabled=human_agent, connection_source="manual",
            last_connected_at=now_utc().replace(microsecond=0), webhook_verify_token="test-verify")
        db.add(channel)
        db.commit()
        return SimpleNamespace(channel_id=channel.id, client_id=channel.client_id, agent_id=agent.id,
            agency_id=agent.agency_id, account=account, provider=provider)


def event(resource, mid, *, text="Hello", person=PERSON, occurred=None, echo=False, app_id=None):
    occurred = occurred or now_utc().replace(microsecond=0)
    message = {"mid": mid, "text": text}
    if echo:
        message["is_echo"] = True
    if app_id:
        message["app_id"] = app_id
    return {"sender": {"id": resource.account if echo else person},
        "recipient": {"id": person if echo else resource.account},
        "timestamp": int(occurred.timestamp() * 1000), "message": message}


def envelope(resource, *events, batch_time=None):
    return {"object": "instagram" if resource.provider == "instagram" else "page", "entry": [
        {"id": resource.account, "time": batch_time or int(now_utc().timestamp()), "messaging": list(events)}]}


def signed_post(client, resource, payload, *, secret=SECRET):
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(f"/api/public/social/channels/{resource.channel_id}/webhook", content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})


def inbound(db, resource, *, mid="incoming-1", person=PERSON, occurred=None):
    channel = db.get(SocialChannel, resource.channel_id)
    asyncio.run(social_inbound.process_event(db, channel, event(resource, mid, person=person, occurred=occurred)))
    return db.scalar(select(Conversation).where(Conversation.social_channel_id == channel.id,
        Conversation.external_chat_id == person).order_by(Conversation.created_at.desc()).limit(1))


def queue(db, conversation, content="Reply", *, human=True):
    conversation.mode = "human" if human else "ai"
    message = Message(conversation_id=conversation.id, role="assistant", sender_type="human" if human else "ai",
                      sender_name="Operator" if human else "Support", content=content)
    db.add(message)
    social_delivery.queue_message(db, conversation, message)
    db.commit()
    return message


def receipt(resource, mid, *, read=False):
    return {"sender": {"id": PERSON}, "recipient": {"id": resource.account},
        "timestamp": int(now_utc().timestamp() * 1000), "read" if read else "delivery": {"mid": mid}}


def test_signed_webhook_is_durable_before_any_ai_or_send(authenticated_client):
    resource = resources(authenticated_client)
    payload = envelope(resource, event(resource, "incoming-1"))
    assert signed_post(authenticated_client, resource, payload, secret="wrong").status_code == 403
    assert signed_post(authenticated_client, resource, payload).status_code == 200
    with TestingSession() as db:
        saved = db.scalars(select(SocialWebhookEvent)).all()
        assert len(saved) == 1 and saved[0].status == "pending"
        assert db.scalar(select(func.count(Conversation.id))) == 0
    whatsapp_inbound.run_completion.assert_not_awaited()
    social_graph.send_text.assert_not_awaited()
    with TestingSession() as db:
        assert asyncio.run(social_inbound.process_pending(db)) == 1
        conversation = db.scalar(select(Conversation))
        assert conversation.channel == "instagram"
        assert conversation.social_reply_due_at is not None
        assert db.scalar(select(SocialWebhookEvent)).status == "processed"
    whatsapp_inbound.run_completion.assert_not_awaited()


def test_message_retries_do_not_create_a_new_case_after_resolution(authenticated_client):
    resource = resources(authenticated_client)
    incoming = event(resource, "stable-mid")
    assert signed_post(authenticated_client, resource, envelope(resource, incoming, batch_time=100)).status_code == 200
    with TestingSession() as db:
        asyncio.run(social_inbound.process_pending(db))
        original = db.scalar(select(Conversation))
        set_status(db, original, "resolved")
        db.commit()
        original_id = original.id
    assert signed_post(authenticated_client, resource, envelope(resource, incoming, batch_time=200)).status_code == 200
    with TestingSession() as db:
        assert asyncio.run(social_inbound.process_pending(db)) == 0
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), incoming))
        assert db.scalar(select(func.count(Conversation.id))) == 1
        assert db.get(Conversation, original_id).status == "resolved"
        assert db.scalar(select(func.count(Message.id)).where(Message.external_message_id == "stable-mid")) == 1


def test_social_digit_ids_are_account_scoped_and_never_phone_numbers(authenticated_client):
    first = resources(authenticated_client, account="111")
    second = resources(authenticated_client, account="222")
    with TestingSession() as db:
        a = inbound(db, first)
        b = inbound(db, second)
        assert a.contact_id != b.contact_id
        assert db.get(Contact, a.contact_id).phone is None
        assert db.get(Contact, b.contact_id).phone is None
        identities = db.scalars(select(ContactIdentity).where(ContactIdentity.external_user_id == PERSON)).all()
        assert {(i.provider, i.external_account_id) for i in identities} == {("instagram", "111"), ("instagram", "222")}


def test_contact_merge_preserves_both_phone_aliases_and_social_identity(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        primary = resolve_contact(db, resource.client_id, phone="573000000001", name="Primary")
        merged = resolve_contact(db, resource.client_id, phone="573000000002", name="Second")
        db.add(ContactIdentity(client_id=resource.client_id, contact_id=merged.id, provider="instagram", external_account_id="111", external_user_id=PERSON))
        db.commit()
        survivor = primary.id
        merge_contacts(db, primary, merged)
        db.commit()
    with TestingSession() as db:
        for phone in ("573000000001", "573000000002"):
            assert resolve_contact(db, resource.client_id, phone=phone).id == survivor
        assert resolve_contact(db, resource.client_id, provider="instagram", external_account_id="111", external_user_id=PERSON).id == survivor
        assert db.scalar(select(func.count(Contact.id))) == 1


def test_human_route_queues_before_send_and_receipts_update_delivery(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        conversation.mode = "human"
        db.commit()
        conversation_id = conversation.id
    response = authenticated_client.post(f"/api/conversations/{conversation_id}/reply", json={"content": "How can I help?"})
    assert response.status_code == 200, response.text
    outbound = response.json()["messages"][-1]
    assert outbound["delivery_status"] == "pending"
    social_graph.send_text.assert_not_awaited()
    with TestingSession() as db:
        asyncio.run(social_delivery.process_outbox(db))
        message = db.get(Message, outbound["id"])
        assert message.delivery_status == "sent"
        assert db.get(Conversation, conversation_id).waiting_since is None
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), receipt(resource, message.external_message_id, read=True)))
        assert message.delivery_status == "read"
    social_graph.send_text.assert_awaited_once()


def test_utf8_multipart_needs_receipts_for_every_part(authenticated_client):
    resource = resources(authenticated_client)
    text = "🌍 mañana e\u0301 " * 230
    with TestingSession() as db:
        conversation = inbound(db, resource)
        message = queue(db, conversation, text)
        parts = db.scalars(select(SocialOutbox).order_by(SocialOutbox.part)).all()
        assert len(parts) > 2
        assert "".join(part.payload["text"] for part in parts) == text
        assert all(0 < len(part.payload["text"].encode("utf-8")) <= 1000 for part in parts)
        asyncio.run(social_delivery.process_outbox(db))
        assert message.delivery_status == "sent"
        channel = db.get(SocialChannel, resource.channel_id)
        asyncio.run(social_inbound.process_event(db, channel, receipt(resource, parts[0].external_message_id, read=True)))
        assert message.delivery_status == "sent"
        for part in parts[1:]:
            asyncio.run(social_inbound.process_event(db, channel, receipt(resource, part.external_message_id, read=True)))
        assert message.delivery_status == "read"


def test_a_late_receipt_cannot_hide_a_failed_part(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    send = AsyncMock(side_effect=["part-one", HTTPException(400, "Attachment refused")])
    monkeypatch.setattr(social_graph, "send_text", send)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        message = queue(db, conversation, "x" * 1500)
        asyncio.run(social_delivery.process_outbox(db))
        assert message.delivery_status == "failed"
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), receipt(resource, "part-one", read=True)))
        assert message.delivery_status == "failed"
        assert message.delivery_error


def test_cached_conversation_cannot_send_after_another_session_takes_over(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as worker:
        conversation = inbound(worker, resource)
        message = queue(worker, conversation, human=False)
        assert conversation.social_channel.status == "connected"
        with TestingSession() as operator:
            current = operator.get(Conversation, conversation.id)
            current.mode = "human"
            operator.commit()
        assert conversation.mode == "ai"
        asyncio.run(social_delivery.process_outbox(worker))
        worker.refresh(message)
        assert message.delivery_status == "failed"
    social_graph.send_text.assert_not_awaited()


def test_cached_channel_revocation_prevents_delivery(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as worker:
        conversation = inbound(worker, resource)
        message = queue(worker, conversation)
        assert conversation.social_channel.status == "connected"
        with TestingSession() as operator:
            channel = operator.get(SocialChannel, resource.channel_id)
            channel.is_enabled = False
            channel.status = "disconnected"
            operator.commit()
        asyncio.run(social_delivery.process_outbox(worker))
        assert message.delivery_status == "failed"
    social_graph.send_text.assert_not_awaited()


def test_revoked_provider_token_requires_reconnection(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    monkeypatch.setattr(social_graph, "send_text", AsyncMock(side_effect=HTTPException(401, "Authorization revoked")))
    with TestingSession() as db:
        conversation = inbound(db, resource)
        message = queue(db, conversation)
        asyncio.run(social_delivery.process_outbox(db))
        assert message.delivery_status == "failed"
        channel = db.get(SocialChannel, resource.channel_id)
        assert channel.status == "reauthorization_required"
        assert not social_policy.window_fields(conversation)["human_reply_window_open"]
    response = authenticated_client.post(f"/api/social/instagram/channels/{resource.client_id}/connect")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "connected"


def test_ambiguous_network_result_is_not_retried(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    send = AsyncMock(side_effect=HTTPException(502, "Connection lost after request"))
    monkeypatch.setattr(social_graph, "send_text", send)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        message = queue(db, conversation)
        asyncio.run(social_delivery.process_outbox(db))
        asyncio.run(social_delivery.process_outbox(db))
        row = db.scalar(select(SocialOutbox))
        assert row.status == "unknown" and row.attempts == 1
        assert message.delivery_status == "unknown"
        assert conversation.waiting_since is not None
    send.assert_awaited_once()


def test_echo_for_a_retried_old_row_waits_for_its_current_send(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        message = queue(db, conversation, "Our reply", human=False)
        row = db.scalar(select(SocialOutbox))
        row.status = "sending"
        row.created_at = now_utc() - timedelta(minutes=4)
        row.locked_until = now_utc() + timedelta(minutes=1)
        db.commit()
        echo = event(resource, "echo-result", text="Our reply", echo=True, app_id="999")
        with pytest.raises(social_inbound.WaitForDelivery):
            asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), echo))
        row.external_message_id = message.external_message_id = "echo-result"
        row.status = message.delivery_status = "sent"
        db.commit()
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), echo))
        assert db.scalar(select(func.count(Message.id)).where(Message.kind == "message")) == 2
        assert conversation.mode == "ai"


def test_native_human_echo_pauses_ai_and_clears_waiting(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource, occurred=now_utc().replace(microsecond=0) - timedelta(seconds=2))
        assert conversation.social_reply_due_at and conversation.waiting_since
        native = event(resource, "native-reply", text="A person replied", echo=True)
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), native))
        assert conversation.mode == "human"
        assert conversation.social_reply_due_at is None
        assert conversation.waiting_since is None
        assert db.scalar(select(Message).where(Message.external_message_id == "native-reply")).sender_type == "human"
        asyncio.run(social_worker.process_replies(db))
    whatsapp_inbound.run_completion.assert_not_awaited()


def test_human_agent_window_never_authorizes_automated_replies(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource, occurred=now_utc() - timedelta(days=2))
        conversation.mode = "human"
        assert social_policy.require_reply(conversation, human=True) is True
        with pytest.raises(HTTPException):
            social_policy.require_reply(conversation, human=False)
        conversation.social_last_inbound_at = now_utc() - timedelta(days=8)
        with pytest.raises(HTTPException):
            social_policy.require_reply(conversation, human=True)
        conversation.social_last_inbound_at = now_utc() - timedelta(days=2)
        conversation.social_channel.human_agent_enabled = False
        with pytest.raises(HTTPException):
            social_policy.require_reply(conversation, human=True)


def test_other_agency_cannot_read_or_reply_to_social_conversation(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        conversation.mode = "human"
        db.commit()
        conversation_id = conversation.id
    monkeypatch.setattr(get_settings(), "allow_multi_agency", True)
    result = authenticated_client.post("/api/auth/register", json={"agency_name": "Other", "name": "Other operator", "email": "other@runtime.example", "password": "another-long-password"})
    assert result.status_code == 201, result.text
    assert authenticated_client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert authenticated_client.post(f"/api/conversations/{conversation_id}/reply", json={"content": "Unauthorized"}).status_code == 404
    social_graph.send_text.assert_not_awaited()


def test_imported_history_stays_resolved_and_does_not_open_a_reply_window(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        channel = db.get(SocialChannel, resource.channel_id)
        historical = event(resource, "historic-one", occurred=channel.last_connected_at - timedelta(days=3))
        historical["_historical"] = True
        asyncio.run(social_inbound.process_event(db, channel, historical))
        conversation = db.scalar(select(Conversation))
        assert conversation.status == "resolved" and conversation.mode == "human"
        assert conversation.social_last_inbound_at is None and conversation.social_reply_due_at is None
        assert not social_policy.window_fields(conversation)["human_reply_window_open"]
        assert db.scalar(select(Message)).is_historical is True
        after_connection = event(resource, "after-cutoff", occurred=channel.last_connected_at + timedelta(seconds=1))
        after_connection["_historical"] = True
        asyncio.run(social_inbound.process_event(db, channel, after_connection))
        assert db.scalar(select(func.count(Message.id))) == 1
        imported_id = conversation.id
        live = inbound(db, resource, mid="new-live-message")
        assert live.id != imported_id and live.status == "open"
        assert live.contact_id == conversation.contact_id
        assert live.social_last_inbound_at and live.social_reply_due_at
    notifications.notify_needs_human.assert_not_awaited()
    whatsapp_inbound.run_completion.assert_not_awaited()


def test_ai_worker_generates_once_and_delivers_through_outbox(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        assert asyncio.run(social_worker.process_replies(db)) == 1
        outbound = db.scalar(select(Message).where(Message.sender_type == "ai"))
        assert outbound and outbound.delivery_status == "pending"
        social_graph.send_text.assert_not_awaited()
        assert conversation.social_reply_due_at is None
        assert asyncio.run(social_worker.process_replies(db)) == 0
        assert asyncio.run(social_delivery.process_outbox(db)) == 1
        assert outbound.delivery_status == "sent"
    whatsapp_inbound.run_completion.assert_awaited_once()
    social_graph.send_text.assert_awaited_once()


def test_human_takeover_during_generation_discards_the_ai_result(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        conversation = inbound(db, resource)
        conversation_id = conversation.id

        async def complete_after_takeover(*args, **kwargs):
            with TestingSession() as operator:
                current = operator.get(Conversation, conversation_id)
                current.mode = "human"
                operator.commit()
            return Completion(text="This late answer must not be sent.")

        completion = AsyncMock(side_effect=complete_after_takeover)
        monkeypatch.setattr(whatsapp_inbound, "run_completion", completion)
        asyncio.run(social_worker.process_replies(db))
        db.refresh(conversation)
        assert conversation.mode == "human"
        assert db.scalar(select(func.count(SocialOutbox.id))) == 0
        assert db.scalar(select(func.count(Message.id)).where(Message.sender_type == "ai")) == 0
    completion.assert_awaited_once()
    social_graph.send_text.assert_not_awaited()


def test_standby_messages_are_visible_but_do_not_trigger_ai(authenticated_client):
    resource = resources(authenticated_client)
    standby = event(resource, "standby-message")
    standby["_standby"] = True
    with TestingSession() as db:
        asyncio.run(social_inbound.process_event(db, db.get(SocialChannel, resource.channel_id), standby))
        conversation = db.scalar(select(Conversation))
        assert conversation.social_thread_owned is False
        assert social_policy.window_fields(conversation)["reply_block_reason"] == "another_app_controls_conversation"
        assert db.scalar(select(func.count(Message.id)).where(Message.sender_type == "visitor")) == 1
        asyncio.run(social_worker.process_replies(db))
        assert db.scalar(select(func.count(SocialOutbox.id))) == 0
    whatsapp_inbound.run_completion.assert_not_awaited()


@pytest.mark.parametrize("delivery_fails", [False, True])
def test_escalation_waits_for_the_durable_farewell_before_human_handover(authenticated_client, monkeypatch, delivery_fails):
    resource = resources(authenticated_client)

    async def complete_with_escalation(*args, **kwargs):
        tool = next(spec for spec in kwargs["extra_specs"] if spec.name == "escalate_to_human")
        result, failed = tool.handler({"trigger": "human_request", "reason": "The visitor requested a person."})
        assert not failed and "registered" in result
        return Completion(text="A person will continue this conversation.")

    monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(side_effect=complete_with_escalation))
    if delivery_fails:
        monkeypatch.setattr(social_graph, "send_text", AsyncMock(side_effect=HTTPException(400, "Message rejected")))
    with TestingSession() as db:
        db.add(Team(client_id=resource.client_id, name="Support", is_default=True, channels=["instagram"]))
        db.commit()
        conversation = inbound(db, resource)
        conversation_id = conversation.id
        assert asyncio.run(social_worker.process_replies(db)) == 1
        assert conversation.mode == "ai"
        assert conversation.social_pending_escalation["message_id"]
        farewell = db.scalar(select(Message).where(Message.sender_type == "ai"))
        assert farewell.delivery_status == "pending"
        assert asyncio.run(social_worker.complete_escalations(db)) == 0
        assert asyncio.run(social_worker.process_replies(db)) == 0
        notifications.notify_needs_human.assert_not_awaited()
    # The handover survives a worker/session restart, including failed delivery.
    with TestingSession() as db:
        assert asyncio.run(social_delivery.process_outbox(db)) == 1
        assert asyncio.run(social_worker.complete_escalations(db)) == 1
        conversation = db.get(Conversation, conversation_id)
        assert conversation.mode == "human"
        assert conversation.social_pending_escalation is None
        assert conversation.social_reply_due_at is None
        assert db.scalar(select(Message.delivery_status).where(Message.sender_type == "ai")) == ("failed" if delivery_fails else "sent")
        assert asyncio.run(social_worker.complete_escalations(db)) == 0
    notifications.notify_needs_human.assert_awaited_once()
    whatsapp_inbound.run_completion.assert_awaited_once()
    social_graph.send_text.assert_awaited_once()


@pytest.mark.parametrize("failure", ["provider_exception", "empty_reply", "missing_credentials"])
def test_failed_ai_reply_hands_over_and_alerts_a_person_without_replaying(authenticated_client, monkeypatch, failure):
    resource = resources(authenticated_client)
    if failure == "provider_exception":
        monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(side_effect=RuntimeError("Provider failed with private diagnostic details")))
    elif failure == "empty_reply":
        monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(return_value=Completion(text="")))
    with TestingSession() as db:
        conversation = inbound(db, resource)
        if failure == "missing_credentials":
            db.delete(db.scalar(select(ProviderCredential).where(ProviderCredential.agency_id == resource.agency_id)))
            db.commit()
        assert asyncio.run(social_worker.process_replies(db)) == 1
        db.refresh(conversation)
        assert conversation.mode == "human"
        assert conversation.social_reply_due_at is None
        assert conversation.social_reply_claimed_until is None
        assert db.scalar(select(func.count(SocialOutbox.id))) == 0
        assert asyncio.run(social_worker.process_replies(db)) == 0
        activity = db.scalars(select(Message).where(Message.kind == "activity")).all()
        assert activity and all("private diagnostic" not in item.content for item in activity)
    notifications.notify_needs_human.assert_awaited_once()
    if failure == "missing_credentials":
        whatsapp_inbound.run_completion.assert_not_awaited()
    else:
        whatsapp_inbound.run_completion.assert_awaited_once()
    social_graph.send_text.assert_not_awaited()


def test_two_attachments_are_preserved_on_one_incoming_message_and_not_duplicated(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    download = AsyncMock(side_effect=[(b"first-image", "image/jpeg"), (b"second-image", "image/png")])
    monkeypatch.setattr(social_inbound, "fetch_inbound_media", download)
    incoming = event(resource, "two-attachments", text="Please compare these pictures.")
    incoming["message"]["attachments"] = [
        {"type": "image", "payload": {"url": "https://scontent.cdninstagram.com/first.jpg"}},
        {"type": "image", "payload": {"url": "https://scontent.cdninstagram.com/second.png"}},
    ]
    with TestingSession() as db:
        channel = db.get(SocialChannel, resource.channel_id)
        channel.agent.image_enabled = False
        db.commit()
        asyncio.run(social_inbound.process_event(db, channel, incoming))
        asyncio.run(social_inbound.process_event(db, channel, incoming))
        messages = db.scalars(select(Message).where(Message.sender_type == "visitor")).all()
        assert len(messages) == 1
        attachments = db.scalars(select(MessageAttachment).where(MessageAttachment.message_id == messages[0].id)).all()
        assert {item.data for item in attachments} == {b"first-image", b"second-image"}
        assert {item.mime for item in attachments} == {"image/jpeg", "image/png"}
        assert len(attachments) == 2
        assert messages[0].content.startswith("Please compare these pictures.")
    assert download.await_count == 2
    whatsapp_inbound.run_completion.assert_not_awaited()


def test_inbound_after_token_revocation_remains_visible_and_needs_a_person(authenticated_client):
    resource = resources(authenticated_client)
    with TestingSession() as db:
        channel = db.get(SocialChannel, resource.channel_id)
        channel.status = "reauthorization_required"
        db.commit()
    response = signed_post(authenticated_client, resource, envelope(resource, event(resource, "after-revocation")))
    assert response.status_code == 200, response.text
    with TestingSession() as db:
        assert asyncio.run(social_inbound.process_pending(db)) == 1
        conversation = db.scalar(select(Conversation))
        assert conversation and conversation.mode == "human"
        assert conversation.social_reply_due_at is None
        assert db.scalar(select(func.count(Message.id)).where(Message.sender_type == "visitor")) == 1
        assert social_policy.window_fields(conversation)["reply_block_reason"] == "authorization_expired"
        assert asyncio.run(social_worker.process_replies(db)) == 0
        assert db.scalar(select(func.count(SocialOutbox.id))) == 0
    notifications.notify_needs_human.assert_awaited_once()
    whatsapp_inbound.run_completion.assert_not_awaited()
