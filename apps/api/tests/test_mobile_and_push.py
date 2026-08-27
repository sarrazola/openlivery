"""Mobile sign-in, portal users, and the vendor-neutral notification seam.

Two things these tests exist to hold still:

* An install that upgrades keeps working. A portal that only ever had the single
  legacy e-mail and password must still sign in, in the browser and on a phone.
* Notifications stay optional. With no provider configured nothing is sent and
  nothing is required, which is the default a self-hosted OpenLivery runs on.
"""

import pytest
from fastapi.testclient import TestClient

from app.services import notifications


@pytest.fixture(autouse=True)
def reset_push(monkeypatch):
    """Every test starts with notifications off, as a fresh install would."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "push_provider", "none", raising=False)
    monkeypatch.setattr(settings, "push_webhook_url", "", raising=False)
    monkeypatch.setattr(settings, "push_webhook_secret", "", raising=False)
    yield


def _client_with_portal(client: TestClient, name="Barber Co"):
    customer = client.post(
        "/api/clients",
        json={"name": name, "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    # Mirrors a user carried over from the pre-0021 shared login: real
    # credentials, no display name.
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "", "email": "owner@barberco.com", "password": "legacy-portal-pw"},
    )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    return customer


def _sign_in(client: TestClient, email, password):
    return client.post("/api/mobile/sign-in", json={"email": email, "password": password})


def test_portal_user_signs_in_on_mobile(authenticated_client: TestClient):
    customer = _client_with_portal(authenticated_client)

    session = _sign_in(authenticated_client, "owner@barberco.com", "legacy-portal-pw")
    assert session.status_code == 200
    body = session.json()
    assert body["portal_slug"] == customer["portal_slug"]
    assert body["token"]
    # The session is attributed to the portal user who signed in.
    assert body["user_id"]
    # Nothing is configured, so the app is told not to initialise a push SDK.
    assert body["push"] == {"enabled": False, "provider": "none"}

    assert _sign_in(authenticated_client, "owner@barberco.com", "wrong").status_code == 401
    assert _sign_in(authenticated_client, "nobody@barberco.com", "legacy-portal-pw").status_code == 401


def test_portal_users_can_be_managed_and_sign_in_everywhere(authenticated_client: TestClient):
    client = authenticated_client
    customer = _client_with_portal(client)
    cid = customer["id"]

    created = client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "Ana@BarberCo.com", "password": "ana-password", "name": "Ana"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "ana@barberco.com"
    assert created.json()["devices"] == 0

    # Same address twice on one portal is a conflict, not a second account.
    assert client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "ana@barberco.com", "password": "another-one", "name": "Ana again"},
    ).status_code == 409

    client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "luis@barberco.com", "password": "luis-password", "name": "Luis"},
    )
    listed = client.get(f"/api/clients/{cid}/portal-users").json()
    assert [row["name"] for row in listed] == ["", "Ana", "Luis"]

    # Both can sign in on a phone, each attributed to themselves.
    ana = _sign_in(client, "ana@barberco.com", "ana-password")
    luis = _sign_in(client, "luis@barberco.com", "luis-password")
    assert ana.status_code == 200 and luis.status_code == 200
    assert ana.json()["user_name"] == "Ana"
    assert ana.json()["user_id"] != luis.json()["user_id"]

    # And in the browser portal, which issues the same kind of session.
    browser = client.post(
        f"/api/portal/{customer['portal_slug']}/login",
        json={"email": "ana@barberco.com", "password": "ana-password"},
    )
    assert browser.status_code == 200
    assert client.get(f"/api/portal/{customer['portal_slug']}/conversations").status_code == 200

    # Deactivating ends access without deleting the record.
    ana_id = ana.json()["user_id"]
    assert client.patch(f"/api/clients/{cid}/portal-users/{ana_id}", json={"is_active": False}).status_code == 200
    assert _sign_in(client, "ana@barberco.com", "ana-password").status_code == 401

    assert client.patch(
        f"/api/clients/{cid}/portal-users/{ana_id}", json={"is_active": True, "password": "ana-new-password"}
    ).status_code == 200
    assert _sign_in(client, "ana@barberco.com", "ana-new-password").status_code == 200

    assert client.delete(f"/api/clients/{cid}/portal-users/{ana_id}").status_code == 204
    assert _sign_in(client, "ana@barberco.com", "ana-new-password").status_code == 401


def test_portal_can_be_enabled_with_users_instead_of_a_shared_login(authenticated_client: TestClient):
    """A new client no longer needs the legacy shared password to open a portal."""
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Clinic Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    cid = customer["id"]

    assert client.patch(f"/api/clients/{cid}/portal", json={"portal_enabled": True}).status_code == 400

    client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "front@clinicco.com", "password": "front-desk-pw", "name": "Front desk"},
    )
    assert client.patch(f"/api/clients/{cid}/portal", json={"portal_enabled": True}).status_code == 200
    assert _sign_in(client, "front@clinicco.com", "front-desk-pw").status_code == 200


def test_device_registration_is_accepted_and_deduplicated(authenticated_client: TestClient):
    client = authenticated_client
    customer = _client_with_portal(client)
    cid = customer["id"]
    client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "ana@barberco.com", "password": "ana-password", "name": "Ana"},
    )
    token = _sign_in(client, "ana@barberco.com", "ana-password").json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Push is off, so registering succeeds but reports honestly.
    registered = client.post(
        "/api/mobile/devices",
        json={"token": "device-token-aaa", "provider": "webhook", "platform": "ios"},
        headers=auth,
    )
    assert registered.status_code == 200
    assert registered.json() == {"registered": False, "provider": "none"}

    # The same install registering again moves its row instead of adding one.
    client.post(
        "/api/mobile/devices",
        json={"token": "device-token-aaa", "provider": "webhook", "platform": "ios"},
        headers=auth,
    )
    listed = client.get(f"/api/clients/{cid}/portal-users").json()
    assert [row["devices"] for row in listed] == [0, 1]

    assert client.delete("/api/mobile/devices/device-token-aaa", headers=auth).status_code == 204
    assert [row["devices"] for row in client.get(f"/api/clients/{cid}/portal-users").json()] == [0, 0]

    assert client.post("/api/mobile/devices", json={"token": "x" * 20}).status_code == 401


def test_removing_someone_takes_their_phone_with_them(authenticated_client: TestClient):
    client = authenticated_client
    customer = _client_with_portal(client)
    cid = customer["id"]
    created = client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "luis@barberco.com", "password": "luis-password", "name": "Luis"},
    ).json()
    token = _sign_in(client, "luis@barberco.com", "luis-password").json()["token"]
    client.post(
        "/api/mobile/devices",
        json={"token": "luis-phone-token", "provider": "webhook", "platform": "android"},
        headers={"Authorization": f"Bearer {token}"},
    )

    from app.database import SessionLocal
    from app.models import PushDevice

    client.delete(f"/api/clients/{cid}/portal-users/{created['id']}")
    db = SessionLocal()
    try:
        assert db.query(PushDevice).filter(PushDevice.token == "luis-phone-token").count() == 0
    finally:
        db.close()


def test_no_provider_means_nothing_is_sent(authenticated_client: TestClient, monkeypatch):
    """The default install must not reach out to anyone, ever."""
    assert notifications.configured_provider() == "none"
    assert notifications.push_enabled() is False

    called = False

    async def explode(_notification):
        nonlocal called
        called = True
        return 0

    notifications.register_provider("exploding", explode)
    try:
        sent = notifications.Notification(title="t", body="b", devices=[notifications.Device(token="x")])
        import asyncio

        assert asyncio.run(notifications.notify_devices(sent)) == 0
        assert called is False
    finally:
        notifications._PROVIDERS.pop("exploding", None)


def test_unknown_provider_falls_back_to_silence(authenticated_client: TestClient, monkeypatch):
    """A typo in the environment turns notifications off rather than erroring."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "push_provider", "not-a-real-provider", raising=False)
    assert notifications.configured_provider() == "none"
    assert notifications.push_enabled() is False


