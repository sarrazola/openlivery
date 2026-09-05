"""AI-initiated escalation: the built-in triggers, the business rules, and
where the conversation lands."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service
from app.services import whatsapp as whatsapp_service


def _setup(client: TestClient, company: str, member_names: list[str]):
    customer = client.post(
        "/api/clients",
        json={"name": company, "is_active": True},
    ).json()
    slug = customer["portal_slug"]
    for index, name in enumerate(member_names):
        client.post(
            f"/api/clients/{customer['id']}/portal-users",
            json={"name": name, "email": f"user{index}@{slug}.com", "password": "secure-portal"},
        )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{slug}/login", json={"email": f"user0@{slug}.com", "password": "secure-portal"})
    members = client.get(f"/api/portal/{slug}/members").json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Beto", "instructions": "", "personality": "", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    return customer, slug, members, agent, channel


def _inbound(client: TestClient, channel_id: str, text: str, message_id: str = "wa-in-1"):
    return client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers={"X-Bridge-Token": get_settings().whatsapp_bridge_token},
        json={"external_message_id": message_id, "remote_jid": "573001112233@s.whatsapp.net", "sender_name": "Sam", "text": text},
    )


def _escalating_completion(call_args: dict, farewell: str, captured: dict | None = None):
    async def fake(db, agent, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None):
        if captured is not None:
            captured["system"] = messages[0]["content"]
            captured["extra_specs"] = extra_specs
        if extra_specs:
            result, is_error = extra_specs[0].handler(call_args)
            assert not is_error, result
        return ai_service.Completion(text=farewell, input_tokens=1, output_tokens=1)

    return fake


def test_builtin_trigger_lands_in_the_general_destination(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, members, agent, channel = _setup(client, "Escala Co", ["Ana", "Beto"])
    team = client.post(
        f"/api/portal/{slug}/teams",
        json={"name": "EquipoSoporteX", "member_ids": [m["id"] for m in members]},
    ).json()
    client.put(f"/api/agents/{agent['id']}/escalation-rules", json={"default_team_id": team["id"], "rules": []})

    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    captured: dict = {}
    monkeypatch.setattr(
        whatsapp_inbound_service,
        "run_completion",
        _escalating_completion({"trigger": "frustration", "reason": "cliente molesto"}, "Lamento la experiencia. Ya mismo te pongo en contacto con una persona del equipo.", captured),
    )
    response = _inbound(client, channel["id"], "esto es un desastre, nadie me respeta la reserva")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "human"
    assert body["reply"].startswith("Lamento")

    conversation = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert conversation["mode"] == "human"
    assert conversation["team_id"] == team["id"]
    assert conversation["assignee_id"] in {m["id"] for m in members}, "routing must hand it to a member"
    events = [m["activity"]["event"] for m in conversation["messages"] if m.get("kind") == "activity" and m.get("activity")]
    assert "escalated" in events and "team_assigned" in events
    # The farewell precedes the hand-over in the thread.
    kinds = [(m.get("kind"), m.get("sender_type")) for m in conversation["messages"]]
    assert kinds.index(("message", "ai")) < kinds.index(("activity", "system"))

    # The prompt got the escalation scaffolding but never the destinations.
    assert "ESCALAMIENTO" in captured["system"]
    assert "EquipoSoporteX" not in captured["system"]

    # The next message is for people, not for the AI.
    follow_up = _inbound(client, channel["id"], "sigo esperando", message_id="wa-in-2").json()
    assert follow_up["mode"] == "human" and follow_up["reply"] is None


def test_business_rule_routes_to_its_own_destination(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, members, agent, channel = _setup(client, "Reglas Co", ["Ana"])
    ventas = client.post(f"/api/portal/{slug}/teams", json={"name": "VentasX", "member_ids": [members[0]["id"]]}).json()
    soporte = client.post(f"/api/portal/{slug}/teams", json={"name": "SoporteX", "is_default": True, "member_ids": [members[0]["id"]]}).json()
    client.put(
        f"/api/agents/{agent['id']}/escalation-rules",
        json={"rules": [{"condition": "Quiere cotizar o comprar planes corporativos", "team_id": ventas["id"]}]},
    )

    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    captured: dict = {}
    monkeypatch.setattr(
        whatsapp_inbound_service,
        "run_completion",
        _escalating_completion({"rule": 1, "reason": "quiere cotizar"}, "Con gusto, te comunico con el área encargada.", captured),
    )
    body = _inbound(client, channel["id"], "quiero cotizar un plan para mi empresa").json()
    conversation = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert conversation["team_id"] == ventas["id"], "the rule's destination wins over the default tray"
    assert conversation["team_name"] == "VentasX"
    assert "[1] Quiere cotizar" in captured["system"]
    assert soporte


def test_without_anywhere_to_land_the_tool_is_not_offered(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, members, agent, channel = _setup(client, "SinEquipos Co", ["Ana"])

    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    captured: dict = {}

    async def fake(db, agent_row, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None):
        captured["extra_specs"] = extra_specs
        captured["system"] = messages[0]["content"]
        return ai_service.Completion(text="Con gusto te ayudo.", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake)
    body = _inbound(client, channel["id"], "hola").json()
    assert body["mode"] == "ai"
    assert captured["extra_specs"] is None
    assert "ESCALAMIENTO" not in captured["system"]


def test_handler_forgives_a_bogus_rule_number_when_the_trigger_is_valid():
    from app.services.escalation import EscalationRequest, build_escalation_spec

    holder: list[EscalationRequest] = []
    spec = build_escalation_spec([], holder)
    # No business rules: the schema must not even offer "rule"...
    assert "rule" not in spec.input_schema["properties"]
    # ...and a model that sends one anyway still escalates via the trigger.
    result, is_error = spec.handler({"rule": 1, "trigger": "frustration", "reason": "molesto"})
    assert not is_error, result
    assert holder and holder[0].trigger == "frustration" and holder[0].rule is None
    # Case sloppiness is tolerated; pure nonsense is not.
    _, is_error = spec.handler({"trigger": "Frustration"})
    assert not is_error
    result, is_error = spec.handler({"trigger": "whatever"})
    assert is_error


def test_builtin_triggers_can_be_switched_off(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, slug, members, agent, channel = _setup(client, "Toggle Co", ["Ana"])
    team = client.post(f"/api/portal/{slug}/teams", json={"name": "SoporteT", "is_default": True, "member_ids": [members[0]["id"]]}).json()
    base = f"/api/agents/{agent['id']}/escalation-rules"
    assert client.get(base).json()["builtin_enabled"] is True

    # Off with no business rules: the tool disappears from the prompt entirely.
    assert client.put(base, json={"builtin_enabled": False, "rules": []}).json()["builtin_enabled"] is False
    monkeypatch.setattr(whatsapp_service, "bridge_command", AsyncMock(return_value={}))
    captured: dict = {}

    async def fake(db, agent_row, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None):
        captured["extra_specs"] = extra_specs
        captured["system"] = messages[0]["content"]
        return ai_service.Completion(text="Con gusto te ayudo.", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake)
    body = _inbound(client, channel["id"], "hola").json()
    assert body["mode"] == "ai"
    assert captured["extra_specs"] is None and "ESCALAMIENTO" not in captured["system"]

    # A business rule brings the tool back, restricted to rule numbers.
    client.put(
        base,
        json={"builtin_enabled": False, "rules": [{"condition": "Pide una cotización corporativa", "team_id": team["id"]}]},
    )
    body = _inbound(client, channel["id"], "quiero cotizar", message_id="wa-in-2").json()
    assert captured["extra_specs"] is not None
    spec = captured["extra_specs"][0]
    assert "trigger" not in spec.input_schema["properties"] and "rule" in spec.input_schema["properties"]
    assert "frustración" not in captured["system"].split("ESCALAMIENTO", 1)[1].split("[1]")[0]
    assert "[1] Pide una cotización corporativa" in captured["system"]
    # The handler refuses trigger-only calls while the switch is off.
    result, is_error = spec.handler({"trigger": "frustration", "reason": "molesto"})
    assert is_error
    _, is_error = spec.handler({"rule": 1, "reason": "cotización"})
    assert not is_error
