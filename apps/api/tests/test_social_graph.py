import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import HTTPException

from app.security import encrypt_secret
from app.services import social_graph as graph


def channel(provider="instagram"):
    return SimpleNamespace(provider=provider, external_account_id="123", status="connected", is_enabled=True,
        encrypted_access_token=encrypt_secret("private-token"), human_agent_enabled=True)


def test_graph_host_and_object_paths_are_not_caller_controlled():
    assert graph.graph_url("instagram", "123/messages").startswith("https://graph.instagram.com/")
    assert graph.graph_url("messenger", "123/messages").startswith("https://graph.facebook.com/")
    for path in ("https://evil.test", "../me", "/me", "me?access_token=bad"):
        with pytest.raises(HTTPException):
            graph.graph_url("instagram", path)
    for identifier in ("../123", "123?x=1", "username"):
        with pytest.raises(HTTPException):
            graph.object_id(identifier)


def test_instagram_text_limit_counts_utf8_bytes_and_never_truncates(monkeypatch):
    request = AsyncMock(return_value={"message_id": "mid.1"})
    monkeypatch.setattr(graph, "request", request)
    assert asyncio.run(graph.send_text(channel(), "456", "😀" * 250)) == "mid.1"
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.send_text(channel(), "456", "😀" * 251))
    assert error.value.status_code == 400
    assert request.await_count == 1
    assert request.call_args.kwargs["json"]["message"]["text"] == "😀" * 250


def test_human_agent_tag_requires_explicit_enabled_connection(monkeypatch):
    request = AsyncMock(return_value={"message_id": "mid.1"})
    monkeypatch.setattr(graph, "request", request)
    instance = channel("messenger")
    asyncio.run(graph.send_text(instance, "456", "Hello", human_agent=True))
    assert request.call_args.kwargs["json"]["tag"] == "HUMAN_AGENT"
    instance.human_agent_enabled = False
    with pytest.raises(HTTPException):
        asyncio.run(graph.send_text(instance, "456", "Hello", human_agent=True))


def test_manual_token_identity_is_verified_before_subscription(monkeypatch):
    request = AsyncMock(return_value={"id": "111", "user_id": "111", "username": "other"})
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.verify_account("instagram", "token", "222", "999", "secret"))
    assert error.value.status_code == 400
    assert request.await_count == 1


def test_instagram_subscription_accepts_acknowledgement_with_different_graph_object_id(monkeypatch):
    request = AsyncMock(side_effect=[
        {"data": []}, {"success": True},
        {"data": [{"id": "888", "subscribed_fields": sorted(graph.SUBSCRIPTIONS["instagram"])}]},
        {"success": True},
    ])
    monkeypatch.setattr(graph, "request", request)

    assert asyncio.run(graph.subscribe("instagram", "token", "111", "999", "secret")) is True
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST"]


def test_messenger_requires_matching_app_and_fields_and_cleans_failed_new_subscription(monkeypatch):
    request = AsyncMock(side_effect=[{"data": []}, {"success": True}, {"data": [{"id": "different"}]}, {"success": True}])
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException):
        asyncio.run(graph.subscribe("messenger", "token", "111", "999", "secret"))
    assert request.call_args_list[-1].args[1] == "DELETE"


@pytest.mark.parametrize("provider, expected_fields", [
    ("instagram", {"messages", "messaging_postbacks", "messaging_seen", "message_reactions",
                   "messaging_referral", "messaging_handover", "standby"}),
    ("messenger", {"messages", "messaging_postbacks", "message_deliveries", "message_reads",
                   "messaging_referrals", "message_echoes", "messaging_handovers", "standby"}),
])
def test_subscription_uses_provider_field_names_and_accepts_confirmed_readback(monkeypatch, provider, expected_fields):
    request = AsyncMock(side_effect=[
        {"data": []},
        {"success": True},
        {"data": [{"id": "999", "subscribed_fields": sorted(expected_fields)}]},
        {"success": True},
    ])
    monkeypatch.setattr(graph, "request", request)

    assert asyncio.run(graph.subscribe(provider, "token", "111", "999", "secret")) is True

    subscription = request.call_args_list[1]
    assert subscription.args == (provider, "POST", "111/subscribed_apps", "token")
    assert set(subscription.kwargs["data"]["subscribed_fields"].split(",")) == expected_fields
    assert subscription.kwargs["data"]["appsecret_proof"] == graph._proof("token", "secret")
    assert request.await_count == (2 if provider == "instagram" else 3)


