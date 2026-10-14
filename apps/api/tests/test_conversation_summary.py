"""A conversation summary is written only when a person asks for it.

It goes through the conversation agent's model and key, is recorded as usage
with purpose "summary", is stored for the team, and asking again before new
messages arrive does not call the model. Summarizing does not move the
conversation in the inbox."""
from datetime import date, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.models import Conversation, Message, UsageRecord
from app.services import summary as summary_service
from app.services.ai import Completion
from tests.conftest import TestingSession, customer_conversation


def _portal_with_conversation(client: TestClient, *, key: bool = True):
    customer = client.post("/api/clients", json={"name": "Muebles Co"}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@muebles.com", "password": "secure-portal", "role": "agent"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Liv", "model": "openai/gpt-6-luna"}).json()
    if key:
        client.put("/api/providers/openrouter", json={"api_key": "secret"})
    conversation = customer_conversation(client, agent["id"])
    with TestingSession() as db:
        for role, text in (("user", "Quiero un tocador blanco"), ("assistant", "Claro, ¿de qué tamaño?"), ("user", "1,20 m, para Bogotá")):
            db.add(Message(conversation_id=conversation["id"], role=role, content=text))
        db.commit()
    slug = customer["portal_slug"]
    assert client.post(f"/api/portal/{slug}/login", json={"email": "ana@muebles.com", "password": "secure-portal"}).status_code == 200
    return slug, conversation["id"]


def _stub(monkeypatch, text="- Quiere un tocador blanco de 1,20 m\\n- Entrega en Bogotá"):
    completion = AsyncMock(return_value=Completion(text=text, input_tokens=400, output_tokens=60))
    monkeypatch.setattr(summary_service, "chat_completion", completion)
    return completion


def test_a_summary_is_written_on_request_billed_and_reused(authenticated_client: TestClient, monkeypatch):
    slug, conversation_id = _portal_with_conversation(authenticated_client)
    path = f"/api/portal/{slug}/conversations/{conversation_id}/summary"
    with TestingSession() as db:
        before = db.get(Conversation, conversation_id).updated_at

    empty = authenticated_client.get(path).json()
    assert empty["summary"] is None and empty["current_message_count"] == 3 and empty["stale"] is False

    completion = _stub(monkeypatch)
    written = authenticated_client.post(path, json={"language": "es"}).json()
    assert written["summary"].startswith("- Quiere") and written["message_count"] == 3 and written["stale"] is False
    assert written["summary_by"] == "Ana"
    assert completion.await_count == 1
    prompt = completion.await_args.args[4]
    assert "Spanish" in prompt[0]["content"] and "Customer: Quiero un tocador blanco" in prompt[1]["content"]

    # Asked again with nothing new: the stored one, no second call.
    again = authenticated_client.post(path, json={"language": "es"}).json()
    assert again["summary"] == written["summary"] and completion.await_count == 1

    with TestingSession() as db:
        records = db.query(UsageRecord).filter(UsageRecord.conversation_id == conversation_id).all()
        assert [(r.purpose, r.input_tokens) for r in records] == [("summary", 400)]
        assert db.get(Conversation, conversation_id).updated_at == before, "a summary does not move the conversation"

    # A new message makes it stale; asking again writes a new one.
    with TestingSession() as db:
        db.add(Message(conversation_id=conversation_id, role="user", content="¿Tienen en negro?"))
        db.commit()
    assert authenticated_client.get(path).json()["stale"] is True
    authenticated_client.post(path, json={"language": "en"})
    assert completion.await_count == 2 and "English" in completion.await_args.args[4][0]["content"]

    today = date.today()
    report = authenticated_client.get(f"/api/reports/replies?from={today - timedelta(days=1)}&to={today + timedelta(days=1)}").json()
    assert {item["purpose"] for item in report["items"]} == {"summary"}


def test_no_key_or_no_messages_is_a_clear_conflict(authenticated_client: TestClient, monkeypatch):
    slug, conversation_id = _portal_with_conversation(authenticated_client, key=False)
    completion = _stub(monkeypatch)
    response = authenticated_client.post(f"/api/portal/{slug}/conversations/{conversation_id}/summary", json={})
    assert response.status_code == 409 and "key" in response.json()["detail"]
    completion.assert_not_awaited()
