"""A hard block puts the contact on WhatsApp's own block list, next to the
internal block; it exists only where WhatsApp accepts it and is lifted from
the same numbers."""

from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
from sqlalchemy import select, update

from app.models import Contact, Message, WhatsAppCloudChannel, now_utc
from app.services import whatsapp_cloud, whatsapp_inbound
from app.services.ai import Completion
from conftest import TestingSession
from test_whatsapp_cloud import _post_signed, _setup_channel, _webhook_payload

PHONE = "573001112233"
BSUID = "CO.123456789012345Ab"
TOO_OLD = {"message": "Re-engagement required", "code": 131047, "error_data": {"details": "User has not messaged in the last 24 hours"}}


class Graph:
    """Stands in for the Graph API: answers sends, and block-list calls with
    whatever the test decides."""

    def __init__(self):
        self.block_calls: list[tuple[str, str, dict]] = []
        self.refuse_block = None
        self.refuse_unblock = None

    async def __call__(self, method, url, access_token, **kwargs):
        if not url.endswith("/block_users"):
            return httpx.Response(200, json={"messages": [{"id": "wamid.reply"}]})
        entry = kwargs["json"]["block_users"][0]
        self.block_calls.append((method, url.rsplit("/", 2)[-2], entry))
        user = entry.get("user") or entry.get("user_id")
        refusal = self.refuse_block if method == "POST" else self.refuse_unblock
        if refusal:
            failed = {"block_users": {"failed_users": [{"input": user, "errors": [refusal]}]}, "error": {"message": "(#139100) Failed to block/unblock users"}}
            return httpx.Response(400, json=failed)
        done = "added_users" if method == "POST" else "removed_users"
        return httpx.Response(200, json={"messaging_product": "whatsapp", "block_users": {done: [{"input": user, "wa_id": user}]}})


def _setup(client, monkeypatch, sender: dict | None = None):
    """A client with a WhatsApp API number, a portal session, and one person
    who just wrote in. Returns (slug, contact, graph)."""
    customer, _agent, channel = _setup_channel(client)
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@bistro.com", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    slug = customer["portal_slug"]
    client.post(f"/api/portal/{slug}/login", json={"email": "ana@bistro.com", "password": "secure-portal"})
    monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(return_value=Completion(text="Welcome!")))
    graph = Graph()
    monkeypatch.setattr(whatsapp_cloud, "graph_request", graph)
    message = {"id": "wamid.in", "timestamp": str(int(now_utc().timestamp())), "type": "text", "text": {"body": "Hello"}, **(sender or {"from": PHONE})}
    assert _post_signed(client, channel["id"], _webhook_payload([message])).status_code == 200
    contact = client.get(f"/api/portal/{slug}/contacts").json()[0]
    return slug, contact, graph


def _block(client, slug, contact, **payload):
    return client.post(f"/api/portal/{slug}/contacts/{contact['id']}/block", json=payload)


def _options(client, slug, contact):
    return client.get(f"/api/portal/{slug}/contacts/{contact['id']}/block").json()


def test_a_hard_block_reaches_whatsapp_and_unblocking_lifts_it(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch)
    assert contact["hard_blocked"] is False
    assert _options(client, slug, contact) == {"hard_available": True, "hard_unavailable_reason": None}

    blocked = _block(client, slug, contact, blocked=True, hard=True)
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["blocked_at"] and blocked.json()["hard_blocked"] is True
    assert graph.block_calls == [("POST", "111", {"user": PHONE})]

    # Blocking again does not go back to WhatsApp for a number already blocked.
    assert _block(client, slug, contact, blocked=True, hard=True).json()["hard_blocked"] is True
    assert len(graph.block_calls) == 1

    unblocked = _block(client, slug, contact, blocked=False)
    assert unblocked.status_code == 200, unblocked.text
    assert unblocked.json()["blocked_at"] is None and unblocked.json()["hard_blocked"] is False
    assert graph.block_calls[-1] == ("DELETE", "111", {"user": PHONE})


