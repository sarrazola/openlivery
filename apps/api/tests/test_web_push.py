"""Web push: the browser subscribes, the server encrypts and signs, gone
subscriptions drop out, and the mobile seam does not notice any of it."""

import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

from conftest import TestingSession, customer_conversation

from app.models import Conversation, PushDevice
from app.services import notifications, webpush


# --- a browser, in miniature ---------------------------------------------


class Browser:
    """The half of the protocol a browser holds: its key pair and auth secret."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.auth = b"\x01" * 16
        public = self.private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.subscription = {
            "endpoint": endpoint,
            "keys": {"p256dh": webpush.b64url_encode(public), "auth": webpush.b64url_encode(self.auth)},
        }

    def decrypt(self, body: bytes) -> bytes:
        salt, record_size, id_len = body[:16], int.from_bytes(body[16:20], "big"), body[20]
        as_public = body[21 : 21 + id_len]
        ciphertext = body[21 + id_len :]
        assert record_size == webpush.RECORD_SIZE and id_len == 65
        as_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
        shared = self.private.exchange(ec.ECDH(), as_key)
        ua_public = self.private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=self.auth, info=b"WebPush: info\x00" + ua_public + as_public).derive(shared)
        cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
        nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
        plaintext = AESGCM(cek).decrypt(nonce, ciphertext, None)
        assert plaintext.endswith(b"\x02")
        return plaintext[:-1]


@pytest.fixture
def vapid(monkeypatch):
    """Web push on: a key pair in the settings, as a deployment would have."""
    from app.config import get_settings

    private = webpush.generate_private_key()
    monkeypatch.setattr(get_settings(), "push_webpush_private_key", private, raising=False)
    monkeypatch.setattr(get_settings(), "push_webpush_subject", "mailto:ops@example.com", raising=False)
    monkeypatch.setattr(get_settings(), "push_provider", "none", raising=False)
    return private


@pytest.fixture
def push_service(monkeypatch):
    """Stands in for the browser vendors' push services: records every POST,
    answers 201, and 410 for any endpoint under /gone/."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/gone/" in str(request.url):
            return httpx.Response(410)
        return httpx.Response(201)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(webpush.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    return calls


# --- the protocol ----------------------------------------------------------


def test_a_browser_can_read_what_the_server_encrypts_for_it():
    browser = Browser("https://push.example/sub/1")
    subscription = webpush.Subscription.parse(browser.subscription)
    body = webpush.encrypt(b'{"title":"Hola"}', subscription)
    assert browser.decrypt(body) == b'{"title":"Hola"}'
    # Each message takes a fresh salt and sender key: the same text never
    # encrypts to the same bytes.
    assert webpush.encrypt(b'{"title":"Hola"}', subscription) != body
    with pytest.raises(webpush.WebPushError):
        webpush.encrypt(b"x" * (webpush.MAX_PLAINTEXT + 1), subscription)


def test_the_signature_names_the_push_service_and_the_sender(vapid):
    private = webpush.load_private_key(vapid)
    import time

    issued = int(time.time())
    header = webpush.vapid_authorization("https://push.example", private, now=issued)
    assert header.startswith("vapid t=")
    token, key = header[len("vapid t=") :].split(", k=")
    public = webpush.b64url_decode(key)
    assert len(public) == 65
    claims = jwt.decode(
        token,
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public),
        algorithms=["ES256"],
        audience="https://push.example",
    )
    assert claims["sub"] == "mailto:ops@example.com"
    assert claims["exp"] == issued + webpush.TOKEN_LIFETIME
    # The key in the header is the one the page subscribes with.
    assert key == webpush.public_key()


def test_keys_round_trip_through_their_text_form():
    private = webpush.generate_private_key()
    loaded = webpush.load_private_key(private)
    assert webpush.public_key_of(loaded) == webpush.public_key_of(webpush.load_private_key(private))
    pem = loaded.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    assert webpush.public_key_of(webpush.load_private_key(pem)) == webpush.public_key_of(loaded)
    for bad in ("", "not-base64!", webpush.b64url_encode(b"short")):
        with pytest.raises(webpush.WebPushError):
            webpush.load_private_key(bad)


