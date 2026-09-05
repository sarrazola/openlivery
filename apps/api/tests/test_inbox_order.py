import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from conftest import customer_conversation

from app.database import SessionLocal
from app.models import Message, now_utc


def _portal(client: TestClient):
    customer = client.post(
        "/api/clients",
        json={"name": "Order Co", "is_active": True},
    ).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@order.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@order.co", "password": "secure-portal"})
    first = customer_conversation(client, agent["id"])["id"]
    second = customer_conversation(client, agent["id"])["id"]
    return customer["portal_slug"], first, second


def _visitor_wrote(conversation_id: str, minutes_ago: int) -> None:
    with SessionLocal() as db:
        db.add(
            Message(
                conversation_id=uuid.UUID(conversation_id),
                role="user",
                content="hola",
                sender_type="visitor",
                created_at=now_utc() - timedelta(minutes=minutes_ago),
            )
        )
        db.commit()


def test_only_a_new_visitor_message_moves_a_conversation_up(authenticated_client: TestClient):
    client = authenticated_client
    slug, first, second = _portal(client)
    base = f"/api/portal/{slug}/conversations"

    def portal_order():
        return [row["id"] for row in client.get(f"{base}?status=open").json()]

    def agency_order():
        plain = [row["id"] for row in client.get("/api/conversations").json() if row["id"] in (first, second)]
        inbox = [row["id"] for row in client.get("/api/conversations/inbox").json() if row["id"] in (first, second)]
        assert plain == inbox
        return inbox

    _visitor_wrote(first, minutes_ago=10)
    _visitor_wrote(second, minutes_ago=5)
    assert portal_order() == [second, first]
    assert agency_order() == [second, first]

    # Opening the older one marks it read: it stays where it was.
    assert client.post(f"{base}/{first}/read").status_code == 204
    assert client.post(f"/api/conversations/{first}/read").status_code in (200, 204)
    assert portal_order() == [second, first]
    assert agency_order() == [second, first]

    # Working it (taking over, replying, resolving) does not move it either.
    client.patch(f"{base}/{first}/mode", json={"mode": "human"})
    client.post(f"{base}/{first}/reply", json={"content": "On it"})
    assert portal_order() == [second, first]
    assert agency_order() == [second, first]

    # The contact writing again is what brings it to the top.
    _visitor_wrote(first, minutes_ago=1)
    assert portal_order() == [first, second]
    assert agency_order() == [first, second]


def test_a_conversation_without_inbound_sorts_by_creation(authenticated_client: TestClient):
    client = authenticated_client
    slug, first, second = _portal(client)
    base = f"/api/portal/{slug}/conversations"
    # Nobody wrote yet: newest created first, and reading does not reorder.
    assert [row["id"] for row in client.get(f"{base}?status=open").json()] == [second, first]
    client.post(f"{base}/{first}/read")
    assert [row["id"] for row in client.get(f"{base}?status=open").json()] == [second, first]
