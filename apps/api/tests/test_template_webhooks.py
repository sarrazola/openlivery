import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Conversation, Message
from app.routers import whatsapp_cloud_webhook as inbound_router
from app.routers import template_webhooks as webhooks_router
from app.services import ai as ai_service
from app.services import template_webhooks as service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as whatsapp_inbound_service
from app.services.whatsapp_templates import normalize


APP_SECRET = "meta-app-secret"
REMINDER = normalize({
    "id": "1", "name": "appointment_reminder", "language": "es", "category": "UTILITY", "status": "APPROVED",
    "parameter_format": "NAMED",
    "components": [{"type": "BODY", "text": "Hola {{nombre}}, tu cita es el {{fecha}} a las {{hora}}."}],
})
PENDING = normalize({
    "id": "2", "name": "promo", "language": "es", "category": "MARKETING", "status": "PENDING",
    "components": [{"type": "BODY", "text": "Promo!"}],
})
CONFIRM = normalize({
    "id": "3", "name": "confirm_visit", "language": "es", "category": "UTILITY", "status": "APPROVED",
    "parameter_format": "NAMED",
    "components": [
        {"type": "BODY", "text": "Hola {{nombre}}, te esperamos el {{fecha}}."},
        {"type": "BUTTONS", "buttons": [
            {"type": "QUICK_REPLY", "text": "Sí, ahí estaré"},
            {"type": "QUICK_REPLY", "text": "Necesito cambiarla"},
            {"type": "URL", "text": "Ver detalles", "url": "https://example.com/visit"},
        ]},
    ],
})
PROMO = normalize({
    "id": "4", "name": "spring_sale", "language": "es", "category": "MARKETING", "status": "APPROVED",
    "components": [{"type": "BODY", "text": "Hola! Esta semana todo con descuento."}],
})
VALUES = {"nombre": "Luna", "fecha": "martes 7", "hora": "3 pm"}


def _setup(client: TestClient, monkeypatch) -> tuple[dict, dict, dict, AsyncMock]:
    customer = client.post("/api/clients", json={"name": "Vet Clinic", "is_active": True}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini", "name": "Front desk",
            "instructions": "", "personality": "", "is_active": True,
        },
    ).json()
    channel = client.put(
        f"/api/whatsapp-cloud/channels/{customer['id']}",
        json={"agent_id": agent["id"], "phone_number_id": "111", "waba_id": "waba-1",
              "access_token": "meta-access-token", "app_secret": APP_SECRET},
    ).json()
    monkeypatch.setattr(service, "list_templates", AsyncMock(return_value=[REMINDER, PENDING, CONFIRM, PROMO]))
    sent = AsyncMock(side_effect=[f"wamid.t{n}" for n in range(1, 10)])
    monkeypatch.setattr(service, "send_template", sent)
    return customer, agent, channel, sent


def _hook(webhook: dict) -> tuple[str, dict]:
    """The address and the header a caller needs."""
    return f"/api/public/hooks/{webhook['id']}", {"Authorization": f"Bearer {webhook['secret']}"}


def _create(client: TestClient, customer: dict, channel: dict, **overrides) -> dict:
    body = {"name": "Appointment reminder", "channel_id": channel["id"],
            "template_name": "appointment_reminder", "template_language": "es", **overrides}
    created = client.post(f"/api/clients/{customer['id']}/webhooks", json=body)
    assert created.status_code == 201, created.text
    return created.json()


def _contact_writes(client: TestClient, channel: dict, text: str, wamid: str, phone: str = "573001112233"):
    return _contact_sends(client, channel, {"from": phone, "id": wamid, "type": "text", "text": {"body": text}}, phone)


def _contact_sends(client: TestClient, channel: dict, message: dict, phone: str = "573001112233"):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "111"},
            "contacts": [{"wa_id": phone, "profile": {"name": "Luna's owner"}}],
            "messages": [message],
        }}]}],
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        f"/api/public/whatsapp-cloud/channels/{channel['id']}/webhook",
        content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )


