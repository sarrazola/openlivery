"""Prompt context and tool routing, with scripted external services.

These checks do not evaluate whether a live model follows the instructions.
"""

from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import pytest

from app.services import knowledge
from app.services.tools import loop


class MondayMorning(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 14, 6, tzinfo=timezone.utc).astimezone(tz)


@pytest.mark.parametrize("language,zone,clock", [
    ("es", "America/Bogota", "lunes, 2026-09-14 01:00"),
    ("en", "America/Los_Angeles", "Sunday, 2026-09-13 23:00"),
    ("en", "UTC", "Monday, 2026-09-14 06:00"),
])
def test_prompt_weekday_uses_the_client_clock(authenticated_client, monkeypatch, language, zone, clock):
    monkeypatch.setattr(knowledge, "datetime", MondayMorning)
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Appointments", "timezone": zone}).json()
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "name": "Assistant", "prompt_language": language,
        "brief_policies": "Reception: Monday to Friday, 09:00-17:00. Online booking: 24 hours.",
    }).json()

    preview = client.get(f"/api/agents/{agent['id']}/prompt")
    assert preview.status_code == 200, preview.text
    prompt = preview.json()["prompt"]
    assert f"({zone}): {clock}." in prompt
    assert agent["brief_policies"] in prompt


@pytest.mark.parametrize("tool_failed", [False, True])
def test_future_booking_tool_runs_outside_reception_hours(authenticated_client, monkeypatch, tool_failed):
    """Exercise the conversation route and real tool loop at 01:00 local time.

    The scripted provider selects the tool; no scheduling decision is mocked
    inside the application, and the tool's result must return to the provider.
    """
    monkeypatch.setattr(knowledge, "datetime", MondayMorning)
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Appointments", "timezone": "America/Bogota"}).json()
    assert client.put("/api/providers/openai", json={"api_key": "test-key"}).status_code == 200
    policies = "Reception: Monday-Friday 09:00-17:00. Online bookings allowed 24 hours for available future slots."
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "name": "Assistant", "provider": "openai", "model": "gpt-5",
        "is_active": True, "prompt_language": "en", "brief_policies": policies,
    }).json()
    created = client.post(f"/api/agents/{agent['id']}/tools", json={
        "type": "http", "name": "book_appointment", "description": "Check a slot and record a booking if available.",
        "url": "https://appointments.example.test/bookings", "http_method": "POST",
        "body_params": [{"name": "starts_at", "type": "string", "required": True}],
    })
    assert created.status_code == 201, created.text
    requested_time = "2026-09-15T10:00:00-05:00"
    result = "HTTP 409: slot unavailable" if tool_failed else 'HTTP 201: {"booking_id":"A-123","confirmed":true}'
    endpoint = AsyncMock(return_value=(result, tool_failed))
    monkeypatch.setattr(loop, "execute_http_tool", endpoint)
    reply = "The slot is unavailable." if tool_failed else "Appointment A-123 is booked."
    provider = AsyncMock(side_effect=[
        {"output": [{"type": "function_call", "call_id": "b1", "name": "book_appointment",
                     "arguments": json.dumps({"starts_at": requested_time})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": reply}]}]},
    ])
    monkeypatch.setattr(loop, "_post_json", provider)
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    response = client.post(f"/api/conversations/{conversation['id']}/messages", json={
        "content": "Please book the appointment for tomorrow at 10 a.m. I confirm those details.",
    })
    assert response.status_code == 200, response.text
    endpoint.assert_awaited_once()
    assert endpoint.await_args.args[1] == {"starts_at": requested_time}
    assert provider.await_count == 2
    sent = provider.await_args_list[0].args[2]
    assert "Monday, 2026-09-14 01:00" in sent["instructions"]
    assert policies in sent["instructions"]
    assert "future dates outside those hours when business policies allow it" in sent["instructions"]
    assert "only after the tool that records it confirms success" in sent["instructions"]
    assert sent["tools"][0]["name"] == "book_appointment"
    returned = provider.await_args_list[1].args[2]["input"][-1]
    assert returned["type"] == "function_call_output"
    assert returned["output"] == (f"Tool call failed: {result}" if tool_failed else result)
    assistant = response.json()["messages"][-1]
    assert assistant["tool_calls"][0]["is_error"] is tool_failed
    assert assistant["tool_calls"][0]["arguments"] == {"starts_at": requested_time}
