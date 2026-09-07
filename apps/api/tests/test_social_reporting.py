"""Connected channel totals and operational metrics exclude imported archives."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import (
    Agency, Agent, Client, Contact, Conversation, Message, PortalUser,
    SocialChannel, WhatsAppChannel, WhatsAppCloudChannel, now_utc,
)
from conftest import TestingSession


def _resources(api, *, portal=False):
    response = api.post("/api/clients", json={"name": "Reporting account"})
    assert response.status_code == 201, response.text
    customer = response.json()
    response = api.post("/api/agents", json={
        "client_id": customer["id"], "name": "Reporting agent", "model": "",
    })
    assert response.status_code == 201, response.text
    agent_id = uuid.UUID(response.json()["id"])
    if portal:
        response = api.post(f"/api/clients/{customer['id']}/portal-users", json={
            "name": "Reporting operator", "email": "operator@example.com", "password": "reporting-password",
        })
        assert response.status_code == 201, response.text
        response = api.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
        assert response.status_code == 200, response.text
        response = api.post(f"/api/portal/{customer['portal_slug']}/login", json={
            "email": "operator@example.com", "password": "reporting-password",
        })
        assert response.status_code == 200, response.text
    with TestingSession() as db:
        agent = db.get(Agent, agent_id)
        member = db.scalar(select(PortalUser).where(PortalUser.client_id == agent.client_id)) if portal else None
        return SimpleNamespace(client_id=agent.client_id, agent_id=agent.id, agency_id=agent.agency_id,
                               slug=customer["portal_slug"], member_id=member.id if member else None)


def test_dashboard_counts_both_social_channels_and_official_whatsapp(authenticated_client):
    api = authenticated_client
    resource = _resources(api)
    with TestingSession() as db:
        shared = dict(agency_id=resource.agency_id, client_id=resource.client_id, agent_id=resource.agent_id)
        instagram = SocialChannel(**shared, provider="instagram", external_account_id="111", status="connected", is_enabled=True)
        messenger = SocialChannel(**shared, provider="messenger", external_account_id="222", status="connected", is_enabled=False)
        db.add_all([
            WhatsAppChannel(**shared, status="disconnected"),
            WhatsAppCloudChannel(**shared, status="connected", is_enabled=True),
            instagram, messenger,
        ])
        # A configured channel belonging to another agency must not inflate
        # the logged-in agency's totals.
        other = Agency(name="Other reporting agency", slug="other-reporting-agency")
        db.add(other)
        db.flush()
        customer = Client(agency_id=other.id, name="Other account", portal_slug="other-reporting-account")
        db.add(customer)
        db.flush()
        agent = Agent(agency_id=other.id, client_id=customer.id, name="Other agent", model="")
        db.add(agent)
        db.flush()
        db.add(SocialChannel(agency_id=other.id, client_id=customer.id, agent_id=agent.id,
                             provider="instagram", external_account_id="333", status="connected", is_enabled=True))
        db.commit()
        instagram_id, messenger_id = instagram.id, messenger.id
    response = api.get("/api/dashboard")
    assert response.status_code == 200, response.text
    assert response.json()["channels"] == 4
    assert response.json()["connected_channels"] == 2
    with TestingSession() as db:
        db.get(SocialChannel, messenger_id).is_enabled = True
        db.commit()
    assert api.get("/api/dashboard").json()["connected_channels"] == 3
    with TestingSession() as db:
        db.get(SocialChannel, instagram_id).status = "reauthorization_required"
        db.commit()
    assert api.get("/api/dashboard").json()["connected_channels"] == 2


def _report(api, slug, provider):
    today = now_utc().date()
    response = api.get(f"/api/portal/{slug}/reports", params={
        "from": (today - timedelta(days=6)).isoformat(), "to": today.isoformat(), "channel": provider,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _inbox(api, path, conversation_id):
    response = api.get(path)
    assert response.status_code == 200, response.text
    return next(row for row in response.json() if row["id"] == str(conversation_id))


@pytest.mark.parametrize("provider", ["instagram", "messenger"])
def test_imported_messages_do_not_inflate_metrics_unread_or_operator_reports(authenticated_client, provider):
    api = authenticated_client
    resource = _resources(api, portal=True)
    current = now_utc()
    with TestingSession() as db:
        channel = SocialChannel(agency_id=resource.agency_id, client_id=resource.client_id,
            agent_id=resource.agent_id, provider=provider, external_account_id="111", status="connected", is_enabled=True)
        contact = Contact(client_id=resource.client_id, name="Social contact", phone=None)
        db.add_all([channel, contact])
        db.flush()
        conversation = Conversation(agency_id=resource.agency_id, client_id=resource.client_id,
            agent_id=resource.agent_id, social_channel_id=channel.id, contact_id=contact.id,
            channel=provider, external_chat_id="222", mode="human", status="resolved",
            assignee_id=resource.member_id, assigned_at=current - timedelta(days=1),
            created_at=current - timedelta(days=1), resolved_at=current - timedelta(hours=20),
            first_reply_at=current - timedelta(hours=23))
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
        db.add_all([
            Message(conversation_id=conversation_id, role="user", sender_type="visitor",
                content="Imported visitor message", is_historical=True, created_at=current - timedelta(days=1)),
            Message(conversation_id=conversation_id, role="assistant", sender_type="human",
                portal_user_id=resource.member_id, content="Imported human reply", is_historical=True,
                created_at=current - timedelta(hours=23)),
            Message(conversation_id=conversation_id, role="assistant", sender_type="ai",
                content="Imported automatic reply", is_historical=True, created_at=current - timedelta(hours=22)),
        ])
        db.commit()
    for path in ("/api/conversations/inbox", f"/api/portal/{resource.slug}/conversations"):
        archive = _inbox(api, path, conversation_id)
        assert archive["unread_count"] == 0 and archive["unread"] is False
    metrics = api.get("/api/dashboard/metrics", params={"days": 7}).json()
    assert metrics["messages"] == 0 and metrics["human_conversations"] == 0
    assert metrics["by_channel"] == {} and metrics["top_agents"] == []
    assert sum(row["count"] for row in metrics["daily_conversations"]) == 0
    archive_report = _report(api, resource.slug, provider)
    for metric in ("started", "resolved", "open_now", "inbound_messages", "human_replies", "ai_replies", "active_contacts"):
        assert archive_report[metric] == 0, (metric, archive_report)
    assert archive_report["by_channel"] == []
    assert archive_report["by_agent"][0]["replies"] == 0
    assert archive_report["by_agent"][0]["assigned"] == 0

    # History can also be present in a conversation with current activity.
    # Every report must still count only actual inbox messages.
    with TestingSession() as db:
        conversation = db.get(Conversation, conversation_id)
        conversation.status = "open"
        conversation.resolved_at = None
        conversation.social_last_inbound_at = now_utc()
        db.add_all([
            Message(conversation_id=conversation_id, role="user", sender_type="visitor",
                content="Current visitor message", is_historical=False),
            Message(conversation_id=conversation_id, role="assistant", sender_type="human",
                portal_user_id=resource.member_id, content="Current human reply", is_historical=False),
        ])
        db.commit()
    for path in ("/api/conversations/inbox", f"/api/portal/{resource.slug}/conversations"):
        active = _inbox(api, path, conversation_id)
        assert active["unread_count"] == 1 and active["unread"] is True
    metrics = api.get("/api/dashboard/metrics", params={"days": 7}).json()
    assert metrics["messages"] == 2 and metrics["human_conversations"] == 1
    assert metrics["by_channel"] == {provider: 1}
    assert sum(row["count"] for row in metrics["daily_conversations"]) == 1
    assert metrics["top_agents"][0]["conversations"] == 1
    current_report = _report(api, resource.slug, provider)
    assert current_report["started"] == 1 and current_report["resolved"] == 0 and current_report["open_now"] == 1
    assert current_report["inbound_messages"] == 1 and current_report["human_replies"] == 1 and current_report["ai_replies"] == 0
    assert current_report["active_contacts"] == 1
    assert current_report["by_channel"] == [{"channel": provider, "started": 1}]
    assert current_report["by_agent"][0]["replies"] == 1
    assert current_report["by_agent"][0]["assigned"] == 1