def test_the_agency_manages_a_clients_webhooks(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent, channel, _sent = _setup(client, monkeypatch)
    base = f"/api/clients/{customer['id']}/webhooks"

    # Only a template the business account has approved can be bound.
    refused = client.post(base, json={"name": "Promo", "channel_id": channel["id"], "template_name": "promo", "template_language": "es"})
    assert refused.status_code == 409
    stranger = client.post(base, json={"name": "X", "channel_id": str(uuid.uuid4()), "template_name": "appointment_reminder", "template_language": "es"})
    assert stranger.status_code == 404

    webhook = _create(client, customer, channel)
    url, auth = _hook(webhook)
    assert webhook["secret"].startswith("whk_") and webhook["secret"].endswith(webhook["secret_hint"])
    assert webhook["url"].endswith(url) and webhook["secret"] not in webhook["url"] and webhook["is_enabled"] is True
    assert webhook["agent_name"] == agent["name"] and webhook["channel_id"] == channel["id"]
    # The secret is shown once: reading the webhook again does not bring it back.
    listed = client.get(base).json()
    assert [w["id"] for w in listed] == [webhook["id"]] and listed[0]["secret"] is None
    assert listed[0]["secret_hint"] == webhook["secret_hint"]

    renamed = client.patch(f"{base}/{webhook['id']}", json={"name": "Reminder", "is_enabled": False})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Reminder" and renamed.json()["is_enabled"] is False
    assert client.patch(f"{base}/{webhook['id']}", json={"template_name": "promo"}).status_code == 409
    assert client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES}).status_code == 409

    assert client.delete(f"{base}/{webhook['id']}").status_code == 204
    assert client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES}).status_code == 404


def test_the_address_alone_sends_nothing(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, channel, sent = _setup(client, monkeypatch)
    webhook = _create(client, customer, channel)
    url, auth = _hook(webhook)
    body = {"phone": "573001112233", "variables": VALUES}
    client.cookies.clear()

    assert client.post(url, json=body).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer whk_wrong"}, json=body).status_code == 401
    assert client.post(url, headers={"Authorization": webhook["secret"]}, json=body).status_code == 401
    assert client.post(f"/api/public/hooks/{uuid.uuid4()}", headers=auth, json=body).status_code == 404
    assert sent.await_count == 0
    assert client.post(url, headers=auth, json=body).status_code == 200

    # A regenerated secret replaces the old one at once.
    client.post("/api/auth/login", json={"email": "ana@prisma.com", "password": "contrasena-segura"})
    fresh = client.post(f"/api/clients/{customer['id']}/webhooks/{webhook['id']}/secret")
    assert fresh.status_code == 200 and fresh.json()["secret"] != webhook["secret"]
    client.cookies.clear()
    assert client.post(url, headers=auth, json=body).status_code == 401
    assert client.post(url, headers={"Authorization": f"Bearer {fresh.json()['secret']}"}, json=body).status_code == 200


def test_a_call_sends_the_template_and_the_agent_answers_with_it_in_mind(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent, channel, sent = _setup(client, monkeypatch)
    url, auth = _hook(_create(client, customer, channel))
    client.cookies.clear()  # the caller is another system: no session, only its secret

    missing = client.post(url, headers=auth, json={"phone": "573001112233", "variables": {"nombre": "Luna"}})
    assert missing.status_code == 422 and "fecha, hora" in missing.json()["detail"]
    assert client.post(url, headers=auth, json={"phone": "abc-def-ghi", "variables": VALUES}).status_code == 422
    assert sent.await_count == 0

    called = client.post(url, headers=auth, json={
        "phone": "+57 300 111 2233", "name": "Luna's owner", "variables": VALUES, "context": "appointment 123",
    })
    assert called.status_code == 200, called.text
    result = called.json()
    assert result["started"] is True and result["mode"] == "ai" and result["duplicate"] is False
    assert result["text"] == "Hola Luna, tu cita es el martes 7 a las 3 pm."
    assert sent.call_args.args == ("meta-access-token", "111", "573001112233")
    assert sent.call_args.kwargs == {"name": "appointment_reminder", "language": "es", "components": [
        {"type": "body", "parameters": [
            {"type": "text", "text": "Luna", "parameter_name": "nombre"},
            {"type": "text", "text": "martes 7", "parameter_name": "fecha"},
            {"type": "text", "text": "3 pm", "parameter_name": "hora"},
        ]},
    ]}

    with SessionLocal() as db:
        conversation = db.get(Conversation, uuid.UUID(result["conversation_id"]))
        assert conversation.mode == "ai" and conversation.agent_id == uuid.UUID(agent["id"])
        assert conversation.follow_up_due_at is None
        message = db.get(Message, uuid.UUID(result["message_id"]))
        assert message.sender_type == "ai" and message.external_message_id == "wamid.t1"
        assert message.content == result["text"] and "appointment 123" in message.llm_content

    # The contact answers: the same conversation, and the model reads the
    # reminder together with the caller's notes.
    completion = AsyncMock(return_value=ai_service.Completion(text="Confirmed, see you then."))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", completion)
    monkeypatch.setattr(inbound_router, "send_text", AsyncMock(return_value="wamid.out-1"))
    monkeypatch.setattr(whatsapp_service, "mark_read_with_typing", AsyncMock())
    assert _contact_writes(client, channel, "Confirmo", "wamid.in-1").status_code == 200
    turns = completion.call_args.args[4]
    assert [turn["role"] for turn in turns[1:]] == ["assistant", "user"]
    assert "martes 7" in turns[1]["content"] and "appointment 123" in turns[1]["content"]
    with SessionLocal() as db:
        rows = db.query(Conversation).all()
        assert len(rows) == 1 and str(rows[0].id) == result["conversation_id"]

    # A later call joins the open conversation instead of opening another.
    again = client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES}).json()
    assert again["conversation_id"] == result["conversation_id"] and again["started"] is False


