"""Delayed sign-out only removes the registration owned by that session."""

import uuid

import pytest
from sqlalchemy import select

from app.models import PushDevice
from app.security import create_portal_token
from conftest import TestingSession
from test_mobile_and_push import _client_with_portal, _sign_in


@pytest.mark.parametrize("previous_identity,current_identity", [
    ("member", "member"), ("legacy", "member"), ("member", "legacy"),
])
def test_old_session_cannot_forget_reassigned_device(authenticated_client, previous_identity, current_identity):
    client = authenticated_client
    customer = _client_with_portal(client)
    previous = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "Next operator", "email": "next@barberco.com", "password": "next-operator-password"},
    )
    current = _sign_in(client, "next@barberco.com", "next-operator-password").json()
    legacy_token = create_portal_token(customer["id"], customer["portal_slug"])
    old_headers = {"Authorization": f"Bearer {previous['token'] if previous_identity == 'member' else legacy_token}"}
    new_headers = {"Authorization": f"Bearer {current['token'] if current_identity == 'member' else legacy_token}"}
    device_token = "shared-phone-registration"
    payload = {"token": device_token, "provider": "webhook", "platform": "ios"}
    assert client.post("/api/mobile/devices", headers=old_headers, json=payload).status_code == 200
    assert client.post("/api/mobile/devices", headers=new_headers, json=payload).status_code == 200

    # A late cleanup from the former session is an idempotent no-op.
    path = f"/api/mobile/devices/{device_token}"
    assert client.delete(path, headers=old_headers).status_code == 204
    with TestingSession() as db:
        device = db.scalar(select(PushDevice).where(PushDevice.token == device_token))
        assert device is not None
        assert device.portal_user_id == (uuid.UUID(current["user_id"]) if current_identity == "member" else None)

    assert client.delete(path, headers=new_headers).status_code == 204
    with TestingSession() as db:
        assert db.scalar(select(PushDevice).where(PushDevice.token == device_token)) is None
    assert client.delete(path, headers=new_headers).status_code == 204
