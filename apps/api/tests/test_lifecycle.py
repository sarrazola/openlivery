"""Deleting things without losing history.

Conversations are archived first and deleted only from the archive; deleting
an agent keeps the conversations it handled; deleting a client is previewed
with counts; an inactive client is switched off everywhere.
"""

import asyncio
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Agent, AgentQA, Conversation, KnowledgeDocument, WhatsAppChannel
from app.services import whatsapp_inbound as inbound_service
from app.services.ai import Completion
from conftest import customer_conversation


def _portal(client: TestClient, name: str = "Archive Co"):
    customer = client.post("/api/clients", json={"name": name, "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@archive.com", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@archive.com", "password": "secure-portal"})
    return customer, agent


def test_conversations_are_archived_before_they_can_be_deleted(authenticated_client: TestClient):
    client = authenticated_client
    customer, agent = _portal(client)
    base = f"/api/portal/{customer['portal_slug']}/conversations"
    first = customer_conversation(client, agent["id"])["id"]
    second = customer_conversation(client, agent["id"])["id"]
    third = customer_conversation(client, agent["id"])["id"]

    # Nothing can be deleted straight from an inbox.
    assert client.delete(f"{base}/{first}").status_code == 409

    # Archiving an open conversation closes it first and leaves a trace.
    archived = client.patch(f"{base}/{first}/archive", json={"archived": True}).json()
    assert archived["status"] == "resolved" and archived["archived_at"]
    assert [m["activity"]["event"] for m in archived["messages"] if m["kind"] == "activity"][-2:] == ["resolved", "archived"]

    # It left the inboxes, it shows in the archive, and the badges agree.
    assert first not in {row["id"] for row in client.get(f"{base}?status=open").json()}
    assert first not in {row["id"] for row in client.get(f"{base}?status=resolved").json()}
    assert [row["id"] for row in client.get(f"{base}?archived=1").json()] == [first]
    summary = client.get(f"{base}/summary").json()
    assert (summary["open"], summary["resolved"], summary["archived"]) == (2, 0, 1)
    # The agency's inbox hides it too.
    assert first not in {row["id"] for row in client.get("/api/conversations/inbox").json()}

    # Restoring brings it back as resolved, not open.
    restored = client.patch(f"{base}/{first}/archive", json={"archived": False}).json()
    assert restored["status"] == "resolved" and restored["archived_at"] is None
    assert [row["id"] for row in client.get(f"{base}?status=resolved").json()] == [first]

    # Archive every resolved conversation at once: open ones stay put.
    client.patch(f"{base}/{second}/status", json={"status": "resolved"})
    assert client.post(f"{base}/archive-resolved").json() == {"count": 2}
    assert {row["id"] for row in client.get(f"{base}?archived=1").json()} == {first, second}
    assert [row["id"] for row in client.get(f"{base}?status=open").json()] == [third]

    # Deleting: one from the archive, a selection (open ones in it are ignored), then the rest. Final.
    assert client.delete(f"{base}/{first}").status_code == 204
    assert client.post(f"{base}/delete-archived", json={"ids": [third]}).json() == {"count": 0}
    assert client.post(f"{base}/delete-archived", json={"ids": [second, third]}).json() == {"count": 1}
    assert client.post(f"{base}/delete-archived").json() == {"count": 0}
    assert client.get(f"{base}?archived=1").json() == []
    assert client.get(f"{base}/{second}").status_code == 404
    assert client.get(f"{base}/summary").json()["archived"] == 0


def test_deleting_an_agent_keeps_its_conversations(authenticated_client: TestClient):
    client = authenticated_client
    customer, agent = _portal(client)
    slug = customer["portal_slug"]
    conversation_id = customer_conversation(client, agent["id"])["id"]
    client.post(f"/api/agents/{agent['id']}/qa", json={"question": "Hours?", "answer": "9 to 5"})
    other = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Backup", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()

    assert client.delete(f"/api/agents/{agent['id']}").status_code == 204

    # Gone from every list, but the conversation is still there under its name.
    assert client.get(f"/api/agents/{agent['id']}").status_code == 404
    assert [a["id"] for a in client.get("/api/agents").json()] == [other["id"]]
    assert [a["id"] for a in client.get(f"/api/clients/{customer['id']}").json()["agents"]] == [other["id"]]
    assert [a["id"] for a in client.get(f"/api/portal/{slug}/agents").json()] == [other["id"]]
    detail = client.get(f"/api/portal/{slug}/conversations/{conversation_id}").json()
    assert detail["agent_id"] == agent["id"]
    inbox = client.get("/api/conversations/inbox").json()
    assert next(row for row in inbox if row["id"] == conversation_id)["agent_name"] == "Host"

    with SessionLocal() as db:
        row = db.get(Agent, agent["id"])
        assert row is not None and row.deleted_at is not None and row.is_active is False
        assert db.scalar(select(AgentQA).where(AgentQA.agent_id == row.id)) is None
        assert db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.agent_id == row.id)) is None
        assert db.get(Conversation, conversation_id) is not None


def test_deleting_an_agent_that_answers_a_channel_is_refused(authenticated_client: TestClient):
    client = authenticated_client
    customer, agent = _portal(client)
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    refused = client.delete(f"/api/agents/{agent['id']}")
    assert refused.status_code == 409
    assert "Assign another agent" in refused.json()["detail"]
    assert client.get(f"/api/agents/{agent['id']}").status_code == 200