@pytest.mark.parametrize("identity", [
    {}, {"id": ""}, {"app_id": "999"}, {"id": "123"},
    {"id": "999", "app_id": "123"}, {"id": "123", "app_id": "999"},
])
def test_messenger_rejects_missing_foreign_and_conflicting_app_ids(monkeypatch, identity):
    fields = ["messages", "messaging_postbacks", "messaging_seen", "message_reactions",
              "messaging_referral", "messaging_handover", "standby", "message_deliveries",
              "message_reads", "messaging_referrals", "message_echoes", "messaging_handovers"]
    request = AsyncMock(side_effect=[
        {"data": []}, {"success": True},
        {"data": [{**identity, "subscribed_fields": fields}]}, {"success": True},
    ])
    monkeypatch.setattr(graph, "request", request)

    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.subscribe("messenger", "token", "111", "999", "secret"))

    assert error.value.status_code == 502
    assert request.call_args_list[-1].args[1] == "DELETE"


@pytest.mark.parametrize("result", [{}, {"success": False}, {"success": None}, {"success": "true"}, {"success": 1}])
def test_instagram_requires_explicit_boolean_acknowledgement(monkeypatch, result):
    request = AsyncMock(side_effect=[
        {"data": [{"id": "888", "subscribed_fields": ["messages"]}]}, result,
    ])
    monkeypatch.setattr(graph, "request", request)

    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.subscribe("instagram", "token", "111", "999", "secret"))

    assert error.value.status_code == 502
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST"]


@pytest.mark.parametrize("before", [
    {"data": [{"id": "888", "subscribed_fields": ["comments"]}]},
    {"data": [{"app_id": "999", "subscribed_fields": ["comments"]}]},
    {"data": [{"id": "888"}, {"id": "777"}]},
    {"data": [], "paging": {"next": "https://graph.instagram.com/next"}},
])
def test_instagram_existing_or_paginated_subscriptions_are_never_treated_as_new(monkeypatch, before):
    request = AsyncMock(side_effect=[
        before, {"success": True},
    ])
    monkeypatch.setattr(graph, "request", request)

    assert asyncio.run(graph.subscribe("instagram", "token", "111", "999", "secret")) is False

    assert set(request.call_args_list[1].kwargs["data"]["subscribed_fields"].split(",")) == graph.SUBSCRIPTIONS["instagram"]
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST"]


@pytest.mark.parametrize("before", [{}, {"data": None}, {"data": {}}, {"data": [None]}])
def test_instagram_malformed_preflight_fails_before_changing_subscription(monkeypatch, before):
    request = AsyncMock(return_value=before)
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.subscribe("instagram", "token", "111", "999", "secret"))
    assert error.value.status_code == 502
    assert [call.args[1] for call in request.call_args_list] == ["GET"]


@pytest.mark.parametrize("status", [401, 403, 429, 502])
def test_instagram_rejected_post_does_not_delete_a_previous_subscription(monkeypatch, status):
    request = AsyncMock(side_effect=[{"data": [{"id": "888"}]}, HTTPException(status, "Provider rejected request")])
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.subscribe("instagram", "token", "111", "999", "secret"))
    assert error.value.status_code == status
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST"]


