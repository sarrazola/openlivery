"""Template webhooks: another system posts a phone and the values of a
template's variables, and the approved template goes out on the webhook's
WhatsApp API number.

The address identifies the webhook; the secret travels in the Authorization
header, so an address that leaks (a log, a screenshot) sends nothing.

The message is stored as the agent's, in the contact's open conversation or
in a new one, so when the contact answers the agent replies with it in its
history. A template is always what goes out, open reply window or not: the
caller gets one behaviour, and the template's buttons with it.
"""

import hashlib
import hmac
import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Client,
    Conversation,
    Message,
    TemplateWebhook,
    TemplateWebhookDelivery,
    WhatsAppCloudChannel,
    now_utc,
)
from ..schemas import TemplateWebhookCall
from .contacts import display_name, normalize_phone, resolve_contact
from .conversation_state import note_reply, record_activity
from .routing import route_new_conversation_by_tags
from .whatsapp_coexistence import lock_chats
from .whatsapp_templates import (
    list_templates,
    rendered_text,
    send_components,
    send_template,
    template_credentials,
)


SECRET_PREFIX = "whk_"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_secret(webhook: TemplateWebhook) -> str:
    """Give the webhook a fresh secret and return it. It is shown once: only
    its hash is stored, and the previous one stops working."""
    secret = SECRET_PREFIX + secrets.token_urlsafe(32)
    webhook.secret_hash = _hash(secret)
    webhook.secret_hint = secret[-6:]
    return secret


