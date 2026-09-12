import asyncio
import hashlib
import json
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.models import SocialChannel, SocialOAuthState, User, now_utc
from app.security import decrypt_secret
from app.services import social_connections as service
from app.services import social_graph as graph
from app.services.social_graph import subscribe as subscribe_with_provider, verify_account as verify_provider_account
from conftest import TestingSession, login_legacy_owner


@pytest.fixture(autouse=True)
def messaging_config(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.test")
    monkeypatch.setattr(settings, "social_public_url", "https://app.example.test")
    monkeypatch.setattr(settings, "instagram_app_id", "999")
    monkeypatch.setattr(settings, "instagram_app_secret", "server-secret")
    monkeypatch.setattr(settings, "instagram_webhook_verify_token", "verify")
    monkeypatch.setattr(service, "_app_resolver", None)
    monkeypatch.setattr(service, "_connection_hooks", [])
    monkeypatch.setattr(service, "_state_hooks", [])
    monkeypatch.setattr(graph, "verify_account", AsyncMock(return_value={"id": "111", "name": "Shop", "username": "shop", "scopes": list(graph.SCOPES["instagram"])}))
    monkeypatch.setattr(graph, "subscribe", AsyncMock(return_value=True))
    monkeypatch.setattr(graph, "unsubscribe", AsyncMock())


def resources(client):
    customer = client.post("/api/clients", json={"name": "Shop", "is_active": True}).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post("/api/agents", json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Support", "instructions": "", "personality": "", "is_active": True}).json()
    return customer, agent


def manual(client, customer, agent, account_id="111"):
    return client.put(f"/api/social/instagram/channels/{customer['id']}", json={
        "agent_id": agent["id"], "external_account_id": account_id, "app_id": "999", "access_token": "private-token", "app_secret": "private-secret"})


def test_manual_draft_webhook_setup_then_connect_hides_credentials(authenticated_client):
    client = authenticated_client
    customer, agent = resources(client)
    response = manual(client, customer, agent)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "disconnected"
    assert data["has_access_token"] and data["has_app_secret"]
    assert "private-token" not in response.text and "private-secret" not in response.text
    assert f"/api/public/social/channels/{data['id']}/webhook" in data["webhook_url"]
    assert data["webhook_verify_token"]
    graph.subscribe.assert_not_awaited()
    connected = client.post(f"/api/social/instagram/channels/{customer['id']}/connect")
    assert connected.status_code == 200, connected.text
    assert connected.json()["status"] == "connected"
    graph.subscribe.assert_awaited_once()
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        assert channel.encrypted_access_token != "private-token"
        assert decrypt_secret(channel.encrypted_access_token) == "private-token"


def test_account_rebind_and_cross_client_assignment_are_rejected(authenticated_client):
    client = authenticated_client
    first, agent = resources(client)
    second, other_agent = resources(client)
    assert manual(client, first, agent).status_code == 200
    assert manual(client, first, agent, "222").status_code == 409
    assert manual(client, second, other_agent).status_code == 409
    assert manual(client, first, other_agent).status_code == 400


def test_disconnecting_releases_the_account_for_another_client(authenticated_client):
    client = authenticated_client
    first, agent = resources(client)
    second, other_agent = resources(client)
    assert manual(client, first, agent).status_code == 200
    assert manual(client, second, other_agent).status_code == 409
    assert client.post(f"/api/social/instagram/channels/{first['id']}/disconnect").status_code == 204
    assert client.get(f"/api/social/instagram/channels/{first['id']}").status_code == 404
    moved = manual(client, second, other_agent)
    assert moved.status_code == 200, moved.text
    # The account now belongs to the second client and nothing else holds it.
    assert manual(client, first, agent).status_code == 409
    with TestingSession() as db:
        rows = db.scalars(select(SocialChannel).where(SocialChannel.external_account_id == "111")).all()
        assert [str(row.client_id) for row in rows] == [second["id"]]


def test_another_agency_cannot_read_or_change_channel(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    login_legacy_owner(client)
    assert client.get(f"/api/social/instagram/channels/{customer['id']}").status_code == 404
    assert manual(client, customer, agent).status_code == 404


def test_failed_subscription_rolls_back_old_credentials_and_state(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    assert client.post(f"/api/social/instagram/channels/{customer['id']}/connect").status_code == 200
    monkeypatch.setattr(graph, "subscribe", AsyncMock(side_effect=HTTPException(502, "Subscription failed")))
    response = client.put(f"/api/social/instagram/channels/{customer['id']}", json={"agent_id": agent["id"], "external_account_id": "111", "access_token": "replacement"})
    assert response.status_code == 502
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        assert channel.status == "connected"
        assert decrypt_secret(channel.encrypted_access_token) == "private-token"


def test_oauth_state_single_use_pending_selection_and_no_tokens_in_redirect(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    monkeypatch.setattr(graph, "exchange_code", AsyncMock(return_value=[{"id": "111", "name": "Shop", "access_token": "oauth-private", "scopes": list(graph.SCOPES["instagram"]), "expires_at": (now_utc() + timedelta(days=60)).isoformat()}]))
    response = client.post("/api/social/instagram/oauth/start", json={"client_id": customer["id"], "agent_id": agent["id"]})
    assert response.status_code == 200, response.text
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    with TestingSession() as db:
        row = db.get(SocialOAuthState, hashlib.sha256(state.encode()).hexdigest())
        assert row and row.id != state
    callback = client.get("/api/social/oauth/callback/instagram", params={"state": state, "code": "code"}, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("?social_status=ready")
    assert "oauth-private" not in callback.headers["location"]
    assert client.get("/api/social/oauth/callback/instagram", params={"state": state, "code": "code"}).status_code == 400
    pending = client.get("/api/social/instagram/oauth/pending", params={"client_id": customer["id"]})
    assert pending.status_code == 200
    assert "oauth-private" not in pending.text
    setup = pending.json()["setup_id"]
    assert client.post("/api/social/instagram/oauth/complete", json={"setup_id": setup, "external_account_id": "222"}).status_code == 400
    complete = client.post("/api/social/instagram/oauth/complete", json={"setup_id": setup, "external_account_id": "111"})
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "connected"
    assert client.post("/api/social/instagram/oauth/complete", json={"setup_id": setup, "external_account_id": "111"}).status_code == 400
    with TestingSession() as db:
        assert "oauth-private" not in decrypt_secret(db.get(SocialOAuthState, setup).encrypted_payload)


@pytest.mark.parametrize("acknowledged", [True, False])
def test_instagram_oauth_persists_only_after_account_checks_and_subscription_acknowledgement(authenticated_client, monkeypatch, acknowledged):
    client = authenticated_client
    customer, agent = resources(client)
    monkeypatch.setattr(graph, "subscribe", subscribe_with_provider)
    monkeypatch.setattr(graph, "verify_account", verify_provider_account)
    monkeypatch.setattr(graph, "exchange_code", AsyncMock(return_value=[{
        "id": "111", "name": "Shop", "access_token": "oauth-private",
        "scopes": list(graph.SCOPES["instagram"]), "expires_at": (now_utc() + timedelta(days=60)).isoformat(),
    }]))
    request = AsyncMock(side_effect=[
        {"id": "222", "user_id": "111", "username": "shop"},
        {"data": []},
        {"data": [{"id": "888", "subscribed_fields": ["messages"]}]},
        {"success": acknowledged},
    ])
    monkeypatch.setattr(graph, "request", request)
    url = client.post("/api/social/instagram/oauth/start", json={"client_id": customer["id"], "agent_id": agent["id"]}).json()["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert client.get("/api/social/oauth/callback/instagram", params={"state": state, "code": "code"}, follow_redirects=False).status_code == 303
    setup = client.get("/api/social/instagram/oauth/pending", params={"client_id": customer["id"]}).json()["setup_id"]

    response = client.post("/api/social/instagram/oauth/complete", json={"setup_id": setup, "external_account_id": "111"})

    assert response.status_code == (200 if acknowledged else 502), response.text
    assert "oauth-private" not in response.text and "server-secret" not in response.text
    assert [(call.args[1], call.args[2]) for call in request.call_args_list] == [
        ("GET", "me"), ("GET", "111/conversations"),
        ("GET", "111/subscribed_apps"), ("POST", "111/subscribed_apps"),
    ]
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        payload = json.loads(decrypt_secret(db.get(SocialOAuthState, setup).encrypted_payload))
        if acknowledged:
            assert channel.status == "connected" and channel.is_enabled
            assert channel.app_id == "999" and channel.external_account_id == "111"
            assert str(channel.client_id) == customer["id"] and str(channel.agent_id) == agent["id"]
            assert decrypt_secret(channel.encrypted_access_token) == "oauth-private"
            assert payload == {"phase": "completed"}
        else:
            assert channel is None
            assert payload["phase"] == "pending"
    graph.unsubscribe.assert_not_awaited()


@pytest.mark.parametrize("before, should_unsubscribe", [
    ({"data": []}, True),
    ({"data": [{"id": "888"}]}, False),
    ({"data": [], "paging": {"next": "https://graph.instagram.com/next"}}, False),
])
def test_instagram_commit_failure_only_unsubscribes_a_proven_new_subscription(authenticated_client, monkeypatch, before, should_unsubscribe):
    customer, agent = resources(authenticated_client)
    monkeypatch.setattr(graph, "subscribe", subscribe_with_provider)
    monkeypatch.setattr(graph, "request", AsyncMock(side_effect=[before, {"success": True}]))
    with TestingSession() as db:
        user = db.scalar(select(User))
        monkeypatch.setattr(db, "commit", Mock(side_effect=RuntimeError("Test commit failure")))
        with pytest.raises(RuntimeError, match="Test commit failure"):
            asyncio.run(service.connect_account(db, user, customer["id"], agent["id"], "instagram",
                {"id": "111", "access_token": "private-token"}, service.get_app_config("instagram"), source="oauth"))
        assert db.scalar(select(SocialChannel)) is None
    assert graph.unsubscribe.await_count == int(should_unsubscribe)


def test_oauth_rejects_unsafe_return_path_and_expired_state(authenticated_client):
    client = authenticated_client
    customer, agent = resources(client)
    base = {"client_id": customer["id"], "agent_id": agent["id"]}
    assert client.post("/api/social/instagram/oauth/start", json={**base, "next_path": "//evil.test"}).status_code == 400
    url = client.post("/api/social/instagram/oauth/start", json=base).json()["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    with TestingSession() as db:
        row = db.get(SocialOAuthState, hashlib.sha256(state.encode()).hexdigest())
        row.expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/social/oauth/callback/instagram", params={"state": state, "code": "code"}).status_code == 400


def test_disconnect_removes_the_channel_even_after_remote_revocation(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    unlinked = []
    service.register_connection_hook(lambda db, channel, event: unlinked.append(event))
    monkeypatch.setattr(graph, "unsubscribe", AsyncMock(side_effect=HTTPException(401, "Revoked")))
    response = client.post(f"/api/social/instagram/channels/{customer['id']}/disconnect")
    assert response.status_code == 204
    assert unlinked == ["unlinked"]
    assert client.get(f"/api/social/instagram/channels/{customer['id']}").status_code == 404
    # The page starts over: a fresh manual setup is accepted for the same account.
    assert manual(client, customer, agent).status_code == 200


def test_refresh_throttles_failures_and_does_not_refresh_expired_tokens(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    assert client.post(f"/api/social/instagram/channels/{customer['id']}/connect").status_code == 200
    refresh = AsyncMock(side_effect=HTTPException(502, "Temporarily unavailable"))
    monkeypatch.setattr(graph, "refresh_instagram", refresh)
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel.token_expires_at = now_utc() + timedelta(days=2)
        channel.token_refreshed_at = now_utc() - timedelta(days=50)
        db.commit()
        asyncio.run(service.refresh_due_channels(db))
        asyncio.run(service.refresh_due_channels(db))
        assert refresh.await_count == 1
        channel.token_expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
        asyncio.run(service.refresh_due_channels(db))
        assert channel.status == "reauthorization_required"
        assert refresh.await_count == 1


def test_assignment_preserves_approved_human_agent_setting(authenticated_client):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel.human_agent_enabled = True
        db.commit()
    response = client.put(f"/api/social/instagram/channels/{customer['id']}", json={"agent_id": agent["id"], "external_account_id": "111"})
    assert response.status_code == 200
    assert response.json()["human_agent_enabled"] is True


def test_managed_capability_cannot_be_enabled_by_customer(authenticated_client, monkeypatch):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    config = service.SocialAppConfig(provider="instagram", app_id="999", app_secret="private-secret",
        source="managed", redirect_uri="https://app.example.test/api/social/oauth/callback/instagram",
        webhook_url="https://app.example.test/hook", verify_token="verify", human_agent_enabled=False)
    monkeypatch.setattr(service, "_app_resolver", lambda provider: config)
    response = client.put(f"/api/social/instagram/channels/{customer['id']}", json={"agent_id": agent["id"], "external_account_id": "111", "human_agent_enabled": True})
    assert response.status_code == 200
    assert response.json()["human_agent_enabled"] is False
    assert manual(client, customer, agent).status_code == 403


def test_refresh_scrubs_expired_pending_oauth_credentials(authenticated_client):
    client = authenticated_client
    customer, agent = resources(client)
    client.post("/api/social/instagram/oauth/start", json={"client_id": customer["id"], "agent_id": agent["id"]})
    with TestingSession() as db:
        state = db.scalar(select(SocialOAuthState))
        state.expires_at = now_utc() - timedelta(seconds=1)
        state_id = state.id
        db.commit()
        asyncio.run(service.refresh_due_channels(db))
        assert db.get(SocialOAuthState, state_id) is None


def test_assignment_does_not_postpone_token_refresh(authenticated_client):
    client = authenticated_client
    customer, agent = resources(client)
    assert manual(client, customer, agent).status_code == 200
    earlier = now_utc() - timedelta(days=40)
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel.connection_source = "oauth"
        channel.token_refreshed_at = earlier
        db.commit()
    response = client.put(f"/api/social/instagram/channels/{customer['id']}", json={"agent_id": agent["id"], "external_account_id": "111"})
    assert response.status_code == 200
    with TestingSession() as db:
        assert db.scalar(select(SocialChannel)).token_refreshed_at == earlier