def test_webhook_provider_fires_when_a_human_is_expected_to_answer(
    authenticated_client: TestClient, monkeypatch
):
    """The whole point of the seam, end to end, through a public widget message."""
    from unittest.mock import AsyncMock

    from app.config import get_settings
    from app.routers import widget as widget_router
    from app.services import ai as ai_service

    client = authenticated_client
    customer = _client_with_portal(client)
    cid = customer["id"]
    client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "ana@barberco.com", "password": "ana-password", "name": "Ana"},
    )
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": cid, "provider": "openai", "model": "gpt-4.1-mini", "name": "Sofia",
            "description": "", "instructions": "", "personality": "", "is_active": True,
        },
    ).json()
    client.patch(f"/api/agents/{agent['id']}", json={"widget_enabled": True})
    public_id = agent["widget_public_id"]

    monkeypatch.setattr(
        widget_router, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hello!"))
    )
    client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "hi"})

    session_token = _sign_in(client, "ana@barberco.com", "ana-password").json()["token"]
    client.post(
        "/api/mobile/devices",
        json={"token": "ana-phone-token", "provider": "webhook", "platform": "ios"},
        headers={"Authorization": f"Bearer {session_token}"},
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "push_provider", "webhook", raising=False)
    monkeypatch.setattr(settings, "push_webhook_url", "https://hooks.example.com/openlivery", raising=False)
    monkeypatch.setattr(settings, "push_webhook_secret", "shhh", raising=False)

    posted = {}

    class _Response:
        status_code = 200
        text = "ok"

    class _FakeAsyncClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, json=None, headers=None):
            posted["url"] = url
            posted["json"] = json
            posted["headers"] = headers
            return _Response()

    monkeypatch.setattr(notifications.httpx, "AsyncClient", _FakeAsyncClient)

    # While the assistant answers, nobody is notified.
    client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "and on Sunday?"})
    assert posted == {}

    # Once a person takes the conversation over, the next message rings.
    conversation_id = client.get("/api/conversations/inbox").json()[0]["id"]
    client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"})
    client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "are you open Saturday?"})

    assert posted["url"] == "https://hooks.example.com/openlivery"
    assert posted["headers"]["Authorization"] == "Bearer shhh"
    # A web visitor is anonymous, so the heading names the channel rather than
    # echoing their first message back as if it had just arrived.
    assert posted["json"]["title"] == "Web chat"
    assert posted["json"]["body"] == "are you open Saturday?"
    assert posted["json"]["data"]["conversation_id"] == conversation_id
    assert [d["token"] for d in posted["json"]["devices"]] == ["ana-phone-token"]