def secret_matches(webhook: TemplateWebhook, authorization: str | None) -> bool:
    scheme, _, presented = (authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer" or not presented.strip():
        return False
    return hmac.compare_digest(_hash(presented.strip()), webhook.secret_hash)


def webhook_out(webhook: TemplateWebhook, secret: str | None = None) -> dict:
    channel = webhook.channel
    return {
        "id": webhook.id,
        "name": webhook.name,
        "url": f"{get_settings().frontend_url.rstrip('/')}/api/public/hooks/{webhook.id}",
        "secret_hint": webhook.secret_hint,
        "secret": secret,
        "channel_id": channel.id,
        "channel_label": channel.label or channel.display_name or channel.phone_number or "",
        "agent_name": channel.agent.name,
        "template_name": webhook.template_name,
        "template_language": webhook.template_language,
        "is_enabled": webhook.is_enabled,
        "last_used_at": webhook.last_used_at,
        "created_at": webhook.created_at,
    }


def client_channel(db: Session, client: Client, channel_id: uuid.UUID) -> WhatsAppCloudChannel:
    channel = db.scalar(
        select(WhatsAppCloudChannel).where(
            WhatsAppCloudChannel.id == channel_id, WhatsAppCloudChannel.client_id == client.id
        )
    )
    if not channel:
        raise HTTPException(status_code=404, detail="That WhatsApp API number does not belong to this client")
    return channel


async def approved_template(db: Session, client: Client, channel: WhatsAppCloudChannel, name: str, language: str) -> tuple[dict, str]:
    """The template as the business account has it now, with the token to
    send it, or 409 when it is not approved in that language. Read on every
    send: a template can be paused or edited after the webhook was created."""
    token, waba_id = template_credentials(db, client, channel)
    found = next(
        (t for t in await list_templates(token, waba_id)
         if t["name"] == name and t["language"] == language and t["status"] == "APPROVED"),
        None,
    )
    if not found:
        raise HTTPException(status_code=409, detail="That template is not approved for this language")
    return found, token


def _body_values(template: dict, variables: dict) -> list[str]:
    """The caller's values in the order the template takes them."""
    given = {str(key): str(value).strip() for key, value in variables.items()}
    missing = [name for name in template["parameters"] if not given.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing template variables: {', '.join(missing)}")
    return [given[name] for name in template["parameters"]]


def _with_context(text: str, context: str) -> str:
    """What the model reads for the template: the text the contact got and the
    caller's notes, marked so the agent stands behind a message it did not write."""
    return (
        f"{text}\n\n[The business sent the message above through an automation. "
        f"Notes about it for you, not shown to the contact: {context}]"
    )


def _result(conversation: Conversation, message_id: uuid.UUID, *, started: bool, duplicate: bool = False, text: str = "") -> dict:
    return {
        "conversation_id": conversation.id,
        "message_id": message_id,
        "mode": conversation.mode,
        "started": started,
        "duplicate": duplicate,
        "text": text,
    }


def _earlier_delivery(db: Session, webhook: TemplateWebhook, key: str) -> dict | None:
    delivery = db.scalar(
        select(TemplateWebhookDelivery).where(
            TemplateWebhookDelivery.webhook_id == webhook.id, TemplateWebhookDelivery.idempotency_key == key
        )
    )
    if not delivery:
        return None
    message = db.get(Message, delivery.message_id)
    conversation = db.get(Conversation, delivery.conversation_id)
    return {
        "conversation_id": delivery.conversation_id,
        "message_id": delivery.message_id,
        "mode": conversation.mode if conversation else "ai",
        "started": False,
        "duplicate": True,
        "text": message.content if message else "",
    }


async def deliver(db: Session, webhook: TemplateWebhook, payload: TemplateWebhookCall) -> dict:
    channel, client = webhook.channel, webhook.client
    if not webhook.is_enabled:
        raise HTTPException(status_code=409, detail="This webhook is turned off")
    if not client.is_active:
        raise HTTPException(status_code=409, detail="This client is inactive")
    if not channel.is_enabled:
        raise HTTPException(status_code=409, detail="This webhook's WhatsApp API number is turned off")
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Send the phone number with its country code, digits only")
    key = payload.idempotency_key.strip()
    if key:
        earlier = _earlier_delivery(db, webhook, key)
        if earlier:
            return earlier

    template, access_token = await approved_template(db, client, channel, webhook.template_name, webhook.template_language)
    body_values = _body_values(template, payload.variables)
    components = send_components(
        template,
        body_values=body_values,
        header_value=payload.header,
        location=payload.location.model_dump() if payload.location else None,
        button_values=payload.buttons,
    )
    text = rendered_text(template, body_values=body_values, header_value=payload.header)

    # Two calls for the same phone wait for each other here, so they end up in
    # one conversation instead of opening two.
    lock_chats(db, channel.id, [phone])
    if key:
        earlier = _earlier_delivery(db, webhook, key)
        if earlier:
            return earlier
    contact = resolve_contact(db, client.id, phone=phone, name=payload.name.strip() or None)
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.whatsapp_cloud_channel_id == channel.id,
            or_(Conversation.external_chat_id == phone, Conversation.contact_id == contact.id),
            Conversation.status != "resolved",
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    started = conversation is None
    if started:
        conversation = Conversation(
            agency_id=channel.agency_id,
            client_id=client.id,
            agent_id=channel.agent_id,
            channel="whatsapp_cloud",
            whatsapp_cloud_channel_id=channel.id,
            external_chat_id=phone,
            contact_id=contact.id,
            contact_name=contact.name.strip()[:180] or None,
            title=display_name(contact)[:240],
        )
        db.add(conversation)
        db.flush()
        # A contact tagged for a team is answered by that team, as when they write first.
        route_new_conversation_by_tags(db, conversation, contact)
        record_activity(db, conversation, "started", actor=webhook.name)

    external_id = await send_template(
        access_token, channel.phone_number_id, phone,
        name=webhook.template_name, language=webhook.template_language, components=components,
    )
    context = payload.context.strip()
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=text,
        # The agent reads the caller's notes next to what the contact read.
        llm_content=_with_context(text, context) if context else None,
        sender_type="ai",
        sender_name=channel.agent.name,
        external_message_id=external_id,
    )
    db.add(message)
    db.flush()
    if started:
        note_reply(conversation)
    now = now_utc()
    conversation.updated_at = now
    webhook.last_used_at = now
    if key:
        db.add(TemplateWebhookDelivery(
            webhook_id=webhook.id, idempotency_key=key, conversation_id=conversation.id, message_id=message.id,
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        earlier = _earlier_delivery(db, webhook, key) if key else None
        if earlier:
            return earlier
        raise
    return _result(conversation, message.id, started=started, text=text)