def test_a_soft_block_tells_whatsapp_nothing_and_can_be_made_hard_later(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch)

    soft = _block(client, slug, contact, blocked=True).json()
    assert soft["blocked_at"] and soft["hard_blocked"] is False
    assert graph.block_calls == []

    hard = _block(client, slug, contact, blocked=True, hard=True).json()
    assert hard["blocked_at"] == soft["blocked_at"] and hard["hard_blocked"] is True
    assert graph.block_calls == [("POST", "111", {"user": PHONE})]


def test_a_hidden_number_is_blocked_by_its_user_id(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch, sender={"from_user_id": BSUID})

    assert _block(client, slug, contact, blocked=True, hard=True).json()["hard_blocked"] is True
    assert graph.block_calls == [("POST", "111", {"user_id": BSUID})]


def test_a_hard_block_needs_a_message_in_the_last_24_hours(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch)
    with TestingSession() as db:
        db.execute(update(Message).values(created_at=now_utc() - timedelta(hours=25)))
        db.commit()

    assert _options(client, slug, contact) == {"hard_available": False, "hard_unavailable_reason": "window_closed"}
    refused = _block(client, slug, contact, blocked=True, hard=True)
    assert refused.status_code == 409 and "24 hours" in refused.json()["detail"]
    assert graph.block_calls == []
    # Nothing changed: the contact is not even soft-blocked.
    assert client.get(f"/api/portal/{slug}/contacts").json()[0]["blocked_at"] is None


def test_a_contact_without_a_whatsapp_api_conversation_can_only_be_soft_blocked(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, _contact, graph = _setup(client, monkeypatch)
    manual = client.post(f"/api/portal/{slug}/contacts", json={"name": "Walk-in", "phone": "573005550000"}).json()

    assert _options(client, slug, manual) == {"hard_available": False, "hard_unavailable_reason": "no_whatsapp_api"}
    assert _block(client, slug, manual, blocked=True, hard=True).status_code == 409
    assert _block(client, slug, manual, blocked=True).json()["hard_blocked"] is False
    assert graph.block_calls == []


def test_when_whatsapp_refuses_nothing_is_blocked(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch)
    graph.refuse_block = TOO_OLD

    refused = _block(client, slug, contact, blocked=True, hard=True)
    assert refused.status_code == 502
    assert "User has not messaged in the last 24 hours" in refused.json()["detail"]
    after = client.get(f"/api/portal/{slug}/contacts").json()[0]
    assert after["blocked_at"] is None and after["hard_blocked"] is False


def test_a_refused_unblock_keeps_the_contact_blocked(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, graph = _setup(client, monkeypatch)
    _block(client, slug, contact, blocked=True, hard=True)
    graph.refuse_unblock = {"message": "Something went wrong", "code": 131000}

    assert _block(client, slug, contact, blocked=False).status_code == 502
    still = client.get(f"/api/portal/{slug}/contacts").json()[0]
    assert still["blocked_at"] and still["hard_blocked"] is True

    graph.refuse_unblock = None
    assert _block(client, slug, contact, blocked=False).json()["hard_blocked"] is False


def test_a_hard_blocked_contact_is_not_deleted_or_merged_away(authenticated_client, monkeypatch):
    client = authenticated_client
    slug, contact, _graph = _setup(client, monkeypatch)
    other = client.post(f"/api/portal/{slug}/contacts", json={"name": "Keeper", "phone": "573005550000"}).json()
    _block(client, slug, contact, blocked=True, hard=True)

    assert client.delete(f"/api/portal/{slug}/contacts/{contact['id']}").status_code == 409
    merge = client.post(f"/api/portal/{slug}/contacts/{contact['id']}/merge", json={"primary_contact_id": other["id"]})
    assert merge.status_code == 409
    with TestingSession() as db:
        channel_id = str(db.scalar(select(WhatsAppCloudChannel.id)))
        assert db.scalar(select(Contact).where(Contact.phone == PHONE)).whatsapp_blocks == [{"channel_id": channel_id, "user": PHONE}]

    # Unblocked, both go through again.
    _block(client, slug, contact, blocked=False)
    assert client.delete(f"/api/portal/{slug}/contacts/{contact['id']}").status_code == 204

