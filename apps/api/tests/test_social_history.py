import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

from fastapi import HTTPException
from sqlalchemy import select

from app.models import SocialChannel, SocialHistoryImport, SocialWebhookEvent, now_utc
from app.services import social_graph as graph
from app.services import social_history as history
from conftest import TestingSession, login_legacy_owner


def setup(client, monkeypatch):
    monkeypatch.setattr(graph, "verify_account", AsyncMock(return_value={"id": "111", "name": "Shop", "scopes": list(graph.SCOPES["instagram"])}))
    monkeypatch.setattr(graph, "subscribe", AsyncMock(return_value=True))
    customer = client.post("/api/clients", json={"name": "Shop", "is_active": True}).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post("/api/agents", json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Support", "instructions": "", "personality": "", "is_active": True}).json()
    response = client.put(f"/api/social/instagram/channels/{customer['id']}", json={"agent_id": agent["id"], "external_account_id": "111", "app_id": "999", "access_token": "private-token", "app_secret": "secret"})
    assert response.status_code == 200
    assert client.post(f"/api/social/instagram/channels/{customer['id']}/connect").status_code == 200
    return f"/api/social/instagram/channels/{customer['id']}/import-history"


def test_history_is_authenticated_and_repeated_requests_reuse_active_job(authenticated_client, monkeypatch):
    client = authenticated_client
    endpoint = setup(client, monkeypatch)
    first = client.post(endpoint)
    assert first.status_code == 202, first.text
    assert first.json()["max_conversations"] == 20
    assert first.json()["limited"] is True
    assert client.post(endpoint).json()["id"] == first.json()["id"]
    login_legacy_owner(client)
    assert client.get(endpoint).status_code == 404
    assert client.post(endpoint).status_code == 404


def test_history_uses_cutoff_ascending_order_and_opaque_ids(authenticated_client, monkeypatch):
    client = authenticated_client
    endpoint = setup(client, monkeypatch)
    client.post(endpoint)
    old = now_utc() - timedelta(days=3)
    recent = now_utc() - timedelta(days=1)
    future = now_utc() + timedelta(minutes=1)
    request = AsyncMock(side_effect=[
        {"data": [{"id": "thread=a/b+1"}], "paging": {"next": "http://127.0.0.1/private", "cursors": {"after": "cursor-2"}}},
        {"messages": {"data": [{"id": "message=recent"}, {"id": "message/old+"}, {"id": "message-future"}]}},
        {"id": "message=recent", "created_time": recent.isoformat(), "from": {"id": "111"}, "to": {"data": [{"id": "222"}]}, "message": "Reply"},
        {"id": "message/old+", "created_time": old.isoformat(), "from": {"id": "222"}, "to": {"data": [{"id": "111"}]}, "message": "Earlier"},
        {"id": "message-future", "created_time": future.isoformat(), "from": {"id": "222"}, "to": {"data": [{"id": "111"}]}, "message": "Live"},
    ])
    monkeypatch.setattr(graph, "request", request)
    with TestingSession() as db:
        assert asyncio.run(history.process_history_jobs(db)) == 1
        job = db.scalar(select(SocialHistoryImport))
        assert job.status == "pending" and job.cursor == "cursor-2"
        assert job.messages_count == 2 and job.conversations_count == 1
        events = db.scalars(select(SocialWebhookEvent).order_by(SocialWebhookEvent.created_at)).all()
        assert [event.payload["message"]["text"] for event in events] == ["Earlier", "Reply"]
        assert all(event.payload["_historical"] for event in events)
    assert request.call_args_list[1].args[2] == "thread%3Da%2Fb%2B1"
    assert request.call_args_list[3].args[2] == "message%2Fold%2B"
    assert "127.0.0.1" not in str(request.call_args_list)


def test_history_limit_checkpoint_and_next_batch_continuation(authenticated_client, monkeypatch):
    client = authenticated_client
    endpoint = setup(client, monkeypatch)
    first = client.post(endpoint).json()
    request = AsyncMock(side_effect=[{"data": [{"id": "thread"}], "paging": {"next": "https://graph.instagram.com/more", "cursors": {"after": "next-page"}}}, {"messages": {"data": []}}])
    monkeypatch.setattr(graph, "request", request)
    with TestingSession() as db:
        job = db.scalar(select(SocialHistoryImport))
        job.conversations_count = 19
        db.commit()
        asyncio.run(history.process_history_jobs(db))
        assert job.status == "completed"
        assert job.conversations_count == 20
        cutoff = job.cutoff_at
    assert client.get(endpoint).json()["has_more"] is True
    second = client.post(endpoint)
    assert second.status_code == 202
    assert second.json()["id"] != first["id"]
    with TestingSession() as db:
        latest = db.scalar(select(SocialHistoryImport).order_by(SocialHistoryImport.created_at.desc()))
        assert latest.cursor == "next-page" and latest.cutoff_at == cutoff


def test_history_bounds_messages_and_does_not_hide_network_failures(authenticated_client, monkeypatch):
    client = authenticated_client
    endpoint = setup(client, monkeypatch)
    client.post(endpoint)
    messages = [{"id": f"message-{index}"} for index in range(50)]
    calls = []
    async def request(provider, method, path, token, **kwargs):
        calls.append(path)
        if path.endswith("/conversations"):
            return {"data": [{"id": "thread"}]}
        if path == "thread":
            return {"messages": {"data": messages}}
        raise HTTPException(502, "The messaging provider could not be reached")
    monkeypatch.setattr(graph, "request", request)
    with TestingSession() as db:
        asyncio.run(history.process_history_jobs(db))
        job = db.scalar(select(SocialHistoryImport))
        assert job.status == "failed" and job.conversations_count == 0
        assert job.messages_count == 0
        assert not db.scalar(select(SocialWebhookEvent))
    assert len(calls) == 22


def test_history_rejects_foreign_and_group_messages():
    class Channel:
        external_account_id = "111"
    cutoff = now_utc()
    payload = {"id": "message", "created_time": (cutoff - timedelta(days=1)).isoformat(),
               "from": {"id": "222"}, "to": {"data": [{"id": "333"}]}, "message": "Foreign"}
    assert history.normalize_message(Channel(), payload, cutoff) is None
    payload["to"] = {"data": [{"id": "111"}, {"id": "333"}]}
    assert history.normalize_message(Channel(), payload, cutoff) is None
