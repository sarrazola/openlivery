import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Conversation, Message, now_utc
from app.routers import portal as portal_router


def _portal_with_qr_line(client: TestClient):
    customer = client.post(
        "/api/clients",
        json={"name": "Report Co", "is_active": True},
    ).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@report.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]})
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": "ana@report.co", "password": "secure-portal"})
    return customer


def test_reports_aggregate_the_range(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = _portal_with_qr_line(client)
    slug = customer["portal_slug"]
    monkeypatch.setattr(portal_router, "send_channel_message", AsyncMock(return_value="wamid.r1"))

    contact = client.post(f"/api/portal/{slug}/contacts", json={"name": "Rita", "phone": "573001112233"}).json()
    conv = client.post(
        f"/api/portal/{slug}/contacts/{contact['id']}/conversations", json={"channel": "whatsapp", "text": "Hola Rita"}
    ).json()

    # The contact answers, and the conversation gets resolved.
    with SessionLocal() as db:
        db.add(Message(conversation_id=uuid.UUID(conv["id"]), role="user", content="Hola!", sender_type="visitor"))
        row = db.get(Conversation, uuid.UUID(conv["id"]))
        row.status = "resolved"
        row.resolved_at = now_utc()
        row.first_reply_at = row.created_at + timedelta(seconds=60)
        db.commit()

    # UTC, not the machine's local date: the default report range groups by
    # UTC days (tz_offset 0) and the rows above were stamped in UTC, so a
    # local evening west of Greenwich must not push them out of the range.
    today = now_utc().date()
    frm = (today - timedelta(days=6)).isoformat()
    report = client.get(f"/api/portal/{slug}/reports?from={frm}&to={today.isoformat()}").json()

    assert report["started"] == 1 and report["resolved"] == 1 and report["open_now"] == 0
    assert report["inbound_messages"] == 1 and report["human_replies"] == 1 and report["ai_replies"] == 0
    assert report["active_contacts"] == 1 and report["agents_online"] == 1
    assert report["avg_first_reply_seconds"] == 60.0
    assert len(report["by_day"]) == 7 and sum(d["started"] for d in report["by_day"]) == 1
    assert report["by_channel"] == [{"channel": "whatsapp", "started": 1}]
    ana = report["by_agent"][0]
    assert ana["name"] == "Ana" and ana["replies"] == 1 and ana["assigned"] == 1 and ana["open_now"] == 0

    # An empty earlier range keeps its shape.
    old_from = (today - timedelta(days=30)).isoformat()
    old_to = (today - timedelta(days=24)).isoformat()
    empty = client.get(f"/api/portal/{slug}/reports?from={old_from}&to={old_to}").json()
    assert empty["started"] == 0 and len(empty["by_day"]) == 7 and empty["by_channel"] == []

    assert client.get(f"/api/portal/{slug}/reports?from={today.isoformat()}&to={frm}").status_code == 422

    # The filters narrow every number: a foreign channel empties the report,
    # the assignee filter keeps only that person's activity and row.
    base = f"/api/portal/{slug}/reports?from={frm}&to={today.isoformat()}"
    other_channel = client.get(f"{base}&channel=widget").json()
    assert other_channel["started"] == 0 and other_channel["by_channel"] == []
    ana_id = client.get(f"/api/portal/{slug}/members").json()[0]["id"]
    mine = client.get(f"{base}&assignee_id={ana_id}").json()
    assert mine["started"] == 1 and mine["human_replies"] == 1
    assert len(mine["by_agent"]) == 1 and mine["by_agent"][0]["name"] == "Ana"
