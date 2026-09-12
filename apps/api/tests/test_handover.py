"""Hand-over: the business answers from the linked phone, and the agent steps
aside until the contact writes again."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as pipeline


def _whatsapp_agent(client: TestClient, monkeypatch):
    customer = client.post(
        "/api/clients",
        json={"name": "Wings", "industry": "restaurants_food", "business_type": "restaurant", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "sk-test"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "prompt_language": "en",
              "name": "Orders", "instructions": "Take orders.", "personality": "Warm", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    return channel["id"], {"X-Bridge-Token": get_settings().whatsapp_bridge_token}


def test_the_business_answers_from_the_phone_and_the_agent_steps_aside(
    authenticated_client: TestClient, monkeypatch
):
    client = authenticated_client
    channel_id, headers = _whatsapp_agent(client, monkeypatch)
    chat = "5219990001111@s.whatsapp.net"

    seen: list[list[dict]] = []

    async def capture(*args, **kwargs):
        seen.append(kwargs.get("messages") or args[4])
        return ai_service.Completion(text="Sure!")

    monkeypatch.setattr(pipeline, "run_completion", AsyncMock(side_effect=capture))

    first = client.post(f"/api/internal/whatsapp/channels/{channel_id}/inbound", headers=headers,
                        json={"external_message_id": "in-1", "remote_jid": chat, "sender_name": "Ana",
                              "text": "how do I pay?"}).json()
    assert first["mode"] == "ai"
    conversation_id = first["conversation_id"]

    # The owner answers on the phone instead of the inbox.
    reported = client.post(f"/api/internal/whatsapp/channels/{channel_id}/outgoing", headers=headers,
                           json={"external_message_id": "phone-1", "remote_jid": chat,
                                 "text": "Transfer to 1234567890 and send us the receipt."})
    assert reported.status_code == 204, reported.text

    paused = client.get(f"/api/conversations/{conversation_id}").json()
    assert paused["mode"] == "human", "the agent steps aside when a person answers"

    # The contact replies: the agent takes over again, now knowing the account.
    resumed = client.post(f"/api/internal/whatsapp/channels/{channel_id}/inbound", headers=headers,
                          json={"external_message_id": "in-2", "remote_jid": chat, "sender_name": "Ana",
                                "text": "already transferred"}).json()
    assert resumed["mode"] == "ai", "the contact wrote: the agent picks it back up"

    history = "\n".join(turn["content"] for turn in seen[-1])
    assert "1234567890" in history, "the agent must see what was typed on the phone"


def test_a_pause_chosen_in_the_inbox_is_not_undone_by_the_contact(
    authenticated_client: TestClient, monkeypatch
):
    """Taking over on purpose outlasts the next message; only the automatic
    pause lifts by itself."""
    client = authenticated_client
    channel_id, headers = _whatsapp_agent(client, monkeypatch)
    chat = "5219990002222@s.whatsapp.net"
    monkeypatch.setattr(pipeline, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hi!")))

    started = client.post(f"/api/internal/whatsapp/channels/{channel_id}/inbound", headers=headers,
                          json={"external_message_id": "in-3", "remote_jid": chat, "text": "hi"}).json()
    client.patch(f"/api/conversations/{started['conversation_id']}/mode", json={"mode": "human"})

    again = client.post(f"/api/internal/whatsapp/channels/{channel_id}/inbound", headers=headers,
                        json={"external_message_id": "in-4", "remote_jid": chat, "text": "anyone there?"}).json()
    assert again["mode"] == "human", "an operator's own pause stays until they hand it back"


def test_the_business_writing_first_opens_the_conversation(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id, headers = _whatsapp_agent(client, monkeypatch)
    chat = "5219990003333@s.whatsapp.net"

    reported = client.post(f"/api/internal/whatsapp/channels/{channel_id}/outgoing", headers=headers,
                           json={"external_message_id": "phone-2", "remote_jid": chat,
                                 "text": "Your order is almost ready."})
    assert reported.status_code == 204

    listed = client.get("/api/conversations").json()
    opened = [row for row in listed if row.get("external_chat_id") == chat]
    assert opened, "a conversation the business started must exist"
    assert opened[0]["mode"] == "human"


def test_our_own_echo_is_ignored(authenticated_client: TestClient, monkeypatch):
    """The bridge guards against this too, but a repeat delivery must never
    create a second copy or flip the mode."""
    client = authenticated_client
    channel_id, headers = _whatsapp_agent(client, monkeypatch)
    chat = "5219990004444@s.whatsapp.net"
    monkeypatch.setattr(pipeline, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hi!")))

    started = client.post(f"/api/internal/whatsapp/channels/{channel_id}/inbound", headers=headers,
                          json={"external_message_id": "in-5", "remote_jid": chat, "text": "hi"}).json()
    for _ in range(2):
        client.post(f"/api/internal/whatsapp/channels/{channel_id}/outgoing", headers=headers,
                    json={"external_message_id": "phone-3", "remote_jid": chat, "text": "On its way."})

    detail = client.get(f"/api/conversations/{started['conversation_id']}").json()
    typed = [m for m in detail["messages"] if m["content"] == "On its way."]
    assert len(typed) == 1, "a repeat delivery must not duplicate the message"


def test_a_media_message_from_the_phone_is_announced(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    channel_id, headers = _whatsapp_agent(client, monkeypatch)
    chat = "5219990005555@s.whatsapp.net"

    client.post(f"/api/internal/whatsapp/channels/{channel_id}/outgoing", headers=headers,
                json={"external_message_id": "phone-4", "remote_jid": chat, "text": "", "media_kind": "image"})

    listed = client.get("/api/conversations").json()
    conversation = next(row for row in listed if row.get("external_chat_id") == chat)
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert any("image was sent" in m["content"] for m in detail["messages"])
