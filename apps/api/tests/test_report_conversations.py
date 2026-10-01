"""The conversation list behind the reports: one row per conversation, the
same filters on the agency and the portal side, the ad referral as filters
and facets, and a CSV of the same list."""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Conversation, Message, now_utc
from app.routers import portal as portal_router

AD = {"source_type": "ad", "source_id": "120211", "source_url": "https://fb.me/x", "headline": "Spring sale", "media_type": "image", "ctwa_clid": "AfQ3x"}
POST = {"source_type": "post", "source_id": "998", "headline": "Our new place"}


def _setup(client: TestClient, monkeypatch):
    """A client with three conversations: one from an ad (resolved by a
    person), one from a post (open, AI), one with no referral (resolved by
    the AI, yesterday)."""
    customer = client.post("/api/clients", json={"name": "List Co", "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@list.co", "password": "secure-portal", "role": "admin"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    slug = customer["portal_slug"]
    client.post(f"/api/portal/{slug}/login", json={"email": "ana@list.co", "password": "secure-portal"})
    monkeypatch.setattr(portal_router, "send_channel_message", AsyncMock(return_value="wamid.o1"))
    ids = []
    for name, phone in (("Rita", "573001112233"), ("Luis", "573004445566"), ("Mar", "573007778899")):
        contact = client.post(f"/api/portal/{slug}/contacts", json={"name": name, "phone": phone}).json()
        conv = client.post(f"/api/portal/{slug}/contacts/{contact['id']}/conversations", json={"channel": "whatsapp", "text": f"Hola {name}"}).json()
        ids.append(uuid.UUID(conv["id"]))
    with SessionLocal() as db:
        for cid in ids:
            db.add(Message(conversation_id=cid, role="user", content="Hola!", sender_type="visitor"))
        from_ad, from_post, plain = (db.get(Conversation, cid) for cid in ids)
        from_ad.acquisition = AD
        from_ad.status, from_ad.resolved_at = "resolved", now_utc()
        from_ad.first_reply_at = from_ad.created_at + timedelta(seconds=30)
        from_post.acquisition = POST
        from_post.taken_over_at = None
        from_post.mode = "ai"
        plain.status, plain.resolved_at = "resolved", now_utc()
        plain.taken_over_at = None
        plain.mode = "ai"
        plain.created_at = now_utc() - timedelta(days=1)
        db.commit()
    return customer, [str(cid) for cid in ids]


def _range(days: int = 6) -> str:
    today = now_utc().date()
    return f"from={(today - timedelta(days=days)).isoformat()}&to={today.isoformat()}"


def test_agency_list_filters_and_sums_the_range(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, (from_ad, from_post, plain) = _setup(client, monkeypatch)

    page = client.get(f"/api/reports/conversations?{_range()}").json()
    assert page["total"] == 3 and len(page["items"]) == 3
    assert page["summary"]["conversations"] == 3 and page["summary"]["handoffs"] >= 1
    by_id = {item["id"]: item for item in page["items"]}
    assert by_id[from_ad]["acquisition"]["headline"] == "Spring sale"
    assert by_id[from_ad]["first_reply_s"] == 30.0 and by_id[from_ad]["status"] == "resolved"
    assert by_id[from_ad]["contact_name"] == "Rita" and by_id[from_ad]["contact_phone"] == "573001112233"
    assert by_id[from_ad]["client_name"] == "List Co" and by_id[from_ad]["agent_name"] == "Host"
    assert by_id[from_ad]["inbound"] == 1 and by_id[from_ad]["human_replies"] == 1
    assert by_id[plain]["acquisition"] is None
    # Newest first.
    assert [item["id"] for item in page["items"]][-1] == plain

    # The case's state, the referral's presence and one of its keys.
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&status=open").json()["items"]} == {from_post}
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&ad=any").json()["items"]} == {from_ad, from_post}
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&ad=none").json()["items"]} == {plain}
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&ad_source_type=post").json()["items"]} == {from_post}
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&ad_headline=Spring%20sale").json()["items"]} == {from_ad}
    assert client.get(f"/api/reports/conversations?{_range()}&ad_headline=Nope").json()["total"] == 0
    # Contact search by name or phone, scope by client, and a range that
    # leaves yesterday out.
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&q=rita").json()["items"]} == {from_ad}
    assert {i["id"] for i in client.get(f"/api/reports/conversations?{_range()}&q=7778").json()["items"]} == {plain}
    assert client.get(f"/api/reports/conversations?{_range()}&client_id={uuid.uuid4()}").json()["total"] == 0
    assert client.get(f"/api/reports/conversations?{_range(0)}&tz=UTC").json()["total"] == 2

    # Paging keeps the total.
    first = client.get(f"/api/reports/conversations?{_range()}&limit=2&offset=0").json()
    rest = client.get(f"/api/reports/conversations?{_range()}&limit=2&offset=2").json()
    assert first["total"] == rest["total"] == 3 and len(first["items"]) == 2 and len(rest["items"]) == 1


def test_facets_report_the_referral_keys_present(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _setup(client, monkeypatch)
    facets = client.get(f"/api/reports/conversations/facets?{_range()}").json()
    assert facets["with_ad"] == 2 and facets["without_ad"] == 1
    keys = {facet["key"]: {v["value"]: v["count"] for v in facet["values"]} for facet in facets["facets"]}
    assert keys["source_type"] == {"ad": 1, "post": 1}
    assert keys["headline"] == {"Spring sale": 1, "Our new place": 1}
    assert "ctwa_clid" not in keys and "body" not in keys
    # Keys appear in a fixed order so the selectors do not jump around.
    assert [facet["key"] for facet in facets["facets"]] == ["source_type", "source_id", "source_url", "headline", "media_type"]


def test_csv_flattens_the_referral(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _setup(client, monkeypatch)
    response = client.get(f"/api/reports/conversations?{_range()}&format=csv&ad=any")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("started_at,conversation,status") and lines[0].endswith("ad_body,ad_media_type")
    assert len(lines) == 3
    assert any("Spring sale" in line and "120211" in line for line in lines[1:])


def test_portal_list_is_scoped_and_needs_the_permission(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, (from_ad, from_post, plain) = _setup(client, monkeypatch)
    slug = customer["portal_slug"]

    page = client.get(f"/api/portal/{slug}/reports/conversations?{_range()}").json()
    assert page["total"] == 3 and page["summary"]["conversations"] == 3
    assert {i["id"] for i in client.get(f"/api/portal/{slug}/reports/conversations?{_range()}&ad_source_id=120211").json()["items"]} == {from_ad}
    facets = client.get(f"/api/portal/{slug}/reports/conversations/facets?{_range()}").json()
    assert facets["with_ad"] == 2
    assert client.get(f"/api/portal/{slug}/reports/conversations?{_range()}&format=csv").status_code == 200
    # A reversed range is rejected on the portal side, as the other report.
    today = now_utc().date().isoformat()
    assert client.get(f"/api/portal/{slug}/reports/conversations?from={today}&to=2000-01-01").status_code == 422

    # Another client's portal sees none of it.
    other = client.post("/api/clients", json={"name": "Other Co", "is_active": True}).json()
    client.post(f"/api/clients/{other['id']}/portal-users", json={"name": "Bo", "email": "bo@other.co", "password": "secure-portal", "role": "admin"})
    client.patch(f"/api/clients/{other['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{other['portal_slug']}/login", json={"email": "bo@other.co", "password": "secure-portal"})
    assert client.get(f"/api/portal/{other['portal_slug']}/reports/conversations?{_range()}").json()["total"] == 0

    # A role without reports.view is turned away.
    client.post(f"/api/clients/{other['id']}/portal-users", json={"name": "Cy", "email": "cy@other.co", "password": "secure-portal", "role": "agent"})
    client.post(f"/api/portal/{other['portal_slug']}/login", json={"email": "cy@other.co", "password": "secure-portal"})
    assert client.get(f"/api/portal/{other['portal_slug']}/reports/conversations?{_range()}").status_code == 403
