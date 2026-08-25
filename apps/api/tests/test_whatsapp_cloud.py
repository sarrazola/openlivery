import hashlib
import hmac
import json
from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.routers import whatsapp_cloud as whatsapp_cloud_router
from app.routers import whatsapp_cloud_webhook as webhook_router
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as whatsapp_inbound_service


APP_SECRET = "meta-app-secret"


def _sign(raw: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _webhook_payload(messages: list[dict], contacts: list[dict] | None = None) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "111"},
                            "contacts": contacts or [],
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


def _post_signed(client: TestClient, channel_id: str, payload: dict, secret: str = APP_SECRET):
    raw = json.dumps(payload).encode()
    return client.post(
        f"/api/public/whatsapp-cloud/channels/{channel_id}/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(raw, secret)},
    )


def _setup_channel(client: TestClient, *, image_enabled: bool = False) -> tuple[dict, dict, dict]:
    customer = client.post(
        "/api/clients",
        json={"name": "Bistro", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"],
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "image_enabled": image_enabled,
            "name": "Host",
            "description": "",
            "instructions": "",
            "personality": "",
            "is_active": True,
        },
    ).json()
    channel = client.put(
        f"/api/whatsapp-cloud/channels/{customer['id']}",
        json={
            "agent_id": agent["id"],
            "phone_number_id": "111",
            "waba_id": "waba-1",
            "access_token": "meta-access-token",
            "app_secret": APP_SECRET,
        },
    ).json()
    return customer, agent, channel


def test_configure_channel_hides_secrets(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent, channel = _setup_channel(client)
    assert channel["has_access_token"] is True
    assert channel["has_app_secret"] is True
    assert channel["phone_number_id"] == "111"
    assert "meta-access-token" not in json.dumps(channel)
    assert channel["webhook_url"].endswith(f"/api/public/whatsapp-cloud/channels/{channel['id']}/webhook")
    assert len(channel["webhook_verify_token"]) == 32

    fetched = client.get(f"/api/whatsapp-cloud/channels/{customer['id']}").json()
    assert fetched["id"] == channel["id"]
    assert "access_token" not in fetched and "app_secret" not in fetched

    # Resubmitting without secrets keeps the stored ones.
    resaved = client.put(
        f"/api/whatsapp-cloud/channels/{customer['id']}",
        json={"agent_id": agent["id"], "phone_number_id": "222"},
    ).json()
    assert resaved["has_access_token"] is True
    assert resaved["phone_number_id"] == "222"
    assert resaved["webhook_verify_token"] == channel["webhook_verify_token"]

    # Another agency cannot see the channel. Registration closes after the
    # first agency, so allow a second one just for this check.
    monkeypatch.setattr(get_settings(), "allow_multi_agency", True)
    other = client.post(
        "/api/auth/register",
        json={"agency_name": "Other", "name": "Eve", "email": "eve@other.com", "password": "another-password"},
    )
    assert other.status_code == 201
    assert client.get(f"/api/whatsapp-cloud/channels/{customer['id']}").status_code == 404


def test_connect_verifies_credentials(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, _channel = _setup_channel(client)

    fake_verify = AsyncMock(return_value={"display_phone_number": "+57 300 111 2233", "verified_name": "Bistro"})
    monkeypatch.setattr(whatsapp_cloud_router, "verify_phone_number", fake_verify)
    connected = client.post(f"/api/whatsapp-cloud/channels/{customer['id']}/connect").json()
    assert connected["status"] == "connected"
    assert connected["phone_number"] == "+57 300 111 2233"
    assert connected["display_name"] == "Bistro"

    failing = AsyncMock(side_effect=HTTPException(status_code=502, detail="Credential check failed: bad token"))
    monkeypatch.setattr(whatsapp_cloud_router, "verify_phone_number", failing)
    errored = client.post(f"/api/whatsapp-cloud/channels/{customer['id']}/connect").json()
    assert errored["status"] == "error"
    assert "bad token" in errored["last_error"]

    disconnected = client.post(f"/api/whatsapp-cloud/channels/{customer['id']}/disconnect").json()
    assert disconnected["status"] == "disconnected"
    assert disconnected["is_enabled"] is False


def test_webhook_verify_handshake(authenticated_client: TestClient):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    url = f"/api/public/whatsapp-cloud/channels/{channel['id']}/webhook"
    ok = client.get(
        url,
        params={"hub.mode": "subscribe", "hub.verify_token": channel["webhook_verify_token"], "hub.challenge": "12345"},
    )
    assert ok.status_code == 200
    assert ok.text == "12345"
    assert client.get(
        url, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"}
    ).status_code == 403


def test_webhook_rejects_bad_signature(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Hello!"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)

    payload = _webhook_payload([{"from": "5730011", "id": "wamid.bad", "type": "text", "text": {"body": "Hola"}}])
    raw = json.dumps(payload).encode()
    url = f"/api/public/whatsapp-cloud/channels/{channel['id']}/webhook"
    assert client.post(url, content=raw, headers={"Content-Type": "application/json"}).status_code == 403
    assert client.post(
        url,
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(raw, "wrong-secret")},
    ).status_code == 403
    assert fake_completion.await_count == 0


def test_webhook_text_message_creates_conversation_and_replies(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="We are open every day."))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    fake_send = AsyncMock(return_value="wamid.out-1")
    monkeypatch.setattr(webhook_router, "send_text", fake_send)

    payload = _webhook_payload(
        [{"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Are you open?"}}],
        contacts=[{"wa_id": "5730011", "profile": {"name": "Maria"}}],
    )
    response = _post_signed(client, channel["id"], payload)
    assert response.status_code == 200, response.text
    fake_send.assert_awaited_once_with("meta-access-token", "111", "5730011", "We are open every day.")

    conversation = client.get("/api/conversations").json()[0]
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["channel"] == "whatsapp_cloud"
    assert detail["contact_name"] == "Maria"
    assert [item["sender_type"] for item in detail["messages"]] == ["visitor", "ai"]
    assert detail["messages"][-1]["external_message_id"] == "wamid.out-1"

    # A Meta retry with the same wamid is deduplicated.
    assert _post_signed(client, channel["id"], payload).status_code == 200
    assert fake_completion.await_count == 1
    assert fake_send.await_count == 1


