import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Client, TemplateWebhook, User
from ..ratelimit import template_webhook_rate_limit
from ..schemas import (
    TemplateOut,
    TemplateWebhookCall,
    TemplateWebhookCreate,
    TemplateWebhookOut,
    TemplateWebhookResult,
    TemplateWebhookUpdate,
)
from ..services.template_webhooks import (
    approved_template, client_channel, deliver, new_secret, secret_matches, webhook_can_send, webhook_out,
)
from ..services.whatsapp_templates import list_templates, template_credentials
from .clients import _client


router = APIRouter(prefix="/clients/{client_id}/webhooks", tags=["Template webhooks"])
public_router = APIRouter(prefix="/public/hooks", tags=["Template webhooks public"])


def _webhook(db: Session, client: Client, webhook_id: uuid.UUID) -> TemplateWebhook:
    webhook = db.scalar(
        select(TemplateWebhook).where(TemplateWebhook.id == webhook_id, TemplateWebhook.client_id == client.id)
    )
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.get("", response_model=list[TemplateWebhookOut])
def list_webhooks(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    rows = db.scalars(
        select(TemplateWebhook).where(TemplateWebhook.client_id == client.id).order_by(TemplateWebhook.created_at)
    ).all()
    return [webhook_out(row) for row in rows]


@router.get("/templates", response_model=list[TemplateOut])
async def channel_templates(
    client_id: uuid.UUID, channel_id: uuid.UUID = Query(), db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """The approved utility templates of one number's business account: what a webhook on it can send."""
    client = _client(db, user, client_id)
    token, waba_id = template_credentials(db, client, client_channel(db, client, channel_id))
    return [template for template in await list_templates(token, waba_id) if webhook_can_send(template)]


@router.post("", response_model=TemplateWebhookOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    client_id: uuid.UUID, payload: TemplateWebhookCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    client = _client(db, user, client_id)
    channel = client_channel(db, client, payload.channel_id)
    language = payload.template_language.strip()
    await approved_template(db, client, channel, payload.template_name, language)
    webhook = TemplateWebhook(
        client_id=client.id,
        whatsapp_cloud_channel_id=channel.id,
        name=payload.name.strip(),
        template_name=payload.template_name,
        template_language=language,
    )
    secret = new_secret(webhook)
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return webhook_out(webhook, secret)


@router.post("/{webhook_id}/secret", response_model=TemplateWebhookOut)
def regenerate_secret(
    client_id: uuid.UUID, webhook_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Replace the secret. The one in use stops working with this call."""
    webhook = _webhook(db, _client(db, user, client_id), webhook_id)
    secret = new_secret(webhook)
    db.commit()
    db.refresh(webhook)
    return webhook_out(webhook, secret)


@router.patch("/{webhook_id}", response_model=TemplateWebhookOut)
async def update_webhook(
    client_id: uuid.UUID,
    webhook_id: uuid.UUID,
    payload: TemplateWebhookUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = _client(db, user, client_id)
    webhook = _webhook(db, client, webhook_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name"):
        webhook.name = changes["name"].strip()
    if changes.get("is_enabled") is not None:
        webhook.is_enabled = changes["is_enabled"]
    if any(changes.get(field) for field in ("channel_id", "template_name", "template_language")):
        channel = client_channel(db, client, changes.get("channel_id") or webhook.whatsapp_cloud_channel_id)
        name = changes.get("template_name") or webhook.template_name
        language = (changes.get("template_language") or webhook.template_language).strip()
        await approved_template(db, client, channel, name, language)
        webhook.whatsapp_cloud_channel_id = channel.id
        webhook.template_name = name
        webhook.template_language = language
    db.commit()
    db.refresh(webhook)
    return webhook_out(webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    client_id: uuid.UUID, webhook_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    client = _client(db, user, client_id)
    db.delete(_webhook(db, client, webhook_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.post("/{webhook_id}", response_model=TemplateWebhookResult, dependencies=[Depends(template_webhook_rate_limit)])
async def call_webhook(
    webhook_id: uuid.UUID,
    payload: TemplateWebhookCall,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Send the webhook's template to a phone. The caller proves itself with
    the webhook's secret as a bearer; the address alone sends nothing."""
    webhook = db.get(TemplateWebhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Unknown webhook")
    if not secret_matches(webhook, authorization):
        raise HTTPException(
            status_code=401,
            detail="Send this webhook's secret in the Authorization header, as a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await deliver(db, webhook, payload)
