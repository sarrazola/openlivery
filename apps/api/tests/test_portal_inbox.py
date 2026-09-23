"""The portal inbox in one response, and the read receipt off the request."""

import asyncio
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from conftest import customer_conversation

from app.routers import portal as portal_router


def _portal(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Inbox Co", "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@inbox.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@inbox.co", "password": "secure-portal"})
    first = customer_conversation(client, agent["id"])["id"]
    second = customer_conversation(client, agent["id"])["id"]
    return customer["portal_slug"], first, second


def test_the_inbox_answers_list_counters_and_mine_together(authenticated_client: TestClient):
    client = authenticated_client
    slug, first, second = _portal(client)
    base = f"/api/portal/{slug}"
    client.patch(f"{base}/conversations/{first}/mode", json={"mode": "human"})

    inbox = client.get(f"{base}/inbox?status=open&limit=30&offset=0")
    assert inbox.status_code == 200
    payload = inbox.json()
    # The same page, total and counters the separate endpoints give.
    separate = client.get(f"{base}/conversations?status=open&limit=30&offset=0")
    assert [row["id"] for row in payload["items"]] == [row["id"] for row in separate.json()]
    assert payload["total"] == int(separate.headers["X-Total-Count"]) == 2
    assert payload["summary"] == client.get(f"{base}/conversations/summary").json()
    assert payload["summary"]["mine"] == 1
    # Taking over handed the conversation to the person: it is theirs.
    assert [row["id"] for row in payload["mine"]] == [first]
    assert payload["mine"][0]["title"]

    # Filters travel the same way.
    resolved = client.get(f"{base}/inbox?status=resolved").json()
    assert resolved["items"] == [] and resolved["total"] == 0
    assert resolved["summary"]["open"] == 2
    assert second not in [row["id"] for row in resolved["mine"]]


def test_marking_read_answers_before_the_channel_hears_about_it(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    slug, first, _ = _portal(client)
    from app.database import SessionLocal
    from app.models import Conversation, Message
    import uuid

    signal = AsyncMock()
    monkeypatch.setattr(portal_router, "signal_channel_read", signal)
    with SessionLocal() as db:
        conversation = db.get(Conversation, uuid.UUID(first))
        conversation.external_chat_id = "573001112233@s.whatsapp.net"
        db.add(Message(conversation_id=conversation.id, role="user", content="hola", sender_type="visitor", external_message_id="wa-in-9"))
        db.commit()

    assert client.post(f"/api/portal/{slug}/conversations/{first}/read").status_code == 204
    # The receipt goes out behind the response, on its own session.
    deadline = time.monotonic() + 3
    while not signal.await_count and time.monotonic() < deadline:
        time.sleep(0.02)
    signal.assert_awaited_once()
    _db, conversation, ids = signal.await_args.args
    assert str(conversation.id) == first
    assert ids == ["wa-in-9"]
    assert signal.await_args.kwargs == {"typing": False}
    assert client.get(f"/api/portal/{slug}/conversations/{first}").json()["unread"] is not True


def test_a_failing_read_receipt_is_logged_not_raised(authenticated_client: TestClient, monkeypatch, caplog):
    client = authenticated_client
    slug, first, _ = _portal(client)
    from app.database import SessionLocal
    from app.models import Conversation, Message
    import uuid

    monkeypatch.setattr(portal_router, "signal_channel_read", AsyncMock(side_effect=RuntimeError("meta down")))
    with SessionLocal() as db:
        conversation = db.get(Conversation, uuid.UUID(first))
        conversation.external_chat_id = "573001112233@s.whatsapp.net"
        db.add(Message(conversation_id=conversation.id, role="user", content="hola", sender_type="visitor", external_message_id="wa-in-1"))
        db.commit()

    assert client.post(f"/api/portal/{slug}/conversations/{first}/read").status_code == 204
    deadline = time.monotonic() + 3
    while portal_router._read_signals and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not portal_router._read_signals
    assert "read signal for conversation" in caplog.text