def test_messenger_reconnection_preserves_existing_fields(monkeypatch):
    fields = graph.SUBSCRIPTIONS["messenger"] | {"feed"}
    request = AsyncMock(side_effect=[
        {"data": [{"id": "999", "subscribed_fields": ["feed"]}]}, {"success": True},
        {"data": [{"id": "999", "subscribed_fields": sorted(fields)}]},
    ])
    monkeypatch.setattr(graph, "request", request)
    assert asyncio.run(graph.subscribe("messenger", "token", "111", "999", "secret")) is False
    assert set(request.call_args_list[1].kwargs["data"]["subscribed_fields"].split(",")) == fields


def test_messenger_existing_subscription_is_preserved_when_readback_loses_a_required_field(monkeypatch):
    fields = sorted(graph.SUBSCRIPTIONS["messenger"])
    request = AsyncMock(side_effect=[
        {"data": [{"id": "999", "subscribed_fields": fields}]}, {"success": True},
        {"data": [{"id": "999", "subscribed_fields": fields[:-1]}]},
    ])
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.subscribe("messenger", "token", "111", "999", "secret"))
    assert error.value.status_code == 502
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST", "GET"]


def test_subscription_diagnostics_include_only_safe_identity_and_field_metadata(monkeypatch, caplog):
    response = {"data": [{"app_id": "123", "id": "private-id-value", "access_token": "private-token",
                          "subscribed_fields": ["messages", "private-value=https://private.example"]}],
                "paging": {"next": "https://private.example/?access_token=private-token"}}
    request = AsyncMock(side_effect=[{"data": []}, {"success": True}, response, {"success": True}])
    monkeypatch.setattr(graph, "request", request)

    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException):
        asyncio.run(graph.subscribe("messenger", "private-token", "111", "999", "private-secret"))

    assert "subscription readback" in caplog.text
    assert "999" in caplog.text and "123" in caplog.text and "messages" in caplog.text
    assert "app_id" in caplog.text
    assert "private" not in caplog.text
    assert "https://" not in caplog.text


def test_instagram_code_exchange_keeps_scopes_and_long_lived_expiry(monkeypatch):
    http = AsyncMock(side_effect=[{"data": [{"access_token": "short", "user_id": "111", "permissions": ",".join(graph.SCOPES["instagram"])}]},
                                 {"access_token": "long", "expires_in": 5184000}])
    monkeypatch.setattr(graph, "_http", http)
    monkeypatch.setattr(graph, "request", AsyncMock(return_value={"id": "scoped", "user_id": "111", "username": "shop"}))
    config = SimpleNamespace(app_id="999", app_secret="secret", redirect_uri="https://app.test/callback")
    accounts = asyncio.run(graph.exchange_code("instagram", "code", config))
    assert accounts[0]["id"] == "111"
    assert accounts[0]["access_token"] == "long"
    assert accounts[0]["expires_at"]
    assert http.call_args_list[0].args[1] == "https://api.instagram.com/oauth/access_token"


def test_missing_oauth_permissions_fail_before_long_token_exchange(monkeypatch):
    http = AsyncMock(return_value={"access_token": "short", "permissions": "instagram_business_basic"})
    monkeypatch.setattr(graph, "_http", http)
    config = SimpleNamespace(app_id="999", app_secret="secret", redirect_uri="https://app.test/callback")
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.exchange_code("instagram", "code", config))
    assert error.value.status_code == 403
    assert http.await_count == 1


def test_httpx_token_request_urls_are_redacted():
    record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request %s", (httpx.URL("https://graph.instagram.com/access_token?client_secret=secret&access_token=token&fb_exchange_token=another"),), None)
    graph._RedactTokenURLs().filter(record)
    output = record.getMessage()
    assert "=secret" not in output and "=token" not in output and "=another" not in output
    assert "[redacted]" in output


def test_provider_errors_do_not_expose_upstream_text(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def request(self, *args, **kwargs):
            return httpx.Response(400, json={"error": {"code": 190, "message": "token=private-secret"}})
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.request("instagram", "GET", "me", "secret"))
    assert error.value.status_code == 401
    assert "private-secret" not in str(error.value.detail)


