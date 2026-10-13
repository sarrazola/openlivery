"""Notifying the people who answer, without picking a provider for you.

The mobile app exists so a phone rings when the assistant escalates. How that
push is actually delivered is an operational choice, not something this project
should decide for its operators, so this module is a seam rather than an
integration:

* ``PushDevice`` rows say *where* to reach an install.
* A provider is one function that takes a :class:`Notification` and delivers it.
* ``PUSH_PROVIDER`` selects one. The default is ``none`` — a self-hosted
  OpenLivery sends nothing, needs no account anywhere, and costs nothing.

Two providers ship here because neither ties you to a company:

``none``      Do nothing. The default.
``webhook``   POST the event as JSON to ``PUSH_WEBHOOK_URL``. Point it at ntfy,
              Gotify, a queue, Home Assistant, or a five-line script that calls
              whatever service you already pay for.

Browsers are a third channel that needs no provider at all: the portal
subscribes with the Web Push protocol and the server delivers to the browser's
own push service, signed with a key pair the deployment owns
(``PUSH_WEBPUSH_PRIVATE_KEY``; see :mod:`app.services.webpush`). Those rows
sit in the same registry under the provider ``webpush`` and are delivered
alongside whatever ``PUSH_PROVIDER`` selects, so a deployment can notify phones
through one and browsers through the other.

Anything else is ~20 lines: write the function, call :func:`register_provider`
at startup. A deployment that adds one does it from outside this repository,
which is why no vendor is named in here.

A note worth knowing before you plan around this: on iOS and Android the push
credentials are bound to the app binary, so a server can only notify an app that
was built against its provider. The store build only accepts notifications sent
with the credentials it was signed with, which belong to whoever published it;
to get push on your own server you rebuild the app under your own identifiers
(see apps/mobile/WHITELABEL.md) and register the matching provider here.

Delivery is best-effort by design. The message is already stored and will be
there when the app next opens, so a failed notification must never fail the
request that produced it: every error is logged and swallowed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Client, Conversation, PortalUser, PushDevice
from . import webpush

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
# A banner on a lock screen is a summary, not the message.
PREVIEW_CHARS = 140


@dataclass
class Device:
    """One install to notify, detached from the ORM so providers stay simple."""

    token: str
    provider: str = ""
    platform: str = ""
    portal_user_id: Any = None


@dataclass
class Notification:
    """What happened, in the shape a provider needs to deliver it."""

    title: str
    body: str
    devices: list[Device]
    # Enough for the app to open straight into the right conversation.
    data: dict[str, Any] = field(default_factory=dict)


# A provider returns how many devices it accepted; 0 means nothing was sent.
Provider = Callable[[Notification], Awaitable[int]]

_PROVIDERS: dict[str, Provider] = {}


def register_provider(name: str, provider: Provider) -> None:
    """Make ``name`` selectable through ``PUSH_PROVIDER``.

    Re-registering a name replaces it, which is what lets a deployment override
    a built-in without editing this file.
    """
    _PROVIDERS[name.strip().lower()] = provider


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def configured_provider() -> str:
    """The provider this deployment selected, or ``none``.

    An unknown name is treated as ``none`` and logged: a typo in the environment
    should leave notifications off, not crash a request that was only trying to
    store a message.
    """
    name = (getattr(get_settings(), "push_provider", "") or "none").strip().lower()
    if name not in _PROVIDERS:
        if name != "none":
            logger.warning("PUSH_PROVIDER=%r is not registered; notifications are off", name)
        return "none"
    return name


def push_enabled() -> bool:
    """A provider for the mobile apps is selected."""
    return configured_provider() != "none"


def webpush_enabled() -> bool:
    """Browsers can be notified: a VAPID key is configured."""
    return webpush.enabled()


def any_push_enabled() -> bool:
    return push_enabled() or webpush_enabled()


async def _send_none(_notification: Notification) -> int:
    return 0


async def _send_webhook(notification: Notification) -> int:
    """POST the event to an operator-chosen URL and let them route it.

    The payload is deliberately plain and stable: title, body, the device tokens
    it concerns, and the ids needed to deep-link.
    """
    url = (getattr(get_settings(), "push_webhook_url", "") or "").strip()
    if not url:
        logger.warning("PUSH_PROVIDER=webhook but PUSH_WEBHOOK_URL is empty")
        return 0
    payload = {
        "title": notification.title,
        "body": notification.body,
        "data": notification.data,
        "devices": [
            {"token": device.token, "platform": device.platform} for device in notification.devices
        ],
    }
    headers = {"Content-Type": "application/json"}
    secret = (getattr(get_settings(), "push_webhook_secret", "") or "").strip()
    if secret:
        # A shared secret so the receiver can tell it is really us.
        headers["Authorization"] = f"Bearer {secret}"
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
        response = await http.post(url, json=payload, headers=headers)
    if response.status_code >= 400:
        logger.warning("push webhook rejected (%s): %s", response.status_code, response.text[:300])
        return 0
    return len(notification.devices)


register_provider("none", _send_none)
register_provider("webhook", _send_webhook)


# What to call a conversation whose visitor never gave a name. A web visitor is
# anonymous, and heading the notification with their first message reads like an
# old message arriving again.
_CHANNEL_LABELS = {
    "widget": "Web chat",
    "whatsapp": "WhatsApp",
    "whatsapp_cloud": "WhatsApp",
}


def _channel_label(channel: str | None) -> str:
    return _CHANNEL_LABELS.get(channel or "", "New message")


def devices_for_client(db: Session, client_id) -> list[Device]:
    """Installs to notify for a client, ignoring ones from another provider.

    Rows keep the provider that issued their token. After a deployment switches
    providers the old tokens are meaningless, so they are skipped until those
    apps register again rather than being sent somewhere they cannot arrive.
    """
    active = configured_provider()
    web = webpush_enabled()
    rows = db.scalars(select(PushDevice).where(PushDevice.client_id == client_id)).all()
    return [
        Device(token=row.token, provider=row.provider, platform=row.platform, portal_user_id=row.portal_user_id)
        for row in rows
        if row.token
        and ((row.provider == webpush.PROVIDER and web) or (row.provider != webpush.PROVIDER and (not row.provider or row.provider == active)))
    ]


def _portal_slug(db: Session, client_id) -> str:
    client = db.get(Client, client_id)
    return client.portal_slug if client else ""


def summarize(body: str) -> str:
    text = " ".join((body or "").split())
    if len(text) > PREVIEW_CHARS:
        return f"{text[:PREVIEW_CHARS].rstrip()}…"
    return text


async def notify_devices(notification: Notification, db: Session | None = None) -> int:
    """Hand a notification to whoever reaches each device. Never raises.

    Browser subscriptions go straight to their push service; everything else
    goes to the configured provider. ``db`` lets a subscription the push
    service declared gone be dropped from the registry on the spot.
    """
    if not notification.devices:
        return 0
    browsers = [d for d in notification.devices if d.provider == webpush.PROVIDER]
    others = [d for d in notification.devices if d.provider != webpush.PROVIDER]
    sent = 0
    if browsers and webpush_enabled():
        payload = {"title": notification.title, "body": notification.body, "data": notification.data}
        try:
            accepted, _gone = await webpush.deliver(payload, [d.token for d in browsers], db)
            sent += accepted
        except Exception as exc:  # noqa: BLE001 - delivery must never break the caller
            logger.warning("web push delivery failed: %s", exc)
    if others:
        provider = _PROVIDERS[configured_provider()]
        try:
            sent += await provider(Notification(notification.title, notification.body, others, notification.data))
        except Exception as exc:  # noqa: BLE001 - delivery must never break the caller
            logger.warning("push delivery failed: %s", exc)
    return sent


async def notify_conversation(
    db: Session,
    conversation: Conversation,
    body: str,
    *,
    title: str | None = None,
    sender: str | None = None,
    member_ids: set | None = None,
) -> int:
    """Ring the installs registered for this conversation's client.

    ``member_ids`` narrows the fan-out to a team: the conversation landed in
    a tray with nobody assigned, so that tray's people ring, not everyone.
    Falls back to everyone when none of them has a device.
    """
    if not any_push_enabled():
        return 0
    devices = devices_for_client(db, conversation.client_id)
    if conversation.assignee_id:
        # Someone owns this conversation: their phone rings, not everyone's.
        mine = [d for d in devices if d.portal_user_id == conversation.assignee_id]
        devices = mine or devices
    elif member_ids:
        team_devices = [d for d in devices if d.portal_user_id in member_ids]
        devices = team_devices or devices
    if not devices:
        return 0
    if title is None:
        title = sender or conversation.contact_name or _channel_label(conversation.channel)
    return await notify_devices(
        Notification(
            title=title,
            body=summarize(body) or "New message",
            devices=devices,
            data={
                "conversation_id": str(conversation.id),
                "client_id": str(conversation.client_id),
                "portal_slug": _portal_slug(db, conversation.client_id),
            },
        ),
        db,
    )


async def notify_assigned(db: Session, conversation: Conversation, assignee: PortalUser, by: str) -> int:
    """Tell the person a conversation was just handed to them."""
    if not any_push_enabled():
        return 0
    devices = [d for d in devices_for_client(db, conversation.client_id) if d.portal_user_id == assignee.id]
    if not devices:
        return 0
    return await notify_devices(
        Notification(
            title=conversation.title,
            body=f"{by} assigned you this conversation",
            devices=devices,
            data={
                "conversation_id": str(conversation.id),
                "client_id": str(conversation.client_id),
                "portal_slug": _portal_slug(db, conversation.client_id),
            },
        ),
        db,
    )


async def notify_needs_human(db: Session, conversation: Conversation, body: str, *, team=None) -> int:
    """Notify only when a person is the one expected to answer.

    While the assistant is handling a conversation there is nothing for anyone
    to do, and a phone that buzzes on every customer message is a phone whose
    notifications get switched off. When the conversation sits unassigned in a
    tray, that tray's members are the ones who ring.
    """
    if conversation.mode != "human":
        return 0
    member_ids = {member.portal_user_id for member in team.members} if team is not None else None
    return await notify_conversation(
        db, conversation, body, sender=conversation.contact_name or None, member_ids=member_ids
    )
