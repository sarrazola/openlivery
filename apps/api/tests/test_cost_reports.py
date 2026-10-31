"""Cost reports: every reply's usage is linked to its conversation and
message and priced as the provider reported it (or at list price when it
did not), then rolled up by client, agent, model and day."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from conftest import TestingSession

from app.models import Message, UsageRecord
from app.routers import conversations as conversations_router
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service


def _period() -> str:
    today = date.today()
    return f"from={(today - timedelta(days=1)).isoformat()}&to={(today + timedelta(days=1)).isoformat()}"


def _setup(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Bistro", "is_active": True}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "provider": "openrouter", "model": "openai/gpt-5.6-luna", "name": "Host",
        "instructions": "", "personality": "", "is_active": True,
    }).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    return customer, agent, conversation


def _reply(client: TestClient, monkeypatch, conversation: dict, completion: ai_service.Completion, content: str) -> dict:
    monkeypatch.setattr(conversations_router, "run_completion", AsyncMock(return_value=completion))
    resp = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": content})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_replies_are_linked_priced_and_rolled_up(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, agent, conversation = _setup(client)
    priced = ai_service.Completion(text="Hi", input_tokens=1_000, output_tokens=100, cost_usd=0.5,
                                   served_by="Azure", cached_tokens=10, reasoning_tokens=3, duration_ms=1200)
    detail = _reply(client, monkeypatch, conversation, priced, "hello")
    # A reply the provider did not price: luna is 0.0002 per 1k input tokens
    # in the catalog, so a million tokens is estimated at 0.2.
    _reply(client, monkeypatch, conversation, ai_service.Completion(text="Again", input_tokens=1_000_000, output_tokens=0), "again")

    # The usage record points at the conversation and the assistant message.
    assistant_ids = {m["id"] for m in detail["messages"] if m["role"] == "assistant"}
    with TestingSession() as db:
        records = db.query(UsageRecord).order_by(UsageRecord.created_at).all()
        assert [str(r.conversation_id) for r in records] == [conversation["id"]] * 2
        assert str(records[0].message_id) in assistant_ids
        assert db.get(Message, records[0].message_id).content == "Hi"
        assert (records[0].served_by, records[0].cached_tokens, records[0].reasoning_tokens, records[0].duration_ms) == ("Azure", 10, 3, 1200)

    report = client.get(f"/api/reports/costs?{_period()}&tz=America/Bogota").json()
    totals = report["totals"]
    assert totals["cost_usd"] == 0.7 and totals["replies"] == 2 and totals["conversations"] == 1
    assert totals["input_tokens"] == 1_001_000 and totals["output_tokens"] == 100
    assert totals["avg_cost_per_reply_usd"] == 0.35
    # Counted over the period, not over the page of replies on screen.
    assert totals["estimated_replies"] == 1
    assert report["by_client"] == [{"id": customer["id"], "name": "Bistro", "replies": 2, "input_tokens": 1_001_000, "output_tokens": 100, "cost_usd": 0.7}]
    assert report["by_agent"][0]["id"] == agent["id"] and report["by_agent"][0]["name"] == "Host"
    assert report["by_model"] == [{"id": "openai/gpt-5.6-luna", "name": "openai/gpt-5.6-luna", "replies": 2, "input_tokens": 1_001_000, "output_tokens": 100, "cost_usd": 0.7}]
    assert len(report["by_day"]) == 1 and report["by_day"][0]["replies"] == 2 and report["by_day"][0]["cost_usd"] == 0.7
    assert report["tz"] == "America/Bogota"
    assert client.get(f"/api/reports/costs?{_period()}&tz=Not/AZone").json()["tz"] == "UTC"

    page = client.get(f"/api/reports/replies?{_period()}&limit=1").json()
    assert page["total"] == 2
    newest = page["items"][0]
    assert newest["cost_usd"] == 0.2 and newest["estimated"] is True and newest["served_by"] == ""
    older = client.get(f"/api/reports/replies?{_period()}&limit=1&offset=1").json()["items"][0]
    assert older["cost_usd"] == 0.5 and older["estimated"] is False
    assert older["conversation_id"] == conversation["id"] and older["client_name"] == "Bistro" and older["agent_name"] == "Host"
    assert older["channel"] == "playground" and older["served_by"] == "Azure" and older["duration_ms"] == 1200
    assert older["cached_tokens"] == 10 and older["reasoning_tokens"] == 3 and older["tools"] == 0

    # Filters narrow, the search finds the conversation by id prefix.
    assert client.get(f"/api/reports/replies?{_period()}&model=openai/gpt-5.6-sol").json()["total"] == 0
    assert client.get(f"/api/reports/replies?{_period()}&client_id={customer['id']}").json()["total"] == 2
    assert client.get(f"/api/reports/replies?{_period()}&q={conversation['id'][:8]}").json()["total"] == 2
    assert client.get(f"/api/reports/replies?{_period()}&q=nobody").json()["total"] == 0

    csv_resp = client.get(f"/api/reports/replies?{_period()}&format=csv")
    assert csv_resp.status_code == 200 and csv_resp.headers["content-type"].startswith("text/csv")
    lines = csv_resp.text.strip().splitlines()
    assert lines[0].startswith("date,reply_id,conversation,contact,client,agent,channel,model,served_by")
    assert len(lines) == 3 and lines[1].endswith(",0.20000000,yes,") and lines[2].endswith(",0.50000000,,1200")


def test_replies_can_be_ordered_by_a_column(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, conversation = _setup(client)
    for tokens in (300, 100, 200):
        _reply(client, monkeypatch, conversation,
               ai_service.Completion(text="Hi", input_tokens=tokens, output_tokens=1, cost_usd=tokens / 1000), f"m{tokens}")

    def tokens(sort: str, order: str = "") -> list[int]:
        items = client.get(f"/api/reports/replies?{_period()}&sort={sort}&order={order}").json()["items"]
        return [item["input_tokens"] for item in items]

    assert tokens("input_tokens", "asc") == [100, 200, 300]
    assert tokens("cost_usd", "desc") == [300, 200, 100]
    # Newest first is the default, and an unknown key falls back to it.
    assert tokens("") == [200, 100, 300]
    assert tokens("tool_calls; drop table usage_records") == [200, 100, 300]
    # The export follows the order on screen.
    rows = client.get(f"/api/reports/replies?{_period()}&sort=input_tokens&order=asc&format=csv").text.strip().splitlines()[1:]
    assert [row.split(",")[9] for row in rows] == ["100", "200", "300"]


def test_media_calls_are_recorded_against_the_conversation(authenticated_client: TestClient, monkeypatch):
    """A voice note or image the agent had transcribed or described is usage
    like any reply: linked to the conversation, with the vendor that served it,
    and priced from the catalog when the provider reported no vendor charge."""
    client = authenticated_client
    customer, agent, conversation = _setup(client)
    client.patch(f"/api/agents/{agent['id']}", json={"audio_enabled": True, "image_enabled": True, "image_model": "openai/gpt-4.1"})
    # OpenRouter's audio endpoint: input/output token names, BYOK with no upstream cost.
    # The audio endpoint reports a zero router charge and nothing else about
    # cost, not even the BYOK flag; that is "unknown", never "free".
    transcription = ai_service.completion_from(
        "quiero reservar",
        ai_service.read_usage({"usage": {"input_tokens": 1_000_000, "output_tokens": 0, "cost": 0}}),
        {"provider": "OpenAI"},
    )
    assert transcription.cost_usd is None and transcription.input_tokens == 1_000_000 and transcription.served_by == "OpenAI"
    monkeypatch.setattr(whatsapp_inbound_service, "transcribe_audio", AsyncMock(return_value=transcription))
    monkeypatch.setattr(whatsapp_inbound_service, "describe_image", AsyncMock(return_value=ai_service.Completion(
        text="a menu", input_tokens=500, output_tokens=20, cost_usd=0.001, served_by="Azure")))
    monkeypatch.setattr(conversations_router, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Listo")))

    resp = client.post(f"/api/conversations/{conversation['id']}/media", files={"file": ("note.ogg", b"ogg", "audio/ogg")})
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/conversations/{conversation['id']}/media", files={"file": ("menu.jpg", b"jpg", "image/jpeg")})
    assert resp.status_code == 200, resp.text

    rows = client.get(f"/api/reports/replies?{_period()}").json()["items"]
    by_model = {row["model"]: row for row in rows}
    audio = by_model["openai/gpt-4o-mini-transcribe"]
    # A million audio tokens on mini-transcribe at $3 per million, estimated.
    assert audio["cost_usd"] == 3.0 and audio["estimated"] is True and audio["served_by"] == "OpenAI"
    assert audio["conversation_id"] == conversation["id"] and audio["agent_name"] == "Host"
    image = by_model["openai/gpt-4.1"]
    assert image["cost_usd"] == 0.001 and image["estimated"] is False and image["served_by"] == "Azure"
    assert image["conversation_id"] == conversation["id"]
    assert len(rows) == 2  # the stubbed chat replies used no tokens, so nothing else is recorded
    # Each call is linked to the visitor message that carried the media.
    with TestingSession() as db:
        linked = {str(r.message_id): db.get(Message, r.message_id) for r in db.query(UsageRecord).all()}
    assert len(linked) == 2 and all(m is not None and m.role == "user" for m in linked.values())


def test_reports_need_a_session_and_start_empty(client: TestClient):
    assert client.get(f"/api/reports/costs?{_period()}").status_code == 401
    assert client.get(f"/api/reports/replies?{_period()}").status_code == 401
    client.post("/api/auth/register", json={
        "agency_name": "Agencia Prisma", "name": "Ana Admin", "email": "ana@prisma.com", "password": "contrasena-segura",
    })
    empty = client.get(f"/api/reports/costs?{_period()}").json()
    assert empty["totals"]["replies"] == 0 and empty["by_client"] == [] and empty["by_day"] == []


def test_a_day_in_the_report_is_the_viewers_day(authenticated_client: TestClient, monkeypatch):
    """Cut in UTC, an evening's replies in Bogotá (UTC-5) fell on the next
    day: they were missing from "today" until midnight UTC."""
    from datetime import datetime, timezone

    client = authenticated_client
    _, _, conversation = _setup(client)
    _reply(client, monkeypatch, conversation, ai_service.Completion(text="Hi", input_tokens=10, output_tokens=5, cost_usd=0.01), "hello")
    with TestingSession() as db:
        record = db.query(UsageRecord).one()
        # 23:30 in Bogotá on 2026-10-29 is 04:30 UTC on the 30th.
        record.created_at = datetime(2026, 10, 30, 4, 30, tzinfo=timezone.utc)
        db.commit()
    evening = "from=2026-10-29&to=2026-10-29"
    assert client.get(f"/api/reports/costs?{evening}&tz=America/Bogota").json()["totals"]["replies"] == 1
    assert client.get(f"/api/reports/replies?{evening}&tz=America/Bogota").json()["total"] == 1
    assert client.get(f"/api/reports/costs?from=2026-10-30&to=2026-10-30&tz=America/Bogota").json()["totals"]["replies"] == 0
