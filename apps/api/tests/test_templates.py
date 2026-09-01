import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Message, now_utc
from app.routers import portal as portal_router


APPROVED = {
    "id": "1", "name": "saludo_inicial", "language": "es", "category": "UTILITY", "status": "APPROVED",
    "body": "Hola {{1}}, te escribimos de {{2}}.", "footer": "Responde para continuar.", "variables": 2, "rejected_reason": None,
}
PENDING = {**APPROVED, "id": "2", "name": "promo", "status": "PENDING", "body": "Promo!", "footer": "", "variables": 0}


def _portal_with_cloud_line(client: TestClient):
    customer = client.post(
        "/api/clients",
        json={"name": "Outbound Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@outbound.com", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    created = client.put(
        f"/api/whatsapp-cloud/channels/{customer['id']}",
        json={"agent_id": agent["id"], "phone_number_id": "PN1", "waba_id": "WABA1", "access_token": "tok", "app_secret": "sec"},
    )
    assert created.status_code in (200, 201), created.text
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@outbound.com", "password": "secure-portal"})
    return customer


def test_a_template_is_deleted_through_the_business_account(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal_with_cloud_line(client)
    slug = customer["portal_slug"]
    deleted = AsyncMock(return_value=None)
    monkeypatch.setattr(portal_router, "delete_template", deleted)

    assert client.delete(f"/api/portal/{slug}/templates/saludo_inicial?hsm_id=1").status_code == 204
    assert deleted.call_args.args == ("tok", "WABA1")
    assert deleted.call_args.kwargs == {"name": "saludo_inicial", "hsm_id": "1"}
    # Without an hsm_id the whole name goes, every language of it.
    assert client.delete(f"/api/portal/{slug}/templates/promo").status_code == 204
    assert deleted.call_args.kwargs == {"name": "promo", "hsm_id": None}
    assert client.delete(f"/api/portal/{slug}/templates/Bad Name").status_code == 422


def test_the_sender_chooses_the_line_when_the_business_has_both(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal_with_cloud_line(client)
    slug = customer["portal_slug"]
    qr_host = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "QR Host", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    assert client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": qr_host["id"]}).status_code in (200, 201)
    assert [c["channel"] for c in client.get(f"/api/portal/{slug}/channels").json()] == ["whatsapp_cloud", "whatsapp"]

    sent = AsyncMock(return_value="msg.qr.1")
    monkeypatch.setattr(portal_router, "send_channel_message", sent)
    contact = client.post(f"/api/portal/{slug}/contacts", json={"name": "Rita", "phone": "573009998877"}).json()
    start = f"/api/portal/{slug}/contacts/{contact['id']}/conversations"

    # Choosing the QR line sends free text, no template involved.
    assert client.post(start, json={"channel": "whatsapp"}).status_code == 422
    opened = client.post(start, json={"channel": "whatsapp", "text": "Hola Rita"})
    assert opened.status_code == 201, opened.text
    conv = opened.json()
    assert conv["channel"] == "whatsapp" and conv["mode"] == "human"
    assert conv["messages"][-1]["content"] == "Hola Rita"
    assert conv["messages"][-1]["external_message_id"] == "msg.qr.1"
    sent.assert_awaited_once()
    # Only one open conversation per line and contact, but the other line stays available.
    assert client.post(start, json={"channel": "whatsapp", "text": "Hola?"}).status_code == 409
    # Left unspecified, the cloud line is still the default and wants a template.
    assert client.post(start, json={"text": "Hola"}).status_code == 422


def test_templates_are_read_and_submitted_through_the_business_account(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal_with_cloud_line(client)
    slug = customer["portal_slug"]
    listed = AsyncMock(return_value=[APPROVED, PENDING])
    created = AsyncMock(return_value={**PENDING, "name": "bienvenida", "body": "Bienvenido {{1}}", "variables": 1})
    monkeypatch.setattr(portal_router, "list_templates", listed)
    monkeypatch.setattr(portal_router, "create_template", created)

    channels = client.get(f"/api/portal/{slug}/channels").json()
    assert channels[0]["channel"] == "whatsapp_cloud" and channels[0]["supports_templates"] is True

    rows = client.get(f"/api/portal/{slug}/templates").json()
    assert [r["name"] for r in rows] == ["saludo_inicial", "promo"]
    assert listed.call_args.args == ("tok", "WABA1")

    bad = client.post(f"/api/portal/{slug}/templates", json={"name": "Bad Name", "body": "x"})
    assert bad.status_code == 422
    ok = client.post(
        f"/api/portal/{slug}/templates",
        json={"name": "bienvenida", "language": "es", "category": "UTILITY", "body": "Bienvenido {{1}}", "examples": ["Sam"]},
    )
    assert ok.status_code == 201 and ok.json()["status"] == "PENDING"
    assert created.call_args.kwargs["examples"] == ["Sam"]


def test_a_template_starts_a_conversation_and_the_window_rules_replies(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal_with_cloud_line(client)
    slug = customer["portal_slug"]
    monkeypatch.setattr(portal_router, "list_templates", AsyncMock(return_value=[APPROVED, PENDING]))
    sent = AsyncMock(side_effect=["wamid.1", "wamid.2", "wamid.3"])
    monkeypatch.setattr(portal_router, "send_template", sent)
    contact = client.post(f"/api/portal/{slug}/contacts", json={"name": "Sam", "phone": "573001112233"}).json()
    start = f"/api/portal/{slug}/contacts/{contact['id']}/conversations"

    assert client.post(start, json={"template": {"name": "promo", "language": "es", "variables": []}}).status_code == 409
    assert client.post(start, json={"template": {"name": "saludo_inicial", "language": "es", "variables": ["Sam"]}}).status_code == 422
    opened = client.post(start, json={"template": {"name": "saludo_inicial", "language": "es", "variables": ["Sam", "Outbound Co"]}})
    assert opened.status_code == 201, opened.text
    conv = opened.json()
    assert conv["mode"] == "human" and conv["assignee_name"] == "Ana" and conv["status"] == "open"
    assert conv["reply_window_open"] is False and conv["reply_window_until"] is None
    assert sent.call_args.kwargs == {"name": "saludo_inicial", "language": "es", "variables": ["Sam", "Outbound Co"]}
    assert sent.call_args.args[2] == "573001112233"
    kinds = [(m["kind"], m.get("activity", {}) or {}) for m in conv["messages"]]
    assert kinds[0] == ("activity", {"event": "started"})
    assert conv["messages"][-1]["content"] == "Hola Sam, te escribimos de Outbound Co.\n\nResponde para continuar."
    assert conv["messages"][-1]["external_message_id"] == "wamid.1"

    # The window is closed until the person answers: free text is refused, a template goes.
    base = f"/api/portal/{slug}/conversations/{conv['id']}"
    assert client.post(f"{base}/reply", json={"content": "Hola?"}).status_code == 409
    again = client.post(f"{base}/reply-template", json={"name": "saludo_inicial", "language": "es", "variables": ["Sam", "Outbound Co"]})
    assert again.status_code == 200
    # Only one open conversation per line and contact.
    assert client.post(start, json={"template": {"name": "saludo_inicial", "language": "es", "variables": ["Sam", "Outbound Co"]}}).status_code == 409

    # The person answers: the window opens for 24 h.
    with SessionLocal() as db:
        db.add(Message(conversation_id=uuid.UUID(conv["id"]), role="user", content="Hola!", sender_type="visitor"))
        db.commit()
    detail = client.get(base).json()
    assert detail["reply_window_open"] is True and detail["reply_window_until"]
    listed = client.get(f"/api/portal/{slug}/conversations").json()
    assert listed[0]["reply_window_open"] is True
    monkeypatch.setattr(portal_router, "send_channel_message", AsyncMock(return_value="wamid.free.1"))
    assert client.post(f"{base}/reply", json={"content": "Genial"}).status_code == 200

    # A day later the window has closed again.
    with SessionLocal() as db:
        for m in db.query(Message).filter(Message.conversation_id == uuid.UUID(conv["id"]), Message.sender_type == "visitor"):
            m.created_at = now_utc() - timedelta(hours=25)
        db.commit()
    assert client.get(base).json()["reply_window_open"] is False
    assert client.post(f"{base}/reply", json={"content": "Sigues ahi?"}).status_code == 409
