"""Web Push for the portal, with nothing but the browser's own protocol.

A browser hands the portal a *subscription*: an endpoint at the browser
vendor's push service plus two keys the page cannot read. The server posts an
encrypted message to that endpoint, signed with a key pair the deployment owns
(VAPID), and the browser's service worker shows it, with the portal closed and
the browser open. No account with anyone, no SDK on the page, no vendor named
here: this is RFC 8030 (the protocol), RFC 8291 (the encryption) and RFC 8292
(the signature), which every push service implements.

What this module holds:

* :func:`encrypt` and :func:`vapid_authorization`: the two pieces of the
  protocol that are easy to get subtly wrong, kept small and tested.
* :func:`deliver`: one notification to many subscriptions, dropping the ones
  the push service reports gone (the person revoked permission or the browser
  was reset), so the registry heals itself.

The key pair is created once with ``python -m app.webpush_keys`` and lives in
``PUSH_WEBPUSH_PRIVATE_KEY``; the public half is derived from it and handed to
the page so the browser can subscribe. The mobile seam in
:mod:`app.services.notifications` is untouched: a web subscription is one more
row in the device registry, with ``provider`` set to :data:`PROVIDER`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings

logger = logging.getLogger(__name__)

# The provider name a web subscription is registered under. Separate from
# PUSH_PROVIDER on purpose: a deployment can run a mobile provider and web push
# side by side, each reaching its own rows.
PROVIDER = "webpush"
PLATFORM = "web"

TIMEOUT_SECONDS = 5.0
# How long the push service keeps an undelivered message. A browser that was
# closed for the night should still show the morning's messages.
TTL_SECONDS = 24 * 3600
# RFC 8188 record size; one record carries our whole payload.
RECORD_SIZE = 4096
# Plaintext ceiling well under the record (16 bytes of tag, 1 of padding) and
# under the 4 KiB push services accept.
MAX_PLAINTEXT = 3800
# A VAPID token is good for at most 24 hours; shorter leaves room for clocks.
TOKEN_LIFETIME = 12 * 3600


class WebPushError(ValueError):
    """A subscription or key that cannot be used."""


def b64url_decode(value: str) -> bytes:
    text = value.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


@dataclass(frozen=True)
class Subscription:
    """What the browser's ``PushSubscription.toJSON()`` gives, validated."""

    endpoint: str
    p256dh: str
    auth: str

    @classmethod
    def parse(cls, raw: Any) -> "Subscription":
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError as exc:
                raise WebPushError("subscription is not JSON") from exc
        if not isinstance(raw, dict):
            raise WebPushError("subscription must be an object")
        endpoint = str(raw.get("endpoint") or "").strip()
        keys = raw.get("keys") or {}
        p256dh = str(keys.get("p256dh") or "").strip()
        auth = str(keys.get("auth") or "").strip()
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise WebPushError("subscription endpoint must be an https URL")
        try:
            if len(b64url_decode(p256dh)) != 65 or len(b64url_decode(auth)) != 16:
                raise WebPushError("subscription keys have the wrong size")
        except (ValueError, TypeError) as exc:
            raise WebPushError("subscription keys are not base64url") from exc
        return cls(endpoint=endpoint, p256dh=p256dh, auth=auth)

    def token(self) -> str:
        """The registry row's token: the subscription, canonically serialised,
        so the same browser registering twice hits the same row."""
        return json.dumps(
            {"endpoint": self.endpoint, "keys": {"auth": self.auth, "p256dh": self.p256dh}},
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.endpoint)
        return f"{parsed.scheme}://{parsed.netloc}"


# --- keys ------------------------------------------------------------------


def generate_private_key() -> str:
    """A fresh VAPID private key, as the base64url of its 32-byte scalar: the
    form every web push tool exchanges, so one key can move between them."""
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    return b64url_encode(raw)


