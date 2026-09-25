"""Contact details the agent collects: the client's field definitions, what
each agent asks for and where, the prompt section, the save tool and the
values landing on the contact."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service
from app.services import whatsapp as whatsapp_service
from app.services.capture import TOOL_NAME


def _setup(client: TestClient, company: str = "Captura Co"):
    customer = client.post("/api/clients", json={"name": company, "is_active": True}).json()
    slug = customer["portal_slug"]
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": f"ana@{slug}.com", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{slug}/login", json={"email": f"ana@{slug}.com", "password": "secure-portal"})
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini", "name": "Beto", "instructions": "", "personality": "", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    return customer, slug, agent, channel


def _inbound(client: TestClient, channel_id: str, text: str, message_id: str, phone: str = "573001112233"):
    return client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers={"X-Bridge-Token": get_settings().whatsapp_bridge_token},
        json={"external_message_id": message_id, "remote_jid": f"{phone}@s.whatsapp.net", "sender_name": "Sam", "text": text},
    )


def _completion(calls: list[dict], reply: str, captured: dict):
    """A fake generation that calls the save tool with each of ``calls`` and
    records what the model was shown."""
    async def fake(db, agent, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None):
        captured["system"] = messages[0]["content"]
        captured["specs"] = {spec.name: spec for spec in (extra_specs or [])}
        captured["results"] = []
        spec = captured["specs"].get(TOOL_NAME)
        for args in calls:
            assert spec is not None, "the save tool was not offered"
            captured["results"].append(spec.handler(args))
        return ai_service.Completion(text=reply, input_tokens=1, output_tokens=1)
    return fake


def test_client_defines_fields_and_agent_picks_them(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, agent, channel = _setup(client)
    base = f"/api/clients/{customer['id']}/contact-fields"

    builtins = client.get(base).json()
    assert [f["key"] for f in builtins] == ["name", "email", "phone"] and all(f["builtin"] for f in builtins)

    created = client.post(base, json={"key": "presupuesto", "label": "Presupuesto", "kind": "number", "description": "Monto que planea invertir"})
    assert created.status_code == 201, created.text
    assert client.post(base, json={"key": "presupuesto", "label": "Otra"}).status_code == 409
    assert client.post(base, json={"key": "email", "label": "Correo"}).status_code == 409
    assert client.post(base, json={"key": "Presupuesto Total", "label": "x"}).status_code == 422
    assert client.post(base, json={"key": "ciudad", "label": "Ciudad", "kind": "date"}).status_code == 422

    renamed = client.patch(f"{base}/{created.json()['id']}", json={"label": "Presupuesto estimado"})
    assert renamed.status_code == 200 and renamed.json()["label"] == "Presupuesto estimado"
    assert [f["key"] for f in client.get(f"/api/portal/{slug}/contact-fields").json()] == ["name", "email", "phone", "presupuesto"]

    config = client.put(
        f"/api/agents/{agent['id']}/capture",
        json={"enabled": True, "fields": [
            {"field_key": "email", "instruction": "Ask once the customer shows interest", "channels": ["whatsapp"]},
            {"field_key": "presupuesto", "instruction": "When they ask for prices"},
        ]},
    )
    assert config.status_code == 200, config.text
    body = config.json()
    assert body["enabled"] is True
    assert [(f["field_key"], f["label"], f["channels"]) for f in body["fields"]] == [
        ("email", "Correo", ["whatsapp"]), ("presupuesto", "Presupuesto estimado", []),
    ]
    assert [f["key"] for f in body["available"]] == ["name", "email", "phone", "presupuesto"]
    assert client.put(f"/api/agents/{agent['id']}/capture", json={"enabled": True, "fields": [{"field_key": "nope"}]}).status_code == 422
    assert client.put(f"/api/agents/{agent['id']}/capture", json={"enabled": True, "fields": [{"field_key": "email", "channels": ["sms"]}]}).status_code == 422
    assert client.put(f"/api/agents/{agent['id']}/capture", json={"enabled": True, "fields": [{"field_key": "email"}, {"field_key": "email"}]}).status_code == 422

    # Deleting the definition removes the agent's request for it.
    assert client.delete(f"{base}/{created.json()['id']}").status_code == 204
    assert [f["field_key"] for f in client.get(f"/api/agents/{agent['id']}/capture").json()["fields"]] == ["email"]


def test_agent_asks_for_what_is_missing_and_saves_it(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, agent, channel = _setup(client, "Guarda Co")
    client.post(f"/api/clients/{customer['id']}/contact-fields", json={"key": "presupuesto", "label": "Presupuesto", "kind": "number", "description": "Monto que planea invertir"})
    client.put(
        f"/api/agents/{agent['id']}/capture",
        json={"enabled": True, "fields": [
            {"field_key": "name"},
            {"field_key": "email", "instruction": "Pídelo cuando muestre interés"},
            {"field_key": "presupuesto", "instruction": "Cuando pregunte precios"},
        ]},
    )
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))

    captured: dict = {}
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", _completion(
        [{"field": "email", "value": " Sam@Example.com "}, {"field": "presupuesto", "value": "abc"}, {"field": "presupuesto", "value": "2500"}],
        "Perfecto, anotado.", captured,
    ))
    body = _inbound(client, channel["id"], "mi correo es sam@example.com y tengo 2500", "m1").json()
    assert body["reply"] == "Perfecto, anotado."
    # The name came with the message, so only the two unknown details are listed.
    assert "Datos por capturar" in captured["system"]
    assert "**Correo** (`email`): Pídelo cuando muestre interés" in captured["system"]
    assert "**Presupuesto** (`presupuesto`): Monto que planea invertir Cuando pregunte precios" in captured["system"]
    assert "`name`" not in captured["system"]
    assert captured["specs"][TOOL_NAME].input_schema["properties"]["field"]["enum"] == ["email", "presupuesto"]
    assert captured["results"][0][1] is False
    assert captured["results"][1] == ("That is not a number.", True)
    assert captured["results"][2][1] is False

    contacts = client.get(f"/api/portal/{slug}/contacts").json()
    assert len(contacts) == 1
    assert contacts[0]["email"] == "sam@example.com"
    assert contacts[0]["attributes"] == {"presupuesto": "2500"}

    # Next case with the same person: the values are context, nothing is pending, no tool.
    client.patch(f"/api/conversations/{body['conversation_id']}/status", json={"status": "resolved"})
    captured.clear()
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", _completion([], "Hola de nuevo", captured))
    _inbound(client, channel["id"], "hola otra vez", "m2")
    assert "**Correo:** sam@example.com" in captured["system"]
    assert "**Presupuesto:** 2500" in captured["system"]
    assert "Datos por capturar" not in captured["system"]
    assert TOOL_NAME not in captured["specs"]


def test_fields_limited_to_a_channel_are_not_asked_elsewhere(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, agent, channel = _setup(client, "Canal Co")
    client.put(
        f"/api/agents/{agent['id']}/capture",
        json={"enabled": True, "fields": [{"field_key": "email", "channels": ["widget"]}]},
    )
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    captured: dict = {}
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", _completion([], "Hola", captured))
    _inbound(client, channel["id"], "hola", "m1")
    assert "Datos por capturar" not in captured["system"]
    assert TOOL_NAME not in captured["specs"]

    # Switched off, nothing is asked anywhere.
    client.put(f"/api/agents/{agent['id']}/capture", json={"enabled": False, "fields": [{"field_key": "email"}]})
    captured.clear()
    _inbound(client, channel["id"], "hola", "m2")
    assert TOOL_NAME not in captured["specs"]


def test_portal_edits_custom_values(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, agent, channel = _setup(client, "Portal Co")
    client.post(f"/api/clients/{customer['id']}/contact-fields", json={"key": "ciudad", "label": "Ciudad"})
    base = f"/api/portal/{slug}/contacts"
    created = client.post(base, json={"name": "Sam", "phone": "+57 300 111 2233", "attributes": {"ciudad": " Bogotá "}})
    assert created.status_code == 201, created.text
    assert created.json()["attributes"] == {"ciudad": "Bogotá"}
    contact_id = created.json()["id"]
    assert client.patch(f"{base}/{contact_id}", json={"attributes": {"nope": "x"}}).status_code == 422
    assert client.patch(f"{base}/{contact_id}", json={"attributes": {"email": "x"}}).status_code == 422
    updated = client.patch(f"{base}/{contact_id}", json={"attributes": {"ciudad": ""}})
    assert updated.status_code == 200 and updated.json()["attributes"] == {}
