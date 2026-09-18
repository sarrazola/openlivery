"""A client with several WhatsApp lines and social accounts."""

import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import TestingSession

from app.config import get_settings
from app.models import Conversation, WhatsAppChannel
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service
from test_whatsapp_cloud import APP_SECRET, _post_signed, _webhook_payload


def _client_with_agents(client: TestClient, name: str = "Rent a Car") -> tuple[dict, dict, dict]:
    customer = client.post("/api/clients", json={"name": name, "is_active": True}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})

    def agent(agent_name: str) -> dict:
        return client.post(
            "/api/agents",
            json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini",
                  "name": agent_name, "instructions": "", "personality": "", "is_active": True},
        ).json()

    return customer, agent("Sales"), agent("Support")


def _bridge_headers() -> dict:
    return {"X-Bridge-Token": get_settings().whatsapp_bridge_token}


def _status(client: TestClient, channel_id: str, phone: str, status: str = "connected") -> None:
    assert client.put(
        f"/api/internal/whatsapp/channels/{channel_id}/status",
        json={"status": status, "phone_number": phone, "display_name": "Shop"},
        headers=_bridge_headers(),
    ).status_code == 204
    if status == "connected":
        assert client.put(
            f"/api/internal/whatsapp/channels/{channel_id}/auth",
            json={"auth_state": {"creds": phone}},
            headers=_bridge_headers(),
        ).status_code == 204


def test_client_can_have_several_qr_lines_each_with_its_own_agent(authenticated_client: TestClient):
    client = authenticated_client
    customer, sales, support = _client_with_agents(client)

    # The legacy shape keeps working: configuring "the client's line" creates the first one.
    first = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": sales["id"], "label": "Sales"})
    assert first.status_code == 200, first.text
    second = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": support["id"]})
    assert second.status_code == 201, second.text
    third = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": sales["id"], "label": "Weekend"})
    assert third.status_code == 201

    lines = client.get(f"/api/whatsapp/clients/{customer['id']}/channels").json()
    assert [row["label"] for row in lines] == ["Sales", None, "Weekend"]
    assert [row["agent_id"] for row in lines] == [sales["id"], support["id"], sales["id"]]

    # Addressing by client id still means the first line; by line id, that line.
    assert client.get(f"/api/whatsapp/channels/{customer['id']}").json()["id"] == first.json()["id"]
    renamed = client.put(f"/api/whatsapp/channels/{second.json()['id']}", json={"agent_id": support["id"], "label": "Support desk"})
    assert renamed.json()["label"] == "Support desk"
    assert client.get(f"/api/whatsapp/channels/{first.json()['id']}").json()["label"] == "Sales"

    # Clearing the label with an empty string; omitting it keeps it.
    assert client.put(f"/api/whatsapp/channels/{second.json()['id']}", json={"agent_id": support["id"], "label": ""}).json()["label"] is None
    assert client.put(f"/api/whatsapp/channels/{first.json()['id']}", json={"agent_id": sales["id"]}).json()["label"] == "Sales"

    # An agent of another client is refused for any line.
    other, other_agent, _ = _client_with_agents(client, "Other")
    assert client.put(f"/api/whatsapp/channels/{first.json()['id']}", json={"agent_id": other_agent["id"]}).status_code == 400
    assert client.post(f"/api/whatsapp/clients/{other['id']}/channels", json={"agent_id": sales["id"]}).status_code == 400


def test_same_phone_is_refused_on_a_second_line(authenticated_client: TestClient):
    client = authenticated_client
    customer, sales, support = _client_with_agents(client)
    first = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": sales["id"]}).json()
    second = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": support["id"]}).json()
    _status(client, first["id"], "573001112233")
    assert client.get(f"/api/whatsapp/channels/{first['id']}").json()["status"] == "connected"

    _status(client, second["id"], "573001112233")
    twin = client.get(f"/api/whatsapp/channels/{second['id']}").json()
    assert twin["status"] == "error" and twin["is_enabled"] is False
    assert "already connected" in twin["last_error"]
    # A different phone on the second line is fine.
    _status(client, second["id"], "573009998877")
    assert client.get(f"/api/whatsapp/channels/{second['id']}").json()["status"] == "connected"


