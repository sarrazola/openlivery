"""The delayed WhatsApp reply: a burst of visitor messages gets one answer.

These tests drive the service layer directly (not the HTTP endpoint) so the
debounce timers run inside a single asyncio loop the test controls.
"""

import asyncio
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Agent, Conversation, Message, WhatsAppChannel
from app.services import whatsapp_inbound as inbound_service
# Bound at import time, before the autouse fixture in conftest patches it away.
from app.services.whatsapp_inbound import reply_delay_seconds
from app.services.ai import Completion


def _setup_channel(client: TestClient) -> None:
    customer = client.post(
        "/api/clients",
        json={
            "name": "Sol Store",
            "industry": "retail_ecommerce",
            "is_active": True,
        },
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"],
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "name": "Sol Advisor",
            "instructions": "Help the customers.",
            "personality": "Friendly",
            "is_active": True,
        },
    ).json()
    assert client.put(
        f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}
    ).status_code == 200


def _inbound(external_message_id: str, text: str) -> inbound_service.InboundMessage:
    return inbound_service.InboundMessage(
        external_message_id=external_message_id,
        external_chat_id="573001112233@s.whatsapp.net",
        sender_name="Cliente",
        text=text,
    )


async def _process(db, channel, message: inbound_service.InboundMessage):
    return await inbound_service.process_inbound(
        db,
        channel,
        message,
        conversation_channel="whatsapp",
        channel_fk_field="whatsapp_channel_id",
    )


def test_burst_is_answered_with_a_single_reply(authenticated_client: TestClient, monkeypatch):
    _setup_channel(authenticated_client)
    monkeypatch.setattr(inbound_service, "reply_delay_seconds", lambda agent: 0.15)
    completion = AsyncMock(return_value=Completion(text="One combined answer"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)
    send = AsyncMock(return_value="wamid-out-1")
    monkeypatch.setattr(inbound_service, "send_channel_message", send)

    db = SessionLocal()
    try:
        channel = db.scalar(select(WhatsAppChannel))

        async def scenario():
            first = await _process(db, channel, _inbound("wa-1", "domi"))
            assert first.accepted and first.reply is None
            second = await _process(db, channel, _inbound("wa-2", "gracias"))
            assert second.accepted and second.reply is None
            await asyncio.sleep(0.5)

        asyncio.run(scenario())

        assert completion.await_count == 1
        prompt_messages = completion.await_args.args[4]
        user_turns = [m["content"] for m in prompt_messages if m["role"] == "user"]
        assert user_turns == ["domi", "gracias"]

        send.assert_awaited_once()
        assert send.await_args.args[2] == "One combined answer"

        replies = db.scalars(select(Message).where(Message.role == "assistant")).all()
        assert len(replies) == 1
        assert replies[0].content == "One combined answer"
        assert replies[0].external_message_id == "wamid-out-1"
    finally:
        db.close()


def test_no_reply_when_operator_takes_over_during_the_window(
    authenticated_client: TestClient, monkeypatch
):
    _setup_channel(authenticated_client)
    monkeypatch.setattr(inbound_service, "reply_delay_seconds", lambda agent: 0.15)
    completion = AsyncMock(return_value=Completion(text="Should never be sent"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)
    send = AsyncMock(return_value="wamid-out-1")
    monkeypatch.setattr(inbound_service, "send_channel_message", send)

    db = SessionLocal()
    try:
        channel = db.scalar(select(WhatsAppChannel))

        async def scenario():
            await _process(db, channel, _inbound("wa-1", "quiero hablar con alguien"))
            conversation = db.scalar(select(Conversation))
            conversation.mode = "human"
            db.commit()
            await asyncio.sleep(0.5)

        asyncio.run(scenario())

        completion.assert_not_awaited()
        send.assert_not_awaited()
    finally:
        db.close()


def test_zero_delay_keeps_the_immediate_reply(authenticated_client: TestClient, monkeypatch):
    _setup_channel(authenticated_client)
    monkeypatch.setattr(inbound_service, "reply_delay_seconds", lambda agent: 0)
    completion = AsyncMock(return_value=Completion(text="Immediate answer"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)

    db = SessionLocal()
    try:
        channel = db.scalar(select(WhatsAppChannel))
        result = asyncio.run(_process(db, channel, _inbound("wa-1", "hola")))
        assert result.reply == "Immediate answer"
        assert result.outbound_message_id is not None
    finally:
        db.close()


def test_delay_is_drawn_between_the_agent_bounds():
    agent = Agent(reply_delay_min_seconds=5, reply_delay_max_seconds=10)
    draws = {reply_delay_seconds(agent) for _ in range(200)}
    assert all(5 <= d <= 10 for d in draws)
    assert len(draws) > 1

    fixed = Agent(reply_delay_min_seconds=8, reply_delay_max_seconds=8)
    assert reply_delay_seconds(fixed) == 8

    off = Agent(reply_delay_min_seconds=0, reply_delay_max_seconds=0)
    assert reply_delay_seconds(off) == 0


def test_agent_delay_bounds_are_validated(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Sol Store", "is_active": True}).json()
    base = {"client_id": customer["id"], "name": "Sol Advisor", "is_active": True}

    created = client.post("/api/agents", json=base)
    assert created.status_code == 201, created.text
    assert (created.json()["reply_delay_min_seconds"], created.json()["reply_delay_max_seconds"]) == (6, 9)

    inverted = client.post("/api/agents", json={**base, "reply_delay_min_seconds": 9, "reply_delay_max_seconds": 3})
    assert inverted.status_code == 422

    agent_id = created.json()["id"]
    assert client.patch(f"/api/agents/{agent_id}", json={"reply_delay_max_seconds": 4}).status_code == 422
    updated = client.patch(f"/api/agents/{agent_id}", json={"reply_delay_min_seconds": 2, "reply_delay_max_seconds": 4})
    assert updated.status_code == 200, updated.text
    assert (updated.json()["reply_delay_min_seconds"], updated.json()["reply_delay_max_seconds"]) == (2, 4)
    assert client.patch(f"/api/agents/{agent_id}", json={"reply_delay_min_seconds": 0, "reply_delay_max_seconds": 0}).status_code == 200
