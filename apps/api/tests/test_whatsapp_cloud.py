import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
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


def _webhook_payload(
    messages: list[dict], contacts: list[dict] | None = None, phone_number_id: str = "111"
) -> dict:
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
                            "metadata": {"phone_number_id": phone_number_id},
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
    fake_read = AsyncMock()
    monkeypatch.setattr(whatsapp_inbound_service, "mark_read_with_typing", fake_read)

    payload = _webhook_payload(
        [{"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Are you open?"}}],
        contacts=[{"wa_id": "5730011", "profile": {"name": "Maria"}}],
    )
    response = _post_signed(client, channel["id"], payload)
    assert response.status_code == 200, response.text
    fake_send.assert_awaited_once_with(
        "meta-access-token", "111", "5730011", "We are open every day.", context_message_id=None
    )
    # The visitor's message is blue-ticked with the typing indicator before the reply.
    fake_read.assert_awaited_once_with("meta-access-token", "111", "wamid.in-1")

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


def test_reply_react_gesture_sends_reaction_without_text(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="[react: 👍]"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    fake_send = AsyncMock(return_value="wamid.out-1")
    monkeypatch.setattr(webhook_router, "send_text", fake_send)
    fake_react = AsyncMock()
    monkeypatch.setattr(whatsapp_inbound_service, "send_reaction", fake_react)
    monkeypatch.setattr(whatsapp_inbound_service, "mark_read_with_typing", AsyncMock())

    payload = _webhook_payload([{"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "gracias!"}}])
    assert _post_signed(client, channel["id"], payload).status_code == 200
    fake_react.assert_awaited_once_with("meta-access-token", "111", "5730011", "wamid.in-1", "👍")
    fake_send.assert_not_awaited()

    conversation = client.get("/api/conversations").json()[0]
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    # Reaction stored on the visitor message; no empty assistant bubble.
    assert [item["sender_type"] for item in detail["messages"]] == ["visitor"]
    assert detail["messages"][0]["reaction"] == "👍"


def test_reply_quote_gesture_quotes_the_visitor_message(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="[quote: 1] Claro, hasta las 10pm."))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    fake_send = AsyncMock(return_value="wamid.out-1")
    monkeypatch.setattr(webhook_router, "send_text", fake_send)
    monkeypatch.setattr(whatsapp_inbound_service, "mark_read_with_typing", AsyncMock())

    payload = _webhook_payload([{"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "¿hasta qué hora abren?"}}])
    assert _post_signed(client, channel["id"], payload).status_code == 200
    fake_send.assert_awaited_once_with(
        "meta-access-token", "111", "5730011", "Claro, hasta las 10pm.", context_message_id="wamid.in-1"
    )

    conversation = client.get("/api/conversations").json()[0]
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    visitor, assistant = detail["messages"]
    assert assistant["content"] == "Claro, hasta las 10pm."
    assert assistant["quoted_message_id"] == visitor["id"]


def test_receipts_land_on_the_outbound_message(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hi")))
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(return_value="wamid.out-1"))
    monkeypatch.setattr(whatsapp_inbound_service.get_settings(), "reply_debounce_seconds", 0)
    _post_signed(client, channel["id"], _webhook_payload([{"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Hola"}}]))
    conversation_id = client.get("/api/conversations/inbox").json()[0]["id"]

    def receipt(state: str, **extra):
        return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {"statuses": [{"id": "wamid.out-1", "status": state, **extra}]}}]}]}

    def outbound():
        return [m for m in client.get(f"/api/conversations/{conversation_id}").json()["messages"] if m["sender_type"] == "ai"][-1]

    assert outbound()["delivery_status"] is None
    _post_signed(client, channel["id"], receipt("delivered"))
    assert outbound()["delivery_status"] == "delivered"
    # A late "sent" never rolls the state back.
    _post_signed(client, channel["id"], receipt("sent"))
    assert outbound()["delivery_status"] == "delivered"
    _post_signed(client, channel["id"], receipt("read"))
    assert outbound()["delivery_status"] == "read"
    _post_signed(client, channel["id"], receipt("failed", errors=[{"code": 131047, "message": "Re-engagement message"}]))
    failed = outbound()
    assert failed["delivery_status"] == "failed" and "131047" in failed["delivery_error"]


