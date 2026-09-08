"""Mobile disclosures reflect only the signed-in client and expose no secrets."""

import uuid

import pytest

from app.config import get_settings
from app.models import Agent, AgentTool, Client
from app.services import mobile_privacy, providers
from conftest import TestingSession
from test_mobile_and_push import _client_with_portal, _sign_in


def _login(client):
    result = _sign_in(client, "owner@barberco.com", "legacy-portal-pw")
    assert result.status_code == 200
    return result.json()


def test_disclosure_is_client_scoped_and_includes_separate_media_provider(authenticated_client, monkeypatch):
    customer = _client_with_portal(authenticated_client)
    other = authenticated_client.post("/api/clients", json={"name": "Other business"}).json()
    with TestingSession() as db:
        owner = db.get(Client, uuid.UUID(customer["id"]))
        agent = Agent(client_id=owner.id, agency_id=owner.agency_id, name="Support", provider="anthropic", is_active=False)
        foreign = Agent(client_id=uuid.UUID(other["id"]), agency_id=owner.agency_id, name="Other")
        db.add_all([agent, foreign])
        db.flush()
        db.add_all([
            AgentTool(agent_id=agent.id, name="calendar", type="http", url="https://user:private-password@calendar.example.test/private-path?token=secret#secret"),
            AgentTool(agent_id=agent.id, name="disabled", type="http", enabled=False, url="https://disabled.example.test"),
            AgentTool(agent_id=foreign.id, name="foreign", type="mcp", url="https://foreign.example.test/private"),
        ])
        db.commit()
    monkeypatch.setattr(providers, "decrypt_secret", lambda *_: pytest.fail("Disclosure must not decrypt a key"))
    result = _login(authenticated_client)
    rows = result["privacy"]["destinations"]
    assert {row["host"] for row in rows} == {"api.anthropic.com", "api.openai.com", "calendar.example.test"}
    assert next(row for row in rows if row["name"] == "OpenAI")["capabilities"] == ["audio", "image"]
    assert next(row for row in rows if row["name"] == "Anthropic")["capabilities"] == ["conversation"]
    for hidden in ("private-password", "private-path", "secret", "foreign.example.test", "disabled.example.test"):
        assert hidden not in str(result["privacy"])
    refreshed = authenticated_client.get("/api/mobile/session", headers={"Authorization": f"Bearer {result['token']}"})
    assert refreshed.json()["privacy"] == result["privacy"]


def test_destination_or_capability_change_updates_disclosure_version(authenticated_client):
    customer = _client_with_portal(authenticated_client)
    before = _login(authenticated_client)["privacy"]
    with TestingSession() as db:
        owner = db.get(Client, uuid.UUID(customer["id"]))
        agent = Agent(client_id=owner.id, agency_id=owner.agency_id, name="Support", provider="openai")
        db.add(agent)
        db.commit()
        agent_id = agent.id
    added = _login(authenticated_client)["privacy"]
    assert added["version"] != before["version"]
    with TestingSession() as db:
        agent = db.get(Agent, agent_id)
        agent.audio_enabled = False
        db.commit()
    changed = _login(authenticated_client)["privacy"]
    assert changed["version"] != added["version"]
    assert "audio" not in changed["destinations"][0]["capabilities"]


def test_push_disclosure_strips_webhook_credentials(authenticated_client, monkeypatch):
    _client_with_portal(authenticated_client)
    monkeypatch.setattr(get_settings(), "push_provider", "webhook")
    monkeypatch.setattr(get_settings(), "push_webhook_url", "https://private:password@push.example.test/secret?key=hidden")
    result = _login(authenticated_client)["privacy"]
    assert result["destinations"] == [{"kind": "notification", "name": "Notification service", "host": "push.example.test", "capabilities": ["notifications"]}]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://[invalid", "file:///private/path"])
def test_invalid_destination_never_exposes_raw_url(url):
    assert mobile_privacy.destination_host(url) == ""


def test_inactive_client_cannot_read_mobile_identity_or_disclosure(authenticated_client):
    customer = _client_with_portal(authenticated_client)
    signed_in = _login(authenticated_client)
    with TestingSession() as db:
        db.get(Client, uuid.UUID(customer["id"])).is_active = False
        db.commit()
    assert _sign_in(authenticated_client, "owner@barberco.com", "legacy-portal-pw").status_code == 401
    response = authenticated_client.get("/api/mobile/session", headers={"Authorization": f"Bearer {signed_in['token']}"})
    assert response.status_code == 401
