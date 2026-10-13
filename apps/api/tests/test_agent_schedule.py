"""An agent on a schedule answers only inside its slots.

Outside them an inbound message is kept and nobody answers, like an inactive
agent, except that the agent comes back on by itself. The slots are read in
the client's timezone."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Agent, Client, WhatsAppChannel
from app.services import whatsapp_inbound as inbound_service
from app.services.ai import Completion
from app.services.availability import agent_available, on_duty
from tests.conftest import TestingSession


def _agent_on_whatsapp(client: TestClient, timezone_name: str = "UTC"):
    customer = client.post("/api/clients", json={"name": "Weekend Co", "timezone": timezone_name}).json()
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Host", "model": "gpt-4.1-mini"}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    return customer, agent


def _inbound(monkeypatch):
    completion = AsyncMock(return_value=Completion(text="Hola, soy el agente"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)
    db = TestingSession()
    try:
        channel = db.scalar(select(WhatsAppChannel))
        result = asyncio.run(inbound_service.process_inbound(
            db, channel,
            inbound_service.InboundMessage(external_message_id="wa-1", external_chat_id="573001112233@s.whatsapp.net", sender_name="Cliente", text="hola"),
            conversation_channel="whatsapp", channel_fk_field="whatsapp_channel_id",
        ))
        db.refresh(channel)
        return result, completion, channel.last_error
    finally:
        db.close()


def test_the_schedule_is_validated_and_normalized(authenticated_client: TestClient):
    customer = authenticated_client.post("/api/clients", json={"name": "Weekend Co"}).json()
    agent = authenticated_client.post("/api/agents", json={"client_id": customer["id"], "name": "Host"}).json()
    assert agent["schedule_enabled"] is False and agent["schedule_slots"] == []
    path = f"/api/agents/{agent['id']}"
    for bad in (
        [{"day": 7, "start": "09:00", "end": "22:00"}],
        [{"day": 3, "start": "22:00", "end": "09:00"}],
        [{"day": 3, "start": "9:00", "end": "22:00"}],
        [{"day": 3, "start": "09:60", "end": "22:00"}],
        [{"day": 3, "start": "09:00", "end": "25:00"}],
    ):
        assert authenticated_client.patch(path, json={"schedule_slots": bad}).status_code == 422, bad
    slots = [{"day": 3, "start": "09:00", "end": "22:00"}, {"day": 6, "start": "00:00", "end": "24:00"}]
    updated = authenticated_client.patch(path, json={"schedule_enabled": True, "schedule_slots": slots}).json()
    assert updated["schedule_enabled"] is True and updated["schedule_slots"] == slots


def test_on_duty_reads_the_slots_in_the_clients_timezone():
    agent = Agent(name="Host", schedule_enabled=True, schedule_slots=[{"day": 4, "start": "09:00", "end": "22:00"}], is_active=True)
    agent.client = Client(name="Weekend Co", timezone="America/Bogota")
    # Friday 2026-10-16 at 02:30 UTC is still Thursday 21:30 in Bogotá.
    assert on_duty(agent, datetime(2026, 10, 16, 2, 30, tzinfo=timezone.utc)) is False
    # Friday 14:00 UTC is Friday 09:00 in Bogotá: the slot opens.
    assert on_duty(agent, datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)) is True
    # Saturday 02:59 UTC is Friday 21:59 in Bogotá; a minute later the slot closes.
    assert on_duty(agent, datetime(2026, 10, 17, 2, 59, tzinfo=timezone.utc)) is True
    assert on_duty(agent, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)) is False
    agent.schedule_enabled = False
    assert on_duty(agent, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)) is True
    agent.is_active = False
    assert agent_available(agent) is False


def test_outside_the_schedule_a_message_is_kept_and_nobody_answers(authenticated_client: TestClient, monkeypatch):
    customer, agent = _agent_on_whatsapp(authenticated_client)
    other_day = (datetime.now(timezone.utc).weekday() + 3) % 7
    authenticated_client.patch(f"/api/agents/{agent['id']}", json={"schedule_enabled": True, "schedule_slots": [{"day": other_day, "start": "09:00", "end": "22:00"}]})

    result, completion, last_error = _inbound(monkeypatch)

    assert result.accepted and result.reply is None
    completion.assert_not_awaited()
    assert not last_error, "off duty is not a channel error"
    conversations = authenticated_client.get("/api/conversations").json()
    assert any(c["id"] == str(result.conversation_id) for c in conversations)


def test_inside_the_schedule_the_agent_answers(authenticated_client: TestClient, monkeypatch):
    customer, agent = _agent_on_whatsapp(authenticated_client)
    today = datetime.now(timezone.utc).weekday()
    authenticated_client.patch(f"/api/agents/{agent['id']}", json={"schedule_enabled": True, "schedule_slots": [{"day": today, "start": "00:00", "end": "24:00"}]})

    result, completion, _ = _inbound(monkeypatch)

    assert result.reply is not None
    completion.assert_awaited()