def test_webhook_failed_status_surfaces_delivery_error(authenticated_client: TestClient):
    client = authenticated_client
    customer, _agent, channel = _setup_channel(client)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.out-2",
                                    "status": "failed",
                                    "errors": [
                                        {
                                            "code": 131053,
                                            "title": "Media upload error",
                                            "error_data": {"details": "The audio is not a valid ogg/opus file."},
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }
    assert _post_signed(client, channel["id"], payload).status_code == 200
    detail = client.get(f"/api/whatsapp-cloud/channels/{customer['id']}").json()
    assert "131053" in (detail["last_error"] or "")
    assert "ogg/opus" in detail["last_error"]


def test_transcoded_voice_note_uploads_with_ogg_filename(monkeypatch):
    captured = {}

    async def fake_voice(data, mime):
        return b"OggS-transcoded", "audio/ogg"

    async def fake_duration(data):
        return 3

    async def fake_upload(token, phone_number_id, data, mime, filename):
        captured["mime"] = mime
        captured["filename"] = filename
        return "media-1"

    async def fake_send(token, phone_number_id, to, kind, media_id, caption="", filename=None):
        return "wamid.audio-out"

    monkeypatch.setattr(whatsapp_service, "to_whatsapp_voice", fake_voice)
    monkeypatch.setattr(whatsapp_service, "audio_duration_seconds", fake_duration)
    monkeypatch.setattr(whatsapp_service, "upload_media", fake_upload)
    monkeypatch.setattr(whatsapp_service, "send_media", fake_send)
    monkeypatch.setattr(whatsapp_service, "decrypt_secret", lambda value: "token")

    channel = SimpleNamespace(encrypted_access_token="enc", phone_number_id="111")
    conversation = SimpleNamespace(
        channel="whatsapp_cloud", whatsapp_cloud_channel_id="ch-1", external_chat_id="573001"
    )
    db = SimpleNamespace(get=lambda model, key: channel)

    wamid = asyncio.run(
        whatsapp_service.send_channel_media(
            db, conversation, kind="audio", data=b"mp4-bytes", mime="audio/mp4", filename="voice-note.mp4"
        )
    )
    assert wamid == "wamid.audio-out"
    # Meta classifies uploads by extension: the name must match the ogg bytes.
    assert captured["filename"] == "voice-note.ogg"
    assert captured["mime"] == "audio/ogg"


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
    operator_send.assert_awaited_once_with(
        "meta-access-token", "111", "5730011", "Hola Maria, te ayudo yo.", context_message_id=None
    )


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


def test_webhook_ignores_traffic_for_a_number_that_is_not_this_channels(
    authenticated_client: TestClient, monkeypatch
):
    """One Meta app has one callback URL, so an app shared between channels
    delivers every number's traffic to whichever channel registered it."""
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Hi"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(return_value="wamid.out-1"))
    monkeypatch.setattr(whatsapp_inbound_service, "mark_read_with_typing", AsyncMock())

    other = _webhook_payload(
        [{"from": "5730011", "id": "wamid.other", "type": "text", "text": {"body": "Hola"}}],
        phone_number_id="999",
    )
    assert _post_signed(client, channel["id"], other).status_code == 200
    assert fake_completion.await_count == 0
    assert client.get("/api/conversations").json() == []

    # The channel's own number still goes through.
    mine = _webhook_payload(
        [{"from": "5730011", "id": "wamid.mine", "type": "text", "text": {"body": "Hola"}}]
    )
    assert _post_signed(client, channel["id"], mine).status_code == 200
    assert fake_completion.await_count == 1


def test_configure_channel_refuses_a_number_another_client_uses(authenticated_client: TestClient):
    client = authenticated_client
    _setup_channel(client)

    other = client.post(
        "/api/clients",
        json={"name": "Cafe", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    agent = client.post(
        "/api/agents",
        json={
            "client_id": other["id"],
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "name": "Host",
            "description": "",
            "instructions": "",
            "personality": "",
            "is_active": True,
        },
    ).json()

    taken = client.put(
        f"/api/whatsapp-cloud/channels/{other['id']}",
        json={"agent_id": agent["id"], "phone_number_id": "111"},
    )
    assert taken.status_code == 400
    assert "another client" in taken.json()["detail"]

    # A different number is fine, and saving the same one again on its own
    # client still is.
    free = client.put(
        f"/api/whatsapp-cloud/channels/{other['id']}",
        json={"agent_id": agent["id"], "phone_number_id": "222"},
    )
    assert free.status_code == 200, free.text