def test_a_subscription_is_checked_before_it_is_kept():
    good = Browser("https://push.example/sub/1").subscription
    assert webpush.Subscription.parse(good).endpoint == good["endpoint"]
    assert webpush.Subscription.parse(json.dumps(good)).token() == webpush.Subscription.parse(good).token()
    for broken in (
        {**good, "endpoint": "http://push.example/plain"},
        {**good, "keys": {"p256dh": "AAAA", "auth": good["keys"]["auth"]}},
        {**good, "keys": {"p256dh": good["keys"]["p256dh"], "auth": "AAAA"}},
        "not json",
        [],
    ):
        with pytest.raises(webpush.WebPushError):
            webpush.Subscription.parse(broken)


# --- the portal ------------------------------------------------------------


def _portal(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Push Co", "is_active": True}).json()
    ana = client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@push.co", "password": "secure-portal"}).json()
    bea = client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Bea", "email": "bea@push.co", "password": "secure-portal"}).json()
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    return customer, agent, ana, bea


def _sign_in(client: TestClient, slug: str, email: str):
    assert client.post(f"/api/portal/{slug}/login", json={"email": email, "password": "secure-portal"}).status_code == 200


def test_the_portal_learns_whether_browsers_can_subscribe(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer, _agent, _ana, _bea = _portal(client)
    slug = customer["portal_slug"]
    _sign_in(client, slug, "ana@push.co")

    assert client.get(f"/api/portal/{slug}/push").json() == {"enabled": False, "public_key": ""}

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "push_webpush_private_key", webpush.generate_private_key(), raising=False)
    config = client.get(f"/api/portal/{slug}/push").json()
    assert config["enabled"] is True
    assert len(webpush.b64url_decode(config["public_key"])) == 65

    # A key that cannot be read leaves web push off rather than breaking the page.
    monkeypatch.setattr(get_settings(), "push_webpush_private_key", "garbage", raising=False)
    assert client.get(f"/api/portal/{slug}/push").json()["enabled"] is False


def test_a_browser_subscribes_once_follows_the_person_and_can_leave(authenticated_client: TestClient, vapid):
    client = authenticated_client
    customer, _agent, ana, bea = _portal(client)
    slug = customer["portal_slug"]
    browser = Browser("https://push.example/sub/ana")

    # Nobody signed in: the business itself cannot be rung.
    assert client.post(f"/api/portal/{slug}/push/subscriptions", json=browser.subscription).status_code == 401

    _sign_in(client, slug, "ana@push.co")
    first = client.post(f"/api/portal/{slug}/push/subscriptions", json=browser.subscription)
    assert first.status_code == 200 and first.json() == {"registered": True}
    # Every portal load registers again; that is one row, not many.
    assert client.post(f"/api/portal/{slug}/push/subscriptions", json=browser.subscription).status_code == 200
    with TestingSession() as db:
        rows = db.query(PushDevice).all()
        assert len(rows) == 1
        assert rows[0].provider == "webpush" and rows[0].platform == "web"
        assert str(rows[0].portal_user_id) == ana["id"]
        assert json.loads(rows[0].token)["endpoint"] == browser.endpoint

    # Bea signs in on the same browser: the subscription is hers now.
    _sign_in(client, slug, "bea@push.co")
    client.post(f"/api/portal/{slug}/push/subscriptions", json=browser.subscription)
    with TestingSession() as db:
        rows = db.query(PushDevice).all()
        assert len(rows) == 1 and str(rows[0].portal_user_id) == bea["id"]

    # A subscription the browser would reject is refused, not stored.
    bad = {**browser.subscription, "keys": {"p256dh": "AAAA", "auth": "AAAA"}}
    assert client.post(f"/api/portal/{slug}/push/subscriptions", json=bad).status_code == 422

    assert client.request("DELETE", f"/api/portal/{slug}/push/subscriptions", json={"endpoint": browser.endpoint}).status_code == 204
    with TestingSession() as db:
        assert db.query(PushDevice).count() == 0


# --- delivery --------------------------------------------------------------


def test_the_assignee_browser_is_rung_and_a_gone_one_is_forgotten(authenticated_client: TestClient, vapid, push_service):
    client = authenticated_client
    customer, agent, ana, _bea = _portal(client)
    slug = customer["portal_slug"]
    _sign_in(client, slug, "ana@push.co")
    laptop = Browser("https://push.example/sub/laptop")
    old_phone = Browser("https://push.example/gone/old-phone")
    for browser in (laptop, old_phone):
        assert client.post(f"/api/portal/{slug}/push/subscriptions", json=browser.subscription).status_code == 200
    conversation_id = customer_conversation(client, agent["id"])["id"]
    assert client.patch(f"/api/portal/{slug}/conversations/{conversation_id}/mode", json={"mode": "human"}).status_code == 200

    import asyncio

    with TestingSession() as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation.assignee_id is not None
        accepted = asyncio.run(notifications.notify_conversation(db, conversation, "¿Sigue disponible la mesa?", sender="Lucía"))
    assert accepted == 1
    assert len(push_service) == 2

    delivered = next(call for call in push_service if "/sub/laptop" in str(call.url))
    assert delivered.headers["content-encoding"] == "aes128gcm"
    assert delivered.headers["ttl"] == str(webpush.TTL_SECONDS)
    assert delivered.headers["authorization"].startswith("vapid t=")
    payload = json.loads(laptop.decrypt(delivered.content))
    assert payload["title"] == "Lucía"
    assert payload["body"] == "¿Sigue disponible la mesa?"
    assert payload["data"]["conversation_id"] == conversation_id
    assert payload["data"]["portal_slug"] == slug

    # The push service said the old phone's subscription is gone: dropped.
    with TestingSession() as db:
        tokens = [json.loads(row.token)["endpoint"] for row in db.query(PushDevice).all()]
    assert tokens == [laptop.endpoint]


def test_browsers_and_phones_each_reach_their_own_provider(authenticated_client: TestClient, vapid, push_service, monkeypatch):
    """A deployment that selects a mobile provider keeps it for phones; web
    rows never reach it, and its absence does not silence browsers."""
    seen: list[list[str]] = []

    async def fake_provider(notification):
        seen.append([device.token for device in notification.devices])
        return len(notification.devices)

    notifications.register_provider("fake", fake_provider)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "push_provider", "fake", raising=False)
    browser = Browser("https://push.example/sub/desk")
    devices = [
        notifications.Device(token=webpush.Subscription.parse(browser.subscription).token(), provider="webpush", platform="web"),
        notifications.Device(token="phone-token", provider="fake", platform="ios"),
    ]
    import asyncio

    sent = asyncio.run(notifications.notify_devices(notifications.Notification("t", "b", devices, {})))
    assert sent == 2
    assert seen == [["phone-token"]]
    assert [str(call.url) for call in push_service] == [browser.endpoint]
    notifications._PROVIDERS.pop("fake", None)


def test_the_mobile_app_is_not_told_push_is_on_when_only_browsers_are(authenticated_client: TestClient, vapid):
    client = authenticated_client
    _portal(client)
    session = client.post("/api/mobile/sign-in", json={"email": "ana@push.co", "password": "secure-portal"})
    assert session.status_code == 200
    # Web push is on, the mobile provider is not: the phone must not initialise anything.
    assert session.json()["push"] == {"enabled": False, "provider": "none"}
    assert notifications.push_enabled() is False
    assert notifications.webpush_enabled() is True
    assert notifications.any_push_enabled() is True
