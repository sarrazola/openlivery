"""Inactivity follow-ups, the closing they end in, and agent-resolved cases."""

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.models import Agent, Conversation, Message, SocialChannel, WhatsAppChannel, now_utc
from app.routers import widget as widget_router
from app.security import encrypt_secret
from app.services import follow_ups, social_delivery, social_graph, social_inbound, social_worker
from app.services import whatsapp_inbound as pipeline
from app.services.ai import Completion
from app.services.conversation_state import resolve_idle_ai_conversations
from conftest import TestingSession

CHAT = "573001112233@s.whatsapp.net"
SCHEDULE = {"enabled": True, "first_minutes": 60, "second_minutes": 180, "close_minutes": 360}


@pytest.fixture
def setup(authenticated_client, monkeypatch):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Barber shop", "industry": "other"}).json()
    assert client.put("/api/providers/openrouter", json={"api_key": "sk-test"}).status_code == 200
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Appointments",
        "model": "openai/gpt-4.1-mini", "prompt_language": "en"}).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    channel_id = uuid.UUID(channel["id"])
    with TestingSession() as db:
        row = db.get(WhatsAppChannel, channel_id)
        row.status = "connected"
        row.is_enabled = True
        db.commit()
    reply = AsyncMock(return_value=Completion(text="Shall I book you for tomorrow at 3?"))
    nudge = AsyncMock(return_value=Completion(text="Still want that slot tomorrow?", input_tokens=10, output_tokens=5))
    send = AsyncMock(side_effect=lambda *args, **kwargs: f"sent-{uuid.uuid4().hex}")
    monkeypatch.setattr(pipeline, "run_completion", reply)
    monkeypatch.setattr(follow_ups, "chat_completion", nudge)
    monkeypatch.setattr("app.services.whatsapp.send_channel_message", send)

    class Setup:
        pass

    s = Setup()
    s.client, s.customer, s.agent, s.channel_id = client, customer, agent, channel_id
    s.headers = {"X-Bridge-Token": get_settings().whatsapp_bridge_token}
    s.reply, s.nudge, s.send = reply, nudge, send
    return s