def test_each_line_keeps_its_own_conversations_and_the_inbox_names_the_line(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, sales, support = _client_with_agents(client)
    first = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": sales["id"], "label": "Sales"}).json()
    second = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": support["id"]}).json()
    _status(client, first["id"], "573001110001")
    _status(client, second["id"], "573001110002")
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hello!", input_tokens=1, output_tokens=1)))

    def inbound(channel_id: str, message_id: str) -> dict:
        return client.post(
            f"/api/internal/whatsapp/channels/{channel_id}/inbound",
            json={"external_message_id": message_id, "remote_jid": "573005550000@s.whatsapp.net", "sender_name": "Sam", "text": "Hola"},
            headers=_bridge_headers(),
        ).json()

    on_first = inbound(first["id"], "m1")["conversation_id"]
    on_second = inbound(second["id"], "m2")["conversation_id"]
    assert on_first != on_second

    detail_first = client.get(f"/api/conversations/{on_first}").json()
    detail_second = client.get(f"/api/conversations/{on_second}").json()
    # One person, one contact, two conversations: one per line, each answered by that line's agent.
    assert detail_first["contact_id"] == detail_second["contact_id"]
    assert detail_first["agent_id"] == sales["id"] and detail_second["agent_id"] == support["id"]
    # The line's own name, or its last digits when it has none.
    assert detail_first["account_label"] == "Sales"
    assert detail_second["account_label"] == "\u00b7\u00b7\u00b70002"
    rows = {row["id"]: row for row in client.get("/api/conversations/inbox").json()}
    assert rows[on_first]["account_label"] == "Sales" and rows[on_second]["account_label"] == "\u00b7\u00b7\u00b70002"


def test_single_line_shows_no_badge_and_removing_a_line_keeps_history(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, sales, _support = _client_with_agents(client)
    line = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": sales["id"]}).json()
    _status(client, line["id"], "573001110001")
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hello!", input_tokens=1, output_tokens=1)))
    conversation_id = client.post(
        f"/api/internal/whatsapp/channels/{line['id']}/inbound",
        json={"external_message_id": "m1", "remote_jid": "573005550000@s.whatsapp.net", "sender_name": "Sam", "text": "Hola"},
        headers=_bridge_headers(),
    ).json()["conversation_id"]
    assert client.get(f"/api/conversations/{conversation_id}").json()["account_label"] is None

    from app.routers import whatsapp as whatsapp_router
    monkeypatch.setattr(whatsapp_router, "bridge_command", AsyncMock(return_value={}))
    assert client.delete(f"/api/whatsapp/channels/{line['id']}").status_code == 204
    assert client.get(f"/api/whatsapp/clients/{customer['id']}/channels").json() == []
    kept = client.get(f"/api/conversations/{conversation_id}")
    assert kept.status_code == 200 and kept.json()["channel"] == "whatsapp"
    with TestingSession() as db:
        assert db.scalar(select(Conversation.whatsapp_channel_id).where(Conversation.id == conversation_id)) is None
        assert db.scalar(select(WhatsAppChannel)) is None
    # Nothing can be sent on it any more, but it can still be read.
    assert client.post(f"/api/conversations/{conversation_id}/human-reply", json={"content": "hi"}).status_code in (404, 409)


def test_client_can_have_several_cloud_numbers_and_the_webhook_routes_by_number(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, sales, support = _client_with_agents(client)
    credentials = {"waba_id": "waba-1", "access_token": "meta-access-token", "app_secret": APP_SECRET}
    first = client.put(f"/api/whatsapp-cloud/channels/{customer['id']}", json={"agent_id": sales["id"], "phone_number_id": "111", "label": "Main", **credentials})
    assert first.status_code == 200, first.text
    second = client.post(f"/api/whatsapp-cloud/clients/{customer['id']}/channels", json={"agent_id": support["id"], "phone_number_id": "222", **credentials})
    assert second.status_code == 201, second.text
    # The same number cannot be saved on another line, of this client or any other.
    dup = client.post(f"/api/whatsapp-cloud/clients/{customer['id']}/channels", json={"agent_id": support["id"], "phone_number_id": "111", **credentials})
    assert dup.status_code == 400
    numbers = client.get(f"/api/whatsapp-cloud/clients/{customer['id']}/channels").json()
    assert [row["phone_number_id"] for row in numbers] == ["111", "222"]
    assert client.get(f"/api/whatsapp-cloud/channels/{customer['id']}").json()["id"] == first.json()["id"]

    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hi")))
    from app.routers import whatsapp_cloud_webhook as webhook_router
    from app.services import whatsapp as whatsapp_service
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(return_value="wamid.out"))
    monkeypatch.setattr(whatsapp_service, "mark_read_with_typing", AsyncMock())

    # Meta delivers both numbers to one callback (the first channel's URL).
    message = {"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Hola"}}
    assert _post_signed(client, first.json()["id"], _webhook_payload([message], phone_number_id="222")).status_code == 200
    assert _post_signed(client, first.json()["id"], _webhook_payload([dict(message, id="wamid.in-2")], phone_number_id="111")).status_code == 200
    assert _post_signed(client, first.json()["id"], _webhook_payload([dict(message, id="wamid.in-3")], phone_number_id="999")).status_code == 200
    with TestingSession() as db:
        rows = db.scalars(select(Conversation).where(Conversation.channel == "whatsapp_cloud")).all()
        by_channel = {str(row.whatsapp_cloud_channel_id): str(row.agent_id) for row in rows}
    assert by_channel == {first.json()["id"]: sales["id"], second.json()["id"]: support["id"]}

    inbox = client.get("/api/conversations/inbox").json()
    # The labelled number is named; the other has no label and, never having
    # been verified with Meta, no phone number to fall back on.
    assert {row["account_label"] for row in inbox} == {"Main", None}
    assert client.delete(f"/api/whatsapp-cloud/channels/{second.json()['id']}").status_code == 204
    assert [row["phone_number_id"] for row in client.get(f"/api/whatsapp-cloud/clients/{customer['id']}/channels").json()] == ["111"]


def test_portal_lists_every_line_with_its_id_and_label(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Lines Co", "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@lines.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@lines.co", "password": "secure-portal"})
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post("/api/agents", json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini",
                                             "name": "Beto", "instructions": "", "personality": "", "is_active": True}).json()
    a = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": agent["id"], "label": "Store"}).json()
    b = client.post(f"/api/whatsapp/clients/{customer['id']}/channels", json={"agent_id": agent["id"]}).json()
    lines = [row for row in client.get(f"/api/portal/{customer['portal_slug']}/channels").json() if row["channel"] == "whatsapp"]
    assert [(row["id"], row["label"]) for row in lines] == [(a["id"], "Store"), (b["id"], None)]
