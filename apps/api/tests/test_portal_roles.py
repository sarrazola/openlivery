"""Portal roles: what an admin and an agent may do, and where the role is set.

The API guards routes by permission key (app.portal_permissions), never by
role name; these tests exercise the presets through the routes.
"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.portal_permissions import PERMISSIONS
from app.routers import portal as portal_router
from conftest import customer_conversation


def _business(client: TestClient, name: str = "Roles Co") -> dict:
    return client.post("/api/clients", json={"name": name, "is_active": True}).json()


def _open_portal(client: TestClient, customer: dict) -> None:
    # A portal opens only once someone can sign in to it.
    assert client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True}).status_code == 200


def _person(client: TestClient, customer: dict, email: str, role: str | None = None) -> dict:
    payload = {"name": email.split("@")[0].title(), "email": email, "password": "secure-portal"}
    if role:
        payload["role"] = role
    created = client.post(f"/api/clients/{customer['id']}/portal-users", json=payload)
    assert created.status_code == 201, created.text
    return created.json()


def _sign_in(client: TestClient, customer: dict, email: str) -> dict:
    response = client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": email, "password": "secure-portal"})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_first_person_is_the_admin_and_the_next_ones_are_agents(authenticated_client: TestClient):
    client = authenticated_client
    customer = _business(client)
    owner = _person(client, customer, "owner@roles.co")
    helper = _person(client, customer, "helper@roles.co")
    named = _person(client, customer, "named@roles.co", role="admin")
    assert (owner["role"], helper["role"], named["role"]) == ("admin", "agent", "admin")

    listed = {row["email"]: row["role"] for row in client.get(f"/api/clients/{customer['id']}/portal-users").json()}
    assert listed == {"owner@roles.co": "admin", "helper@roles.co": "agent", "named@roles.co": "admin"}

    # The agency changes a role like any other field; unknown roles are refused.
    changed = client.patch(f"/api/clients/{customer['id']}/portal-users/{helper['id']}", json={"role": "admin"})
    assert changed.status_code == 200 and changed.json()["role"] == "admin"
    assert client.patch(f"/api/clients/{customer['id']}/portal-users/{helper['id']}", json={"role": "owner"}).status_code == 422


def test_the_session_says_what_the_person_may_do(authenticated_client: TestClient):
    client = authenticated_client
    customer = _business(client)
    _person(client, customer, "owner@roles.co")
    _person(client, customer, "helper@roles.co")
    _open_portal(client, customer)
    slug = customer["portal_slug"]

    session = _sign_in(client, customer, "owner@roles.co")
    assert session["role"] == "admin" and session["permissions"] == sorted(PERMISSIONS)
    me = client.get(f"/api/portal/{slug}/me").json()
    assert me["role"] == "admin" and me["permissions"] == sorted(PERMISSIONS)

    session = _sign_in(client, customer, "helper@roles.co")
    assert session["role"] == "agent" and session["permissions"] == []

    # The mobile app gets the same answer.
    mobile = client.post("/api/mobile/sign-in", json={"email": "helper@roles.co", "password": "secure-portal"})
    assert mobile.status_code == 200, mobile.text
    assert mobile.json()["role"] == "agent" and mobile.json()["permissions"] == []


def test_an_agent_works_the_inbox_but_manages_nothing(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _business(client)
    admin = _person(client, customer, "owner@roles.co")
    _person(client, customer, "helper@roles.co")
    _open_portal(client, customer)
    slug = customer["portal_slug"]
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Beto", "is_active": True},
    ).json()
    conversation_id = customer_conversation(client, agent["id"])["id"]

    # The admin sets the stage: a team, a tag, a saved reply.
    _sign_in(client, customer, "owner@roles.co")
    team = client.post(f"/api/portal/{slug}/teams", json={"name": "Ventas", "member_ids": [admin["id"]]}).json()
    tag = client.post(f"/api/portal/{slug}/tags", json={"name": "VIP"}).json()
    assert client.post(f"/api/portal/{slug}/canned-responses", json={"shortcut": "hola", "content": "Hola!"}).status_code == 201

    _sign_in(client, customer, "helper@roles.co")
    base = f"/api/portal/{slug}"
    forbidden = {"detail": "Your role cannot do this"}

    # Working the inbox is free.
    assert client.get(f"{base}/conversations").status_code == 200
    assert client.patch(f"{base}/conversations/{conversation_id}/mode", json={"mode": "human"}).status_code == 200
    assert client.post(f"{base}/conversations/{conversation_id}/reply", json={"content": "Con gusto"}).status_code == 200
    assert client.patch(f"{base}/conversations/{conversation_id}/team", json={"team_id": team["id"]}).status_code == 200
    assert client.post(f"{base}/conversations/{conversation_id}/assignment", json={"assignee_id": admin["id"]}).status_code == 200
    assert client.patch(f"{base}/conversations/{conversation_id}/status", json={"status": "resolved"}).status_code == 200
    contact = client.post(f"{base}/contacts", json={"name": "Rita", "phone": "573001112233"})
    assert contact.status_code == 201, contact.text
    assert client.put(f"{base}/contacts/{contact.json()['id']}/tags", json={"tag_ids": [tag["id"]]}).status_code == 200
    assert client.get(f"{base}/teams").status_code == 200
    assert client.get(f"{base}/canned-responses").status_code == 200
    assert client.patch(f"{base}/me", json={"availability": "away"}).status_code == 200

    # Managing is not.
    assert client.patch(f"{base}/conversations/{conversation_id}/archive", json={"archived": True}).json() == forbidden
    assert client.delete(f"{base}/conversations/{conversation_id}").status_code == 403
    assert client.post(f"{base}/conversations/archive-resolved").status_code == 403
    assert client.post(f"{base}/conversations/delete-archived").status_code == 403
    assert client.get(f"{base}/contacts/export").status_code == 403
    assert client.get(f"{base}/contacts/import-template").status_code == 403
    assert client.post(f"{base}/contacts/import", files={"file": ("c.csv", b"name,phone\n", "text/csv")}).status_code == 403
    assert client.delete(f"{base}/contacts/{contact.json()['id']}").status_code == 403
    assert client.post(f"{base}/contacts/{contact.json()['id']}/block", json={"blocked": True}).status_code == 403
    assert client.post(f"{base}/contacts/{contact.json()['id']}/merge", json={"primary_id": contact.json()["id"]}).status_code == 403
    assert client.post(f"{base}/tags", json={"name": "Nuevo"}).status_code == 403
    assert client.patch(f"{base}/tags/{tag['id']}", json={"name": "Otro"}).status_code == 403
    assert client.delete(f"{base}/tags/{tag['id']}").status_code == 403
    assert client.post(f"{base}/teams", json={"name": "Soporte", "member_ids": []}).status_code == 403
    assert client.patch(f"{base}/teams/{team['id']}", json={"name": "Ventas", "member_ids": []}).status_code == 403
    assert client.delete(f"{base}/teams/{team['id']}").status_code == 403
    assert client.post(f"{base}/canned-responses", json={"shortcut": "adios", "content": "Adios"}).status_code == 403
    assert client.get(f"{base}/reports").status_code == 403
    monkeypatch.setattr(portal_router, "create_template", AsyncMock())
    monkeypatch.setattr(portal_router, "delete_template", AsyncMock())
    assert client.post(f"{base}/templates", json={"name": "promo", "body": "Hola"}).status_code == 403
    assert client.delete(f"{base}/templates/promo").status_code == 403

    # Nothing the agent tried to manage happened.
    _sign_in(client, customer, "owner@roles.co")
    assert [row["name"] for row in client.get(f"{base}/teams").json()] == ["Ventas"]
    assert [row["name"] for row in client.get(f"{base}/tags").json()] == ["VIP"]
    assert client.get(f"{base}/conversations/{conversation_id}").json()["archived_at"] is None


def test_a_session_with_nobody_behind_it_reads_but_never_manages(authenticated_client: TestClient):
    from app.security import create_portal_token

    client = authenticated_client
    customer = _business(client)
    _person(client, customer, "owner@roles.co")
    _open_portal(client, customer)
    headers = {"Authorization": f"Bearer {create_portal_token(customer['id'], customer['portal_slug'])}"}
    slug = customer["portal_slug"]
    assert client.get(f"/api/portal/{slug}/teams", headers=headers).status_code == 200
    assert client.post(f"/api/portal/{slug}/teams", headers=headers, json={"name": "X", "member_ids": []}).status_code == 403
    me = client.get(f"/api/portal/{slug}/me", headers=headers).json()
    assert me["role"] is None and me["permissions"] == []