def configure(s, **overrides):
    response = s.client.put(f"/api/agents/{s.agent['id']}/follow-ups", json={**SCHEDULE, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def incoming(s, mid="customer-1", text="Do you have a slot tomorrow?"):
    response = s.client.post(f"/api/internal/whatsapp/channels/{s.channel_id}/inbound", headers=s.headers,
        json={"external_message_id": mid, "remote_jid": CHAT, "text": text})
    assert response.status_code == 200, response.text
    return response.json()


def conversation_of(s, db):
    return db.scalar(select(Conversation).where(Conversation.whatsapp_channel_id == s.channel_id)
                     .order_by(Conversation.created_at.desc()).limit(1))


def state(s):
    with TestingSession() as db:
        row = conversation_of(s, db)
        return row.status, row.follow_up_step, row.follow_up_due_at, row.pending_resolution


def rewind(s, minutes):
    """Move the conversation's clock back, as if ``minutes`` had passed."""
    with TestingSession() as db:
        row = conversation_of(s, db)
        delta = timedelta(minutes=minutes)
        row.follow_up_anchor_at -= delta
        row.follow_up_due_at -= delta
        for message in db.scalars(select(Message).where(Message.conversation_id == row.id)):
            message.created_at -= delta
        db.commit()


def sweep():
    with TestingSession() as db:
        return asyncio.run(follow_ups.run_due(db))


def messages(s):
    with TestingSession() as db:
        row = conversation_of(s, db)
        return db.scalars(select(Message).where(Message.conversation_id == row.id).order_by(Message.created_at)).all()


def test_schedule_is_validated(setup):
    s = setup
    initial = s.client.get(f"/api/agents/{s.agent['id']}/follow-ups").json()
    assert initial["enabled"] is False and initial["resolve_enabled"] is False
    assert initial["max_minutes"] == 23 * 60 and "whatsapp_cloud" in initial["available_channels"]

    saved = configure(s, channels=["whatsapp", "whatsapp", "widget"], resolve_enabled=True)
    assert saved["channels"] == ["whatsapp", "widget"] and saved["resolve_enabled"] is True

    def rejected(**overrides):
        return s.client.put(f"/api/agents/{s.agent['id']}/follow-ups", json={**SCHEDULE, **overrides}).status_code == 422

    assert rejected(first_minutes=None)                      # enabled needs a first follow-up
    assert rejected(close_minutes=None)                      # and a closing
    assert rejected(second_minutes=30)                       # out of order
    assert rejected(close_minutes=24 * 60)                   # past the reply window
    assert rejected(first_minutes=1)                         # below the minimum
    assert rejected(channels=["playground"])                 # not a channel a contact waits on
    assert rejected(first_minutes=None, enabled=False)       # a second without a first
    # Switched off, an empty schedule is fine.
    assert not rejected(enabled=False, first_minutes=None, second_minutes=None, close_minutes=None)


def test_the_sequence_follows_up_twice_and_closes(setup):
    s = setup
    configure(s)
    assert incoming(s)["reply"] == "Shall I book you for tomorrow at 3?"
    status, step, due, _ = state(s)
    assert status == "open" and step == 0
    assert timedelta(minutes=59) < due - now_utc() < timedelta(minutes=61)

    assert sweep() == 0                                       # nothing is due yet
    s.nudge.assert_not_awaited()

    rewind(s, 61)
    sweep()
    s.send.assert_awaited_once()
    assert s.send.await_args.args[2] == "Still want that slot tomorrow?"
    turns = s.nudge.await_args.args[4]
    assert "INACTIVITY FOLLOW-UP" in turns[0]["content"] and "stopped answering" in turns[0]["content"]
    assert turns[-1]["role"] == "user" and "1 hour have passed" in turns[-1]["content"]
    assert turns[-2] == {"role": "assistant", "content": "Shall I book you for tomorrow at 3?"}
    status, step, due, _ = state(s)
    assert status == "open" and step == 1
    assert timedelta(minutes=118) < due - now_utc() < timedelta(minutes=120)   # 180 from the reply, 61 gone

    rewind(s, 120)
    sweep()
    assert "not even your previous follow-up" in s.nudge.await_args.args[4][0]["content"]
    assert state(s)[1] == 2

    rewind(s, 180)
    s.nudge.return_value = Completion(text="I'll close this for now. Write whenever you like.")
    sweep()
    assert "CLOSING FOR INACTIVITY" in s.nudge.await_args.args[4][0]["content"]
    assert "6 hours have passed" in s.nudge.await_args.args[4][-1]["content"]
    assert s.send.await_count == 3
    status, step, due, _ = state(s)
    assert status == "resolved" and step == 0 and due is None
    thread = messages(s)
    assert thread[-1].kind == "activity" and thread[-1].activity == {"event": "closed_unanswered", "hours": 6}
    assert [m.content for m in thread if m.sender_type == "ai"][-1] == "I'll close this for now. Write whenever you like."
    assert sweep() == 0


def test_an_answer_stops_the_clock_and_the_next_reply_restarts_it(setup):
    s = setup
    configure(s)
    incoming(s)
    rewind(s, 61)
    sweep()
    assert state(s)[1] == 1
    incoming(s, "customer-2", "Yes please")
    status, step, due, _ = state(s)
    assert status == "open" and step == 0
    assert timedelta(minutes=59) < due - now_utc() < timedelta(minutes=61)    # counts from the new reply


def test_a_person_taking_over_ends_the_sequence(setup):
    s = setup
    configure(s)
    incoming(s)
    with TestingSession() as db:
        cid = conversation_of(s, db).id
    assert s.client.patch(f"/api/conversations/{cid}/mode", json={"mode": "human"}).status_code == 200
    assert state(s)[2] is None
    sweep()
    s.nudge.assert_not_awaited()
    s.send.assert_not_awaited()


def test_a_human_held_conversation_with_a_stale_clock_is_left_alone(setup):
    """The sweep re-checks: a path that forgot to stop the clock sends nothing."""
    s = setup
    configure(s)
    incoming(s)
    rewind(s, 61)
    with TestingSession() as db:
        conversation_of(s, db).mode = "human"
        db.commit()
    sweep()
    s.nudge.assert_not_awaited()
    assert state(s)[2] is None


def test_channels_not_chosen_are_skipped(setup):
    s = setup
    configure(s, channels=["widget"])
    incoming(s)
    assert state(s)[2] is None


def test_a_message_arriving_while_the_follow_up_is_written_cancels_it(setup):
    s = setup
    configure(s)
    incoming(s)
    rewind(s, 61)

    async def slow(*args, **kwargs):
        with TestingSession() as db:
            row = conversation_of(s, db)
            db.add(Message(conversation_id=row.id, role="user", content="Sorry, I'm here", sender_type="visitor"))
            db.commit()
        return Completion(text="Still there?", input_tokens=7, output_tokens=3)

    s.nudge.side_effect = slow
    sweep()
    s.send.assert_not_awaited()
    assert state(s)[2] is None
    assert [m.content for m in messages(s) if m.kind == "message"][-1] == "Sorry, I'm here"


def test_a_follow_up_that_cannot_be_delivered_is_skipped_not_retried(setup):
    s = setup
    configure(s)
    incoming(s)
    rewind(s, 61)
    s.send.side_effect = HTTPException(status_code=502, detail="WhatsApp is not connected")
    sweep()
    status, step, _, _ = state(s)
    assert status == "open" and step == 1
    assert [m.content for m in messages(s) if m.sender_type == "ai"] == ["Shall I book you for tomorrow at 3?"]
    assert sweep() == 0                                       # the second one waits for its own time


def test_a_disconnected_channel_spends_nothing_and_still_closes(setup):
    s = setup
    configure(s, second_minutes=None)
    incoming(s)
    with TestingSession() as db:
        db.get(WhatsAppChannel, s.channel_id).status = "disconnected"
        db.commit()
    rewind(s, 61)
    sweep()
    rewind(s, 300)
    sweep()
    s.nudge.assert_not_awaited()
    s.send.assert_not_awaited()
    assert state(s)[0] == "resolved"


def _resolving(reason="Booked the slot they asked for", farewell="Done, see you tomorrow!", *, escalate=False):
    async def fake(db, agent, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None):
        specs = {spec.name: spec for spec in extra_specs or []}
        assert "CLOSING THE CONVERSATION" in messages[0]["content"]
        result, is_error = specs["resolve_conversation"].handler({"reason": reason})
        assert not is_error, result
        if escalate:
            specs["escalate_to_human"].handler({"trigger": "human_request", "reason": "Asked for a person"})
        return Completion(text=farewell, input_tokens=1, output_tokens=1)

    return fake


def test_the_agent_resolves_a_settled_case_after_its_farewell(setup, monkeypatch):
    s = setup
    configure(s, enabled=False, resolve_enabled=True)
    monkeypatch.setattr(pipeline, "run_completion", _resolving())
    assert incoming(s)["reply"] == "Done, see you tomorrow!"
    status, _, due, pending = state(s)
    assert status == "open"                                   # the farewell goes out first
    assert pending["event"] == "resolved_by_agent" and pending["details"] == {"reason": "Booked the slot they asked for"}
    assert timedelta(seconds=90) < due - now_utc() < timedelta(seconds=121)

    assert sweep() == 0
    rewind(s, 3)
    sweep()
    assert state(s)[0] == "resolved"
    last = messages(s)[-1]
    assert last.activity == {"event": "resolved_by_agent", "reason": "Booked the slot they asked for"}
    assert last.sender_name == "Appointments" and "Booked the slot" in last.content
    s.nudge.assert_not_awaited()


def test_writing_back_before_the_grace_ends_keeps_the_case_open(setup, monkeypatch):
    s = setup
    configure(s, enabled=False, resolve_enabled=True)
    monkeypatch.setattr(pipeline, "run_completion", _resolving())
    incoming(s)
    monkeypatch.setattr(pipeline, "run_completion", s.reply)
    incoming(s, "customer-2", "Oh, one more thing")
    status, _, due, pending = state(s)
    assert status == "open" and pending is None and due is None
    assert sweep() == 0 and state(s)[0] == "open"


def test_without_the_setting_the_agent_has_no_resolve_tool(setup):
    s = setup
    incoming(s)
    assert s.reply.await_args.kwargs["extra_specs"] is None
    assert "resolve_conversation" not in s.reply.await_args.args[4][0]["content"]


def test_escalation_wins_over_resolution(setup, monkeypatch):
    s = setup
    slug = s.customer["portal_slug"]
    s.client.post(f"/api/clients/{s.customer['id']}/portal-users",
                  json={"name": "Ana", "email": "ana@barber.com", "password": "secure-portal"})
    s.client.patch(f"/api/clients/{s.customer['id']}/portal", json={"portal_enabled": True})
    s.client.post(f"/api/portal/{slug}/login", json={"email": "ana@barber.com", "password": "secure-portal"})
    members = s.client.get(f"/api/portal/{slug}/members").json()
    team = s.client.post(f"/api/portal/{slug}/teams", json={"name": "Front desk", "member_ids": [m["id"] for m in members]}).json()
    s.client.put(f"/api/agents/{s.agent['id']}/escalation-rules", json={"default_team_id": team["id"], "rules": []})
    configure(s, resolve_enabled=True)
    monkeypatch.setattr("app.services.whatsapp.bridge_command", AsyncMock(return_value={}))
    monkeypatch.setattr(pipeline, "run_completion", _resolving(escalate=True))
    assert incoming(s)["mode"] == "human"
    status, _, due, pending = state(s)
    assert status == "open" and pending is None and due is None


def test_the_idle_sweep_still_closes_what_has_no_schedule(setup):
    s = setup
    incoming(s)
    assert state(s)[2] is None
    with TestingSession() as db:
        row = conversation_of(s, db)
        for message in db.scalars(select(Message).where(Message.conversation_id == row.id)):
            message.created_at -= timedelta(hours=25)
        db.commit()
        assert resolve_idle_ai_conversations(db, hours=24) == 1
    assert messages(s)[-1].activity == {"event": "auto_resolved", "hours": 24}


def test_the_widget_gets_follow_ups_as_stored_messages(setup, monkeypatch):
    s = setup
    configure(s, second_minutes=None)
    channel = s.client.put(f"/api/webchat/channels/{s.customer['id']}",
                           json={"agent_id": s.agent["id"], "greeting": "Hi!", "color": "#075985", "is_enabled": True}).json()
    monkeypatch.setattr(widget_router, "run_completion", AsyncMock(return_value=Completion(text="What size do you need?")))
    public_id = channel["public_id"]
    assert s.client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "hello"}).status_code == 200

    def widget_conversation(db):
        return db.scalar(select(Conversation).where(Conversation.channel == "widget"))

    with TestingSession() as db:
        row = widget_conversation(db)
        assert row.follow_up_due_at is not None
        row.follow_up_anchor_at -= timedelta(minutes=61)
        row.follow_up_due_at -= timedelta(minutes=61)
        db.commit()
    sweep()
    s.send.assert_not_awaited()                               # the widget reads its messages from the thread
    history = s.client.get(f"/api/widget/{public_id}/history?session_id=s1").json()
    assert [m["content"] for m in history["messages"]][-1] == "Still want that slot tomorrow?"

    # A visitor message stops the clock even though the widget has no inbound hook.
    monkeypatch.setattr(widget_router, "run_completion", AsyncMock(side_effect=HTTPException(status_code=502)))
    s.client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "medium"})
    with TestingSession() as db:
        assert widget_conversation(db).follow_up_due_at is None