def test_client_deletion_is_previewed_with_counts(authenticated_client: TestClient):
    client = authenticated_client
    customer, agent = _portal(client)
    customer_conversation(client, agent["id"])
    customer_conversation(client, agent["id"])
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})

    preview = client.get(f"/api/clients/{customer['id']}/deletion-preview").json()
    assert preview == {"agents": 1, "channels": 1, "conversations": 2, "contacts": 0, "portal_users": 1}

    assert client.delete(f"/api/clients/{customer['id']}").status_code == 204
    assert client.get(f"/api/clients/{customer['id']}").status_code == 404
    assert client.get("/api/agents").json() == []
    assert client.get("/api/conversations/inbox").json() == []


def test_an_inactive_client_is_switched_off_everywhere(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent = _portal(client)
    slug = customer["portal_slug"]
    client.put("/api/providers/openai", json={"api_key": "secret"})
    client.patch(f"/api/agents/{agent['id']}", json={"model": "gpt-4.1-mini"})
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    completion = AsyncMock(return_value=Completion(text="Should not be sent"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)

    client.patch(f"/api/clients/{customer['id']}", json={"is_active": False})

    # The portal is closed to its people.
    assert client.post(f"/api/portal/{slug}/login", json={"email": "ana@archive.com", "password": "secure-portal"}).status_code == 404

    # A WhatsApp message is kept, but nobody answers and no model is called.
    db = SessionLocal()
    try:
        channel = db.scalar(select(WhatsAppChannel))
        result = asyncio.run(
            inbound_service.process_inbound(
                db,
                channel,
                inbound_service.InboundMessage(
                    external_message_id="wa-1", external_chat_id="573001112233@s.whatsapp.net", sender_name="Cliente", text="hola"
                ),
                conversation_channel="whatsapp",
                channel_fk_field="whatsapp_channel_id",
            )
        )
        assert result.accepted and result.reply is None
        db.refresh(channel)
        assert "inactive" in (channel.last_error or "")
    finally:
        db.close()
    completion.assert_not_awaited()

    # Reactivating opens the portal again.
    client.patch(f"/api/clients/{customer['id']}", json={"is_active": True})
    assert client.post(f"/api/portal/{slug}/login", json={"email": "ana@archive.com", "password": "secure-portal"}).status_code == 200


def test_a_blocked_contact_talks_to_a_wall(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent = _portal(client)
    slug = customer["portal_slug"]
    client.put("/api/providers/openai", json={"api_key": "secret"})
    client.patch(f"/api/agents/{agent['id']}", json={"model": "gpt-4.1-mini", "reply_delay_min_seconds": 0, "reply_delay_max_seconds": 0})
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    completion = AsyncMock(return_value=Completion(text="Hi there"))
    monkeypatch.setattr(inbound_service, "run_completion", completion)
    monkeypatch.setattr(inbound_service, "send_channel_message", AsyncMock(return_value="wamid-out"))

    def inbound(db, channel, external_id: str, text: str):
        return asyncio.run(
            inbound_service.process_inbound(
                db,
                channel,
                inbound_service.InboundMessage(
                    external_message_id=external_id, external_chat_id="573001112233@s.whatsapp.net", sender_name="Spammer", text=text
                ),
                conversation_channel="whatsapp",
                channel_fk_field="whatsapp_channel_id",
            )
        )

    db = SessionLocal()
    try:
        channel = db.scalar(select(WhatsAppChannel))
        first = inbound(db, channel, "wa-1", "hola")
        assert first.reply == "Hi there"
        contact = client.get(f"/api/portal/{slug}/contacts").json()[0]
        assert contact["blocked_at"] is None

        # Block: stored, unanswered, out of every inbox, still readable from the contact.
        blocked = client.post(f"/api/portal/{slug}/contacts/{contact['id']}/block", json={"blocked": True}).json()
        assert blocked["blocked_at"]
        completion.reset_mock()
        second = inbound(db, channel, "wa-2", "spam spam")
        assert second.accepted and second.reply is None
        completion.assert_not_awaited()
        assert client.get(f"/api/portal/{slug}/conversations?status=open").json() == []
        assert client.get(f"/api/portal/{slug}/conversations/summary").json()["open"] == 0
        assert client.get("/api/conversations/inbox").json() == []
        history = client.get(f"/api/portal/{slug}/contacts/{contact['id']}/conversations").json()
        assert [row["id"] for row in history] == [str(first.conversation_id)]
        thread = client.get(f"/api/portal/{slug}/conversations/{first.conversation_id}").json()
        assert [m["content"] for m in thread["messages"] if m["kind"] == "message" and m["role"] == "user"] == ["hola", "spam spam"]

        # Unblock: the old case closes with a note, the backlog is not answered,
        # and the next message opens a fresh conversation the agent handles.
        unblocked = client.post(f"/api/portal/{slug}/contacts/{contact['id']}/block", json={"blocked": False}).json()
        assert unblocked["blocked_at"] is None
        completion.assert_not_awaited()
        closed = client.get(f"/api/portal/{slug}/conversations/{first.conversation_id}").json()
        assert closed["status"] == "resolved"
        assert [m["activity"]["event"] for m in closed["messages"] if m["kind"] == "activity"][-3:] == ["blocked", "resolved", "unblocked"]
        third = inbound(db, channel, "wa-3", "ahora si")
        assert third.reply == "Hi there" and third.conversation_id != first.conversation_id
        assert [row["id"] for row in client.get(f"/api/portal/{slug}/conversations?status=open").json()] == [str(third.conversation_id)]
    finally:
        db.close()
