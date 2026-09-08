"""Messages with hidden phone numbers must still reach the inbox and get replies."""

import asyncio
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.models import Contact, ContactIdentity, Conversation, Message, WhatsAppCloudChannel, now_utc
from app.services import whatsapp_cloud, whatsapp_coexistence as coex, whatsapp_inbound
from app.services.ai import Completion
from app.services.contacts import normalize_phone
from app.services.whatsapp_identity import resolve_peer_contact
from conftest import TestingSession
from test_whatsapp_cloud import _setup_channel, _post_signed, _webhook_payload

BSUID = "CO.123456789012345Ab"
PHONE = "573001112233"
BUSINESS = "573009998877"


def incoming(mid, identity=BSUID, phone=None):
    return {"id": mid, "from_user_id": identity, **({"from": phone} if phone else {}),
        "timestamp": str(int(now_utc().timestamp())), "type": "text", "text": {"body": "Hello"}}


def setup(client, monkeypatch):
    customer, agent, channel = _setup_channel(client)
    completion = AsyncMock(return_value=Completion(text="Welcome!"))
    monkeypatch.setattr(whatsapp_inbound, "run_completion", completion)
    graph = AsyncMock(return_value=httpx.Response(200, json={"messages": [{"id": "wamid.reply"}]}))
    monkeypatch.setattr(whatsapp_cloud, "_graph_request", graph)
    monkeypatch.setattr(whatsapp_inbound, "notify_needs_human", AsyncMock())
    with TestingSession() as db:
        stored = db.get(WhatsAppCloudChannel, uuid.UUID(channel["id"]))
        stored.coexistence = True
        stored.status = "connected"
        stored.phone_number = BUSINESS
        db.commit()
    return channel, completion, graph


@pytest.mark.parametrize("identity,field", [(BSUID, "from_user_id"), ("CO.ENT.123456789012345Ab", "from_parent_user_id")])
def test_hidden_phone_receives_replies_and_deduplicates(authenticated_client, monkeypatch, identity, field):
    channel, completion, graph = setup(authenticated_client, monkeypatch)
    message = incoming("wamid.hidden", identity)
    message[field] = message.pop("from_user_id")
    contacts = [{"user_id" if field == "from_user_id" else "parent_user_id": identity, "profile": {"name": "Maria"}}]
    payload = _webhook_payload([message], contacts=contacts)
    assert _post_signed(authenticated_client, channel["id"], payload).status_code == 200
    assert _post_signed(authenticated_client, channel["id"], payload).status_code == 200
    assert completion.await_count == 1
    sent = [call.kwargs["json"] for call in graph.await_args_list if call.kwargs.get("json", {}).get("type") == "text"]
    assert len(sent) == 1 and sent[0]["recipient"] == identity and "to" not in sent[0]
    with TestingSession() as db:
        conv = db.scalar(select(Conversation))
        assert conv.external_chat_id == identity and conv.contact_name == "Maria"
        assert conv.contact.phone is None
        assert db.scalar(select(ContactIdentity)).external_user_id == identity
        messages = db.scalars(select(Message).order_by(Message.created_at)).all()
        assert [m.sender_type for m in messages] == ["visitor", "ai"]
        assert messages[-1].external_message_id == "wamid.reply"


@pytest.mark.parametrize("phone_first", [True, False])
def test_identity_transitions_preserve_case_and_phone_takeover(authenticated_client, monkeypatch, phone_first):
    channel, completion, graph = setup(authenticated_client, monkeypatch)
    for index, phone in enumerate(([PHONE, None] if phone_first else [None, PHONE])):
        payload = _webhook_payload([incoming(f"wamid.in-{index}", phone=phone)])
        assert _post_signed(authenticated_client, channel["id"], payload).status_code == 200
    with TestingSession() as db:
        assert len(db.scalars(select(Contact)).all()) == 1
        conv = db.scalar(select(Conversation))
        assert conv.contact.phone == PHONE
        assert len(db.scalars(select(Conversation)).all()) == 1
        conv_id = conv.id
        echo = {"id": "wamid.phone", "from": BUSINESS, "to_user_id": BSUID,
            "timestamp": str(int(now_utc().timestamp())), "type": "text", "text": {"body": "I will help"}}
        stored = db.get(WhatsAppCloudChannel, uuid.UUID(channel["id"]))
        body = {"metadata": {"phone_number_id": "111"}, "message_echoes": [echo]}
        assert coex.accept_change(db, stored, "smb_message_echoes", body)
        db.refresh(conv)
        assert conv.external_chat_id == BSUID and conv.mode == "human"
        assert len(db.scalars(select(Conversation)).all()) == 1
    assert _post_signed(authenticated_client, channel["id"], _webhook_payload([incoming("wamid.after-takeover")])).status_code == 200
    assert completion.await_count == 2
    with TestingSession() as db:
        conv = db.get(Conversation, conv_id)
        assert conv.mode == "human"
        assert db.scalar(select(Message).where(Message.external_message_id == "wamid.phone")).sender_type == "human"
        assert db.scalar(select(Message).where(Message.external_message_id == "wamid.after-takeover")).conversation_id == conv_id


@pytest.mark.parametrize("recipient", [BSUID, "CO.ENT.123456789012345Ab", PHONE])
def test_all_outbound_types_use_the_correct_address_field(monkeypatch, recipient):
    graph = AsyncMock(return_value=httpx.Response(200, json={"messages": [{"id": "out"}]}))
    monkeypatch.setattr(whatsapp_cloud, "_graph_request", graph)
    asyncio.run(whatsapp_cloud.send_text("token", "111", recipient, "Hello"))
    asyncio.run(whatsapp_cloud.send_reaction("token", "111", recipient, "wamid.in", "👍"))
    asyncio.run(whatsapp_cloud.send_media("token", "111", recipient, "image", "media-1"))
    key = "to" if recipient == PHONE else "recipient"
    other = "recipient" if key == "to" else "to"
    assert graph.await_count == 3
    for call in graph.await_args_list:
        payload = call.kwargs["json"]
        assert payload[key] == recipient and other not in payload
    if recipient != PHONE:
        assert normalize_phone(recipient) is None


def test_same_user_id_is_scoped_to_client_and_account(authenticated_client):
    _, _, data = _setup_channel(authenticated_client)
    with TestingSession() as db:
        channel = db.get(WhatsAppCloudChannel, uuid.UUID(data["id"]))
        first = resolve_peer_contact(db, channel, BSUID)
        channel.waba_id = "another-account"
        second = resolve_peer_contact(db, channel, BSUID)
        assert first.id != second.id
        assert first.phone is None and second.phone is None


def test_history_with_hidden_phone_is_imported_without_reply(authenticated_client, monkeypatch):
    channel, completion, graph = setup(authenticated_client, monkeypatch)
    body = {"metadata": {"phone_number_id": "111"}, "history": [{"threads": [
        {"context": {"user_id": BSUID}, "messages": [incoming("wamid.history")]}
    ]}]}
    with TestingSession() as db:
        stored = db.get(WhatsAppCloudChannel, uuid.UUID(channel["id"]))
        assert coex.accept_change(db, stored, "history", body)
        asyncio.run(coex.process_pending(db))
        message = db.scalar(select(Message))
        assert message and message.is_historical and message.sender_type == "visitor"
        assert message.conversation.contact.phone is None
        assert message.conversation.status == "resolved"
    completion.assert_not_awaited()
    graph.assert_not_awaited()