def test_a_retry_with_the_same_key_does_not_send_twice(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, channel, sent = _setup(client, monkeypatch)
    url, auth = _hook(_create(client, customer, channel))
    body = {"phone": "573001112233", "variables": VALUES, "idempotency_key": "appointment-123-reminder"}

    first = client.post(url, headers=auth, json=body).json()
    retry = client.post(url, headers=auth, json=body).json()
    assert retry["duplicate"] is True and retry["message_id"] == first["message_id"]
    assert retry["text"] == first["text"]
    assert sent.await_count == 1
    other = client.post(url, headers=auth, json={**body, "idempotency_key": "appointment-124-reminder"}).json()
    assert other["duplicate"] is False and sent.await_count == 2


def test_a_conversation_in_human_hands_gets_the_template_and_stays_there(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, channel, sent = _setup(client, monkeypatch)
    url, auth = _hook(_create(client, customer, channel))
    first = client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES}).json()
    taken = client.patch(f"/api/conversations/{first['conversation_id']}/mode", json={"mode": "human"})
    assert taken.status_code == 200, taken.text

    second = client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES})
    assert second.status_code == 200
    assert second.json()["mode"] == "human" and second.json()["conversation_id"] == first["conversation_id"]
    assert sent.await_count == 2


def test_a_send_meta_refuses_leaves_nothing_behind(authenticated_client: TestClient, monkeypatch):
    from fastapi import HTTPException

    client = authenticated_client
    customer, _agent, channel, _sent = _setup(client, monkeypatch)
    url, auth = _hook(_create(client, customer, channel))
    monkeypatch.setattr(service, "send_template", AsyncMock(side_effect=HTTPException(status_code=502, detail="WhatsApp could not send the template: nope")))

    assert client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES}).status_code == 502
    with SessionLocal() as db:
        assert db.query(Conversation).count() == 0 and db.query(Message).count() == 0


