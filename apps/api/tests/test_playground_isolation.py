from datetime import date
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.routers import widget as widget_router
from app.services import ai as ai_service


def _setup(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Luna Cafe"}).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post("/api/agents", json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Luna", "is_active": True}).json()
    rehearsal = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    assert rehearsal["channel"] == "playground"
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Equipo", "email": "equipo@luna.com", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    assert client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "equipo@luna.com", "password": "secure-portal"}).status_code == 200
    return customer, agent, rehearsal


def test_playground_conversations_stay_out_of_the_portal_and_its_reports(authenticated_client: TestClient):
    client = authenticated_client
    customer, agent, rehearsal = _setup(client)
    slug = customer["portal_slug"]

    inbox = client.get(f"/api/portal/{slug}/conversations")
    assert inbox.status_code == 200
    assert all(item["id"] != rehearsal["id"] for item in inbox.json())

    today = date.today().isoformat()
    report = client.get(f"/api/portal/{slug}/reports", params={"from": today, "to": today})
    assert report.status_code == 200, report.text
    assert report.json()["started"] == 0
    assert all(row["channel"] != "playground" for row in report.json()["by_channel"])

    # The agency's own views keep it, flagged by its channel.
    metrics = client.get("/api/dashboard/metrics", params={"days": 7}).json()
    assert metrics["by_channel"].get("playground") == 1
    mine = client.get("/api/conversations", params={"agent_id": agent["id"]}).json()
    assert any(item["id"] == rehearsal["id"] for item in mine)


def test_only_playground_conversations_can_be_deleted(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent, rehearsal = _setup(client)
    assert client.delete(f"/api/conversations/{rehearsal['id']}").status_code == 204
    assert client.get(f"/api/conversations/{rehearsal['id']}").status_code == 404

    channel = client.put(f"/api/webchat/channels/{customer['id']}", json={"agent_id": agent["id"], "is_enabled": True}).json()
    monkeypatch.setattr(widget_router, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hola")))
    assert client.post(f"/api/widget/{channel['public_id']}/messages", json={"session_id": "s1", "content": "hola"}).status_code == 200
    real = next(item for item in client.get("/api/conversations/inbox").json() if item["channel"] == "widget")
    assert client.delete(f"/api/conversations/{real['id']}").status_code == 409