def test_tokens_from_another_provider_are_skipped(authenticated_client: TestClient, monkeypatch):
    """Switching providers must not send old tokens somewhere they can't arrive."""
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import Client as ClientModel

    client = authenticated_client
    customer = _client_with_portal(client)
    token = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()["token"]
    client.post(
        "/api/mobile/devices",
        json={"token": "stale-token", "provider": "old-provider", "platform": "ios"},
        headers={"Authorization": f"Bearer {token}"},
    )

    monkeypatch.setattr(get_settings(), "push_provider", "webhook", raising=False)
    db = SessionLocal()
    try:
        model = db.query(ClientModel).filter(ClientModel.id == customer["id"]).one()
        assert notifications.devices_for_client(db, model.id) == []
    finally:
        db.close()


def test_replies_are_signed_by_the_person_not_the_business(authenticated_client: TestClient):
    """And never by their e-mail, which the customer would see."""
    client = authenticated_client
    customer = _client_with_portal(client)
    slug, cid = customer["portal_slug"], customer["id"]
    agent = client.post(
        "/api/agents",
        json={
            "client_id": cid, "name": "Sofia", "description": "", "instructions": "",
            "personality": "", "model": "", "is_active": True,
        },
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()

    def reply_as(token, text):
        client.patch(
            f"/api/portal/{slug}/conversations/{conversation['id']}/mode",
            headers={"Authorization": f"Bearer {token}"},
            json={"mode": "human"},
        )
        answer = client.post(
            f"/api/portal/{slug}/conversations/{conversation['id']}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"content": text},
        )
        assert answer.status_code == 200
        return answer.json()["messages"][-1]["sender_name"]

    client.post(
        f"/api/clients/{cid}/portal-users",
        json={"email": "ana@barberco.com", "password": "ana-password", "name": "Ana"},
    )
    named = _sign_in(client, "ana@barberco.com", "ana-password").json()["token"]
    assert reply_as(named, "I can confirm that") == "Ana"

    # Someone carried over from the old shared login has no name, and their
    # address is a credential - the business's name is what the customer sees.
    legacy = _sign_in(client, "owner@barber.test".replace("barber.test", "barberco.com"), "legacy-portal-pw")
    assert legacy.status_code == 200
    assert reply_as(legacy.json()["token"], "So can I") == "Barber Co"
