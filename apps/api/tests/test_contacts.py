import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service


def _portal(client: TestClient, name: str = "Contacts Co"):
    customer = client.post(
        "/api/clients",
        json={"name": name, "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "Ana", "email": f"ana@{customer['portal_slug']}.com", "password": "secure-portal"},
    )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": f"ana@{customer['portal_slug']}.com", "password": "secure-portal"})
    return customer


def test_portal_manages_contacts(authenticated_client: TestClient):
    client = authenticated_client
    customer = _portal(client)
    base = f"/api/portal/{customer['portal_slug']}/contacts"

    created = client.post(base, json={"name": "Sam Pérez", "phone": "+57 300 111 2233", "email": "sam@example.com", "notes": "Prefers mornings"})
    assert created.status_code == 201, created.text
    contact = created.json()
    assert contact["phone"] == "573001112233"
    assert contact["conversation_count"] == 0

    assert client.post(base, json={"name": "Dup", "phone": "573001112233"}).status_code == 409
    assert client.post(base, json={"name": "Short", "phone": "12345"}).status_code == 422

    assert [row["id"] for row in client.get(f"{base}?search=sam").json()] == [contact["id"]]
    assert [row["id"] for row in client.get(f"{base}?search=3001112").json()] == [contact["id"]]
    assert client.get(f"{base}?search=nobody").json() == []

    updated = client.patch(f"{base}/{contact['id']}", json={"name": "Samuel Pérez", "notes": ""})
    assert updated.status_code == 200 and updated.json()["name"] == "Samuel Pérez" and updated.json()["notes"] == ""

    assert client.delete(f"{base}/{contact['id']}").status_code == 204
    assert client.get(f"{base}/{contact['id']}").status_code == 404


def test_inbound_creates_the_contact_and_a_new_case_after_resolution(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal(client, "Cases Co")
    slug = customer["portal_slug"]
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Beto", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    headers = {"X-Bridge-Token": get_settings().whatsapp_bridge_token}
    completion = AsyncMock(return_value=ai_service.Completion(text="Hello!", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", completion)
    monkeypatch.setattr(whatsapp_inbound_service.get_settings(), "reply_debounce_seconds", 0)

    def inbound(message_id: str, text: str, name: str | None = "Sam"):
        return client.post(
            f"/api/internal/whatsapp/channels/{channel['id']}/inbound",
            json={"external_message_id": message_id, "remote_jid": "573001112233@s.whatsapp.net", "sender_name": name, "text": text},
            headers=headers,
        ).json()

    first_id = inbound("m1", "Hola, quiero reservar")["conversation_id"]
    contacts = client.get(f"/api/portal/{slug}/contacts").json()
    assert len(contacts) == 1 and contacts[0]["phone"] == "573001112233" and contacts[0]["name"] == "Sam"
    contact_id = contacts[0]["id"]
    assert client.get(f"/api/conversations/{first_id}").json()["contact_id"] == contact_id

    # While the case is open, more messages join it.
    assert inbound("m2", "para mañana")["conversation_id"] == first_id

    client.patch(f"/api/conversations/{first_id}/status", json={"status": "resolved"})
    second_id = inbound("m3", "Hola de nuevo")["conversation_id"]
    assert second_id != first_id
    assert client.get(f"/api/conversations/{first_id}").json()["status"] == "resolved"
    assert client.get(f"/api/conversations/{second_id}").json()["contact_id"] == contact_id

    history = client.get(f"/api/portal/{slug}/contacts/{contact_id}/conversations").json()
    assert [row["id"] for row in history] == [second_id, first_id]
    assert [row["status"] for row in history] == ["open", "resolved"]
    summary = client.get(f"/api/portal/{slug}/contacts/{contact_id}").json()
    assert summary["conversation_count"] == 2 and summary["open_count"] == 1

    # The model hears about the previous case when a new one opens.
    sent = completion.call_args.args[4]
    assert "CONTEXTO DEL CONTACTO" in sent[0]["content"]
    assert "quiero reservar" in sent[0]["content"]

    # Renaming the contact renames its conversations everywhere.
    client.patch(f"/api/portal/{slug}/contacts/{contact_id}", json={"name": "Samuel"})
    titles = {row["title"] for row in client.get(f"/api/portal/{slug}/contacts/{contact_id}/conversations").json()}
    assert titles == {"Samuel"}
