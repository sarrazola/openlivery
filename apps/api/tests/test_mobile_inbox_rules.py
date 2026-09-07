"""Bearer sessions and final-case rules hold even when a phone has stale state."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.security import create_portal_token
from conftest import customer_conversation
from test_mobile_and_push import _client_with_portal, _sign_in


def _session(client: TestClient):
    customer = _client_with_portal(client)
    session = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()
    return customer, session, {"Authorization": f"Bearer {session['token']}"}


def _assert_denied(client, slug, headers):
    assert client.get("/api/mobile/session", headers=headers).status_code == 401
    assert client.get(f"/api/portal/{slug}/conversations", headers=headers).status_code == 401
    assert client.post(
        "/api/mobile/devices", headers=headers,
        json={"token": "revoked-device-token", "platform": "ios"},
    ).status_code == 401
    assert client.patch(
        f"/api/portal/{slug}/me", headers=headers, json={"availability": "away"},
    ).status_code == 401


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_revoked_member_loses_existing_bearer_session(authenticated_client, action):
    client = authenticated_client
    customer, session, headers = _session(client)
    path = f"/api/clients/{customer['id']}/portal-users/{session['user_id']}"
    if action == "disable":
        assert client.patch(path, json={"is_active": False}).status_code == 200
    else:
        assert client.delete(path).status_code == 204
    _assert_denied(client, customer["portal_slug"], headers)


@pytest.mark.parametrize("identity", ["missing", "malformed", "foreign"])
def test_named_session_cannot_fall_back_to_legacy_identity(authenticated_client, identity):
    client = authenticated_client
    customer, session, _ = _session(client)
    user_id = str(uuid.uuid4()) if identity == "missing" else "not-a-uuid"
    if identity == "foreign":
        other = client.post("/api/clients", json={"name": "Other client"}).json()
        user_id = client.post(
            f"/api/clients/{other['id']}/portal-users",
            json={"name": "Other operator", "email": "operator@example.com", "password": "other-password"},
        ).json()["id"]
    token = create_portal_token(customer["id"], customer["portal_slug"], user_id)
    _assert_denied(client, customer["portal_slug"], {"Authorization": f"Bearer {token}"})


def test_legacy_unnamed_session_still_reads(authenticated_client):
    client = authenticated_client
    customer, _, _ = _session(client)
    token = create_portal_token(customer["id"], customer["portal_slug"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/mobile/session", headers=headers).status_code == 200
    assert client.get(f"/api/portal/{customer['portal_slug']}/conversations", headers=headers).status_code == 200


def test_resolved_case_rejects_every_outbound_action_before_delivery(authenticated_client, monkeypatch):
    from app.routers import portal

    client = authenticated_client
    customer, _, headers = _session(client)
    agent = client.post(
        "/api/agents", json={"client_id": customer["id"], "name": "Assistant"},
    ).json()
    conversation = customer_conversation(client, agent["id"])
    path = f"/api/portal/{customer['portal_slug']}/conversations/{conversation['id']}"
    assert client.patch(f"{path}/mode", headers=headers, json={"mode": "human"}).status_code == 200
    resolved = client.patch(f"{path}/status", headers=headers, json={"status": "resolved"})
    assert resolved.status_code == 200
    message_count = len(resolved.json()["messages"])
    deliver = AsyncMock()
    for method in ["send_channel_message", "store_operator_media_reply", "_send_template_to", "deliver_reaction"]:
        monkeypatch.setattr(portal, method, deliver)

    responses = [
        client.post(f"{path}/reply", headers=headers, json={"content": "Stale composer"}),
        client.post(f"{path}/reply-media", headers=headers, files={"file": ("photo.png", b"image", "image/png")}),
        client.post(f"{path}/reply-template", headers=headers, json={"name": "hello", "language": "en", "variables": []}),
        client.post(f"{path}/messages/{uuid.uuid4()}/reaction", headers=headers, json={"emoji": "👍"}),
    ]
    assert [response.status_code for response in responses] == [409, 409, 409, 409]
    assert all("resolved" in response.json()["detail"] for response in responses)
    deliver.assert_not_called()
    assert len(client.get(path, headers=headers).json()["messages"]) == message_count