def test_webhook_ignores_statuses_and_unsupported_types(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Hi"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)

    statuses = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {"statuses": [{"id": "wamid.out-1", "status": "delivered"}]},
                    }
                ]
            }
        ],
    }
    assert _post_signed(client, channel["id"], statuses).status_code == 200
    sticker = _webhook_payload([{"from": "5730011", "id": "wamid.stk", "type": "sticker", "sticker": {"id": "1"}}])
    assert _post_signed(client, channel["id"], sticker).status_code == 200
    assert fake_completion.await_count == 0


def test_webhook_human_mode_skips_ai(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="AI reply"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    fake_send = AsyncMock(return_value="wamid.out-1")
    monkeypatch.setattr(webhook_router, "send_text", fake_send)

    first = _webhook_payload([{"from": "5730011", "id": "wamid.h-1", "type": "text", "text": {"body": "Hola"}}])
    _post_signed(client, channel["id"], first)
    conversation = client.get("/api/conversations").json()[0]
    client.patch(f"/api/conversations/{conversation['id']}/mode", json={"mode": "human"})

    second = _webhook_payload([{"from": "5730011", "id": "wamid.h-2", "type": "text", "text": {"body": "Quiero hablar con alguien"}}])
    _post_signed(client, channel["id"], second)
    assert fake_completion.await_count == 1
    assert fake_send.await_count == 1
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["messages"][-1]["sender_type"] == "visitor"

    # The operator answers from the Inbox through the Graph API.
    operator_send = AsyncMock(return_value="wamid.human-1")
    monkeypatch.setattr(whatsapp_service, "send_text", operator_send)
    reply = client.post(f"/api/conversations/{conversation['id']}/reply", json={"content": "Hola Maria, te ayudo yo."})
    assert reply.status_code == 200, reply.text
    assert reply.json()["messages"][-1]["external_message_id"] == "wamid.human-1"
    operator_send.assert_awaited_once_with("meta-access-token", "111", "5730011", "Hola Maria, te ayudo yo.")


def test_webhook_image_uses_capability(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client, image_enabled=True)
    monkeypatch.setattr(webhook_router, "fetch_media", AsyncMock(return_value=(b"fake-image-bytes", "image/jpeg")))
    monkeypatch.setattr(whatsapp_inbound_service, "describe_image", AsyncMock(return_value="a photo of the menu"))
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Here are the dishes!"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(return_value="wamid.out-img"))

    payload = _webhook_payload(
        [
            {
                "from": "5730011",
                "id": "wamid.img-1",
                "type": "image",
                "image": {"id": "media-1", "mime_type": "image/jpeg", "caption": "What is this?"},
            }
        ]
    )
    assert _post_signed(client, channel["id"], payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    # The chat shows the caption plus the stored file; the description only feeds the LLM.
    assert detail["messages"][0]["content"] == "What is this?"
    assert detail["messages"][0]["attachments"][0]["kind"] == "image"
    prompt_messages = fake_completion.await_args.args[4]
    assert any("a photo of the menu" in message["content"] for message in prompt_messages)