def test_a_templates_buttons_stay_on_the_message_and_a_tap_answers_it(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, channel, sent = _setup(client, monkeypatch)
    url, auth = _hook(_create(client, customer, channel, name="Visit confirmation", template_name="confirm_visit"))
    client.cookies.clear()

    called = client.post(url, headers=auth, json={"phone": "573001112233", "variables": {"nombre": "Luna", "fecha": "jueves 8"}})
    assert called.status_code == 200, called.text
    result = called.json()
    assert result["text"] == "Hola Luna, te esperamos el jueves 8."
    # Quick replies and a fixed link add nothing to the send: they are the template's.
    assert [component["type"] for component in sent.call_args.kwargs["components"]] == ["body"]
    with SessionLocal() as db:
        message = db.get(Message, uuid.UUID(result["message_id"]))
        assert message.buttons == [
            {"type": "QUICK_REPLY", "text": "Sí, ahí estaré"},
            {"type": "QUICK_REPLY", "text": "Necesito cambiarla"},
            {"type": "URL", "text": "Ver detalles"},
        ]
        assert message.content == result["text"]
        # The model reads which answers the contact could tap; a link is not one.
        assert message.llm_content.startswith(result["text"])
        assert '"Sí, ahí estaré", "Necesito cambiarla"' in message.llm_content and "Ver detalles" not in message.llm_content

    # The contact taps a button: the answer arrives in its words, quoting the
    # template, and the agent reads it next to the buttons it had offered.
    completion = AsyncMock(return_value=ai_service.Completion(text="Claro, qué día te queda mejor?"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", completion)
    monkeypatch.setattr(inbound_router, "send_text", AsyncMock(return_value="wamid.out-1"))
    monkeypatch.setattr(whatsapp_service, "mark_read_with_typing", AsyncMock())
    tap = {
        "from": "573001112233", "id": "wamid.in-1", "type": "button",
        "button": {"payload": "Necesito cambiarla", "text": "Necesito cambiarla"},
        "context": {"from": "111", "id": "wamid.t1"},
    }
    assert _contact_sends(client, channel, tap).status_code == 200
    turns = completion.call_args.args[4]
    assert "Reply buttons under this message" in turns[1]["content"] and turns[2]["content"] == "Necesito cambiarla"
    with SessionLocal() as db:
        answer = db.query(Message).filter(Message.external_message_id == "wamid.in-1").one()
        assert answer.content == "Necesito cambiarla" and answer.quoted_message_id == uuid.UUID(result["message_id"])


def test_webhooks_send_utility_templates_only(authenticated_client: TestClient, monkeypatch):
    """A webhook carries notices. An approved marketing template is not
    offered, cannot be bound, and stops sending if Meta moves the bound
    template to marketing after the fact."""
    client = authenticated_client
    customer, _agent, channel, sent = _setup(client, monkeypatch)
    base = f"/api/clients/{customer['id']}/webhooks"

    # The picker reads the business account through the router's own import.
    monkeypatch.setattr(webhooks_router, "list_templates", service.list_templates)
    offered = client.get(f"{base}/templates", params={"channel_id": channel["id"]}).json()
    assert sorted(t["name"] for t in offered) == ["appointment_reminder", "confirm_visit"]

    refused = client.post(base, json={"name": "Sale", "channel_id": channel["id"], "template_name": "spring_sale", "template_language": "es"})
    assert refused.status_code == 409 and "utility" in refused.json()["detail"]
    webhook = _create(client, customer, channel)
    assert client.patch(f"{base}/{webhook['id']}", json={"template_name": "spring_sale"}).status_code == 409

    # Meta recategorizes the reminder during a later review: the next call
    # stops with the reason instead of going out as marketing.
    moved = dict(REMINDER, category="MARKETING", previous_category="UTILITY")
    monkeypatch.setattr(service, "list_templates", AsyncMock(return_value=[moved, PENDING, CONFIRM, PROMO]))
    url, auth = _hook(webhook)
    client.cookies.clear()
    stopped = client.post(url, headers=auth, json={"phone": "573001112233", "variables": VALUES})
    assert stopped.status_code == 409 and "marketing" in stopped.json()["detail"]
    assert sent.await_count == 0
