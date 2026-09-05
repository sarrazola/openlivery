"""Operator and inbound WhatsApp gestures: reactions, quoted replies, and the
read/typing signal, on the bridge channel (the Cloud API variants live in
test_whatsapp_cloud.py)."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as whatsapp_inbound_service


def _headers() -> dict:
    return {"X-Bridge-Token": get_settings().whatsapp_bridge_token}


def _setup_bridge_channel(client: TestClient) -> str:
    customer = client.post(
        "/api/clients",
        json={"name": "Casa", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"],
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "name": "Bella",
            "instructions": "",
            "personality": "",
            "is_active": True,
        },
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    return channel["id"]


def _inbound(client: TestClient, channel_id: str, external_id: str, text: str, **extra) -> dict:
    response = client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers=_headers(),
        json={
            "external_message_id": external_id,
            "remote_jid": "573001112233@s.whatsapp.net",
            "sender_name": "Maria",
            "text": text,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_bridge_inbound_reaction_lands_on_the_target(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id = _setup_bridge_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Ok")))
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))

    result = _inbound(client, channel_id, "wa-in-1", "hola")
    conversation_id = result["conversation_id"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assistant = detail["messages"][-1]
    assert client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/outbound-confirm",
        headers=_headers(),
        json={"message_id": result["outbound_message_id"], "external_message_id": "wa-out-1"},
    ).status_code == 204

    # The customer reacts to the reply; the portal mirrors it.
    react = {"remote_jid": "573001112233@s.whatsapp.net", "target_external_id": "wa-out-1", "emoji": "❤️"}
    assert client.post(f"/api/internal/whatsapp/channels/{channel_id}/reaction", json=react).status_code == 401
    assert client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/reaction", headers=_headers(), json=react
    ).status_code == 204
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["id"] == assistant["id"]
    assert detail["messages"][-1]["incoming_reaction"] == "❤️"

    # An empty emoji removes it.
    assert client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/reaction", headers=_headers(), json={**react, "emoji": ""}
    ).status_code == 204
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["incoming_reaction"] is None


def test_bridge_inbound_quoted_reply_links_the_messages(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id = _setup_bridge_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Claro")))
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))

    result = _inbound(client, channel_id, "wa-in-1", "¿abren hoy?")
    assert client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/outbound-confirm",
        headers=_headers(),
        json={"message_id": result["outbound_message_id"], "external_message_id": "wa-out-1"},
    ).status_code == 204

    _inbound(client, channel_id, "wa-in-2", "gracias!", quoted_external_id="wa-out-1")
    detail = client.get(f"/api/conversations/{result['conversation_id']}").json()
    assistant = next(item for item in detail["messages"] if item["external_message_id"] == "wa-out-1")
    visitor = next(item for item in detail["messages"] if item["external_message_id"] == "wa-in-2")
    assert visitor["quoted_message_id"] == assistant["id"]


def test_bridge_read_signal_fires_before_the_ai_reply(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id = _setup_bridge_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Ok")))
    bridge = AsyncMock(return_value={})
    monkeypatch.setattr(whatsapp_service, "bridge_command", bridge)

    _inbound(client, channel_id, "wa-in-1", "hola")
    bridge.assert_awaited_once()
    method, path, payload = bridge.await_args.args
    assert method == "POST" and path == f"/channels/{channel_id}/read"
    assert payload == {"remote_jid": "573001112233@s.whatsapp.net", "message_ids": ["wa-in-1"], "typing": True}


def test_operator_reaction_on_the_bridge_channel(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id = _setup_bridge_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Ok")))
    bridge = AsyncMock(return_value={})
    monkeypatch.setattr(whatsapp_service, "bridge_command", bridge)

    result = _inbound(client, channel_id, "wa-in-1", "hola")
    conversation_id = result["conversation_id"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    visitor = detail["messages"][0]
    assistant = detail["messages"][-1]

    # Reactions require taking control first, and only target visitor messages.
    endpoint = f"/api/conversations/{conversation_id}/messages/{visitor['id']}/reaction"
    assert client.post(endpoint, json={"emoji": "👍"}).status_code == 409
    assert client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"}).status_code == 200
    assert client.post(
        f"/api/conversations/{conversation_id}/messages/{assistant['id']}/reaction", json={"emoji": "👍"}
    ).status_code == 409

    bridge.reset_mock()
    updated = client.post(endpoint, json={"emoji": "👍"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["messages"][0]["reaction"] == "👍"
    method, path, payload = bridge.await_args.args
    assert method == "POST" and path == f"/channels/{channel_id}/react"
    assert payload == {
        "remote_jid": "573001112233@s.whatsapp.net",
        "external_message_id": "wa-in-1",
        "emoji": "👍",
        "target_from_me": False,
    }

    # Removing goes through the same door with an empty emoji.
    cleared = client.post(endpoint, json={"emoji": ""})
    assert cleared.json()["messages"][0]["reaction"] is None


def test_operator_quoted_reply_on_the_bridge_channel(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id = _setup_bridge_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Ok")))
    bridge = AsyncMock(return_value={"external_message_id": "wa-out-2"})
    monkeypatch.setattr(whatsapp_service, "bridge_command", bridge)

    result = _inbound(client, channel_id, "wa-in-1", "¿abren hoy?")
    conversation_id = result["conversation_id"]
    visitor = client.get(f"/api/conversations/{conversation_id}").json()["messages"][0]
    client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"})

    bridge.reset_mock()
    reply = client.post(
        f"/api/conversations/{conversation_id}/reply",
        json={"content": "Sí, hasta las 10pm", "quoted_message_id": visitor["id"]},
    )
    assert reply.status_code == 200, reply.text
    outbound = reply.json()["messages"][-1]
    assert outbound["quoted_message_id"] == visitor["id"]
    assert outbound["external_message_id"] == "wa-out-2"
    method, path, payload = bridge.await_args.args
    assert method == "POST" and path == f"/channels/{channel_id}/send"
    assert payload["quote_external_id"] == "wa-in-1"

    # A quote from another conversation is rejected.
    bad = client.post(
        f"/api/conversations/{conversation_id}/reply",
        json={"content": "hola", "quoted_message_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 404