def test_a_social_closing_message_is_delivered_before_the_case_ends(setup, monkeypatch):
    s = setup
    configure(s, second_minutes=None)
    monkeypatch.setattr(social_graph, "send_text", AsyncMock(side_effect=lambda *a, **k: f"sent.{uuid.uuid4().hex}"))
    monkeypatch.setattr(social_graph, "sender_profile", AsyncMock(return_value={"name": "", "username": None}))
    monkeypatch.setattr(social_inbound, "reply_delay_seconds", lambda agent: 0)
    with TestingSession() as db:
        agent = db.get(Agent, uuid.UUID(s.agent["id"]))
        channel = SocialChannel(agency_id=agent.agency_id, client_id=agent.client_id, agent_id=agent.id,
            provider="instagram", app_id="999", external_account_id="111", display_name="Shop", status="connected",
            encrypted_access_token=encrypt_secret("test-token"), encrypted_app_secret=encrypt_secret("secret"),
            is_enabled=True, human_agent_enabled=False, connection_source="manual",
            last_connected_at=now_utc().replace(microsecond=0), webhook_verify_token="test-verify")
        db.add(channel)
        db.commit()
        occurred = now_utc().replace(microsecond=0)
        asyncio.run(social_inbound.process_event(db, channel, {
            "sender": {"id": "person-1"}, "recipient": {"id": "111"},
            "timestamp": int(occurred.timestamp() * 1000), "message": {"mid": "in-1", "text": "Hello"}}))
        asyncio.run(social_worker.process_replies(db))
        asyncio.run(social_delivery.process_outbox(db))
        row = db.scalar(select(Conversation).where(Conversation.social_channel_id == channel.id))
        assert row.follow_up_due_at is not None and row.status == "open"
        cid = row.id

    def shift(minutes):
        with TestingSession() as db:
            row = db.get(Conversation, cid)
            row.follow_up_anchor_at -= timedelta(minutes=minutes)
            row.follow_up_due_at -= timedelta(minutes=minutes)
            db.commit()

    shift(61)
    sweep()
    shift(300)
    s.nudge.return_value = Completion(text="Closing this for now.")
    sweep()
    with TestingSession() as db:
        row = db.get(Conversation, cid)
        # Queued for the outbox, which refuses a resolved conversation: the case waits.
        assert row.status == "open" and row.pending_resolution["event"] == "closed_unanswered"
        asyncio.run(social_delivery.process_outbox(db))
        closing = db.scalar(select(Message).where(Message.conversation_id == cid, Message.content == "Closing this for now."))
        assert closing.delivery_status == "sent"
    shift(3)
    sweep()
    with TestingSession() as db:
        assert db.get(Conversation, cid).status == "resolved"