def load_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    """Accept the base64url scalar or a PEM, since both are in circulation."""
    text = (value or "").strip()
    if not text:
        raise WebPushError("no private key")
    if text.startswith("-----BEGIN"):
        key = serialization.load_pem_private_key(text.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise WebPushError("the private key is not an EC key")
        return key
    try:
        raw = b64url_decode(text)
    except (ValueError, TypeError) as exc:
        raise WebPushError("the private key is not base64url") from exc
    if len(raw) != 32:
        raise WebPushError("the private key must be 32 bytes")
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def public_key_of(private_key: ec.EllipticCurvePrivateKey) -> str:
    """The uncompressed point, base64url: what ``applicationServerKey`` takes."""
    point = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url_encode(point)


def configured_private_key() -> ec.EllipticCurvePrivateKey | None:
    value = (getattr(get_settings(), "push_webpush_private_key", "") or "").strip()
    if not value:
        return None
    try:
        return load_private_key(value)
    except WebPushError as exc:
        logger.warning("PUSH_WEBPUSH_PRIVATE_KEY is unusable, web push is off: %s", exc)
        return None


def enabled() -> bool:
    return configured_private_key() is not None


def public_key() -> str:
    """The key the portal subscribes with, or empty when web push is off."""
    key = configured_private_key()
    return public_key_of(key) if key else ""


def subject() -> str:
    """Who the push service may contact about this sender (RFC 8292 ``sub``)."""
    value = (getattr(get_settings(), "push_webpush_subject", "") or "").strip()
    return value or "mailto:admin@localhost"


# --- the protocol ----------------------------------------------------------


def encrypt(plaintext: bytes, subscription: Subscription) -> bytes:
    """RFC 8291 ``aes128gcm`` content encoding, one record."""
    if len(plaintext) > MAX_PLAINTEXT:
        raise WebPushError("payload too large for one push message")
    ua_public = b64url_decode(subscription.p256dh)
    auth_secret = b64url_decode(subscription.auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public = as_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    shared = as_private.exchange(ec.ECDH(), ua_key)
    ikm = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=auth_secret, info=b"WebPush: info\x00" + ua_public + as_public
    ).derive(shared)
    salt = os.urandom(16)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
    # 0x02 marks the last record; no padding beyond it.
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_authorization(endpoint_origin: str, private_key: ec.EllipticCurvePrivateKey, *, now: float | None = None) -> str:
    """The ``Authorization: vapid`` header value for one push service."""
    issued = int(now if now is not None else time.time())
    claims = {"aud": endpoint_origin, "exp": issued + TOKEN_LIFETIME, "sub": subject()}
    token = jwt.encode(claims, private_key, algorithm="ES256")
    return f"vapid t={token}, k={public_key_of(private_key)}"


def request_for(subscription: Subscription, payload: dict[str, Any], private_key: ec.EllipticCurvePrivateKey) -> tuple[dict[str, str], bytes]:
    """Headers and body of the POST that delivers ``payload`` to one browser."""
    body = encrypt(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), subscription)
    headers = {
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "high",
        "Authorization": vapid_authorization(subscription.origin, private_key),
    }
    return headers, body


# A push service's verdict on one subscription.
DELIVERED = "delivered"
GONE = "gone"
FAILED = "failed"


async def send_one(http: httpx.AsyncClient, subscription: Subscription, payload: dict[str, Any], private_key: ec.EllipticCurvePrivateKey) -> str:
    headers, body = request_for(subscription, payload, private_key)
    try:
        response = await http.post(subscription.endpoint, headers=headers, content=body)
    except httpx.HTTPError as exc:
        logger.warning("web push: %s unreachable: %s", subscription.origin, exc)
        return FAILED
    if response.status_code in (200, 201, 202):
        return DELIVERED
    # 404 and 410 are the push service saying this subscription no longer
    # exists: permission revoked, browser reset, or the service rotated it.
    if response.status_code in (404, 410):
        return GONE
    logger.warning("web push rejected (%s) by %s: %s", response.status_code, subscription.origin, response.text[:200])
    return FAILED


async def deliver(payload: dict[str, Any], tokens: list[str], db=None) -> tuple[int, list[str]]:
    """Send ``payload`` to every subscription in ``tokens``.

    Returns how many were accepted and the tokens the push service declared
    gone. When ``db`` is given those rows are deleted here, so a revoked
    browser stops being tried on every message.
    """
    private_key = configured_private_key()
    if private_key is None or not tokens:
        return 0, []
    accepted = 0
    gone: list[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
        for token in tokens:
            try:
                subscription = Subscription.parse(token)
            except WebPushError as exc:
                logger.warning("web push: skipping a malformed subscription: %s", exc)
                gone.append(token)
                continue
            verdict = await send_one(http, subscription, payload, private_key)
            if verdict == DELIVERED:
                accepted += 1
            elif verdict == GONE:
                gone.append(token)
    if gone and db is not None:
        forget(db, gone)
    return accepted, gone


def forget(db, tokens: list[str]) -> None:
    """Delete registry rows for subscriptions that no longer exist."""
    from sqlalchemy import delete

    from ..models import PushDevice

    try:
        db.execute(delete(PushDevice).where(PushDevice.token.in_(tokens)))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - housekeeping must not break delivery
        logger.warning("web push: could not drop gone subscriptions: %s", exc)
        db.rollback()