def test_messenger_page_selection_checks_tasks_and_uses_only_safe_pagination(monkeypatch):
    monkeypatch.setattr(graph, "_http", AsyncMock(side_effect=[{"access_token": "short-user"}, {"access_token": "long-user"}]))
    request = AsyncMock(side_effect=[
        {"data": [{"permission": scope, "status": "granted"} for scope in graph.SCOPES["messenger"]]},
        {"data": [{"id": "111", "name": "Allowed", "access_token": "page-one", "tasks": ["MESSAGING", "MODERATE"]},
                   {"id": "222", "name": "Insufficient", "access_token": "page-two", "tasks": ["MESSAGING"]}],
         "paging": {"next": "http://127.0.0.1/secrets", "cursors": {"after": "safe-cursor"}}},
        {"data": [{"id": "333", "name": "Another", "access_token": "page-three", "tasks": ["MESSAGING", "MODERATE"]}]},
    ])
    monkeypatch.setattr(graph, "request", request)
    config = SimpleNamespace(app_id="999", app_secret="secret", redirect_uri="https://app.test/callback")
    accounts = asyncio.run(graph.exchange_code("messenger", "code", config))
    assert [account["id"] for account in accounts] == ["111", "333"]
    assert request.call_args_list[-1].args[2] == "me/accounts"
    assert request.call_args_list[-1].kwargs["params"]["after"] == "safe-cursor"
    assert "127.0.0.1" not in str(request.call_args_list)


def test_messenger_rejects_token_from_another_app(monkeypatch):
    request = AsyncMock(side_effect=[{"id": "111", "name": "Shop"},
        {"data": {"is_valid": True, "app_id": "12345", "type": "PAGE", "scopes": ["pages_messaging", "pages_manage_metadata"]}}])
    monkeypatch.setattr(graph, "request", request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.verify_account("messenger", "page-token", "111", "999", "secret"))
    assert error.value.status_code == 400
    assert request.await_count == 2


def test_managed_human_agent_revocation_is_enforced_at_delivery(monkeypatch):
    from app.services import social_connections
    request = AsyncMock(return_value={"message_id": "mid.1"})
    monkeypatch.setattr(graph, "request", request)
    monkeypatch.setattr(social_connections, "get_app_config", lambda provider: SimpleNamespace(human_agent_enabled=False))
    instance = channel()
    instance.connection_source = "managed"
    with pytest.raises(HTTPException) as error:
        asyncio.run(graph.send_text(instance, "456", "Support", human_agent=True))
    assert error.value.status_code == 409
    request.assert_not_awaited()


def test_outgoing_request_includes_appsecret_proof(monkeypatch):
    request = AsyncMock(return_value={"message_id": "mid.1"})
    monkeypatch.setattr(graph, "request", request)
    instance = channel()
    instance.encrypted_app_secret = encrypt_secret("app-secret")
    asyncio.run(graph.send_text(instance, "456", "Hello"))
    assert request.call_args.kwargs["json"]["appsecret_proof"] == graph._proof("private-token", "app-secret")
    assert "app-secret" not in str(request.call_args)


def test_opaque_message_identifiers_are_bounded_without_losing_base64_symbols():
    identifier = "a" * 1019 + ".+=/="
    assert len(identifier) == 1024
    encoded = graph.path_component(identifier)
    assert encoded.endswith("%2E%2B%3D%2F%3D")
    assert graph._message_id({"message_id": identifier}) == identifier
    assert urlsplit(graph.graph_url("instagram", encoded)).hostname == "graph.instagram.com"
    for invalid in ("a" * 1025, "a\n", "😀"):
        with pytest.raises(HTTPException):
            graph.path_component(invalid)
        with pytest.raises(HTTPException):
            graph._message_id({"message_id": invalid})
