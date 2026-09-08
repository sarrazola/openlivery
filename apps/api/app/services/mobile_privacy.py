"""Client-scoped processing destinations, without reading provider secrets."""

import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, AgentTool, Client, SocialChannel, WhatsAppChannel, WhatsAppCloudChannel
from . import notifications, providers


class PrivacyDestination(BaseModel):
    kind: Literal["ai", "integration", "notification"]
    name: str
    host: str
    capabilities: list[str]


class MobilePrivacy(BaseModel):
    version: str
    destinations: list[PrivacyDestination]


def destination_host(url: str) -> str:
    """Expose a destination, never a credential, path, parameter or fragment."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https"):
            return ""
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def provider_destination(db: Session, agency_id, provider: str) -> tuple[str, str]:
    """Deployment seam for compatible endpoints. Configuration is not readiness."""
    config = providers.PROVIDERS.get(provider)
    if not config:
        return provider, ""
    return config["label"], destination_host(config["base_url"])


def notification_destination() -> tuple[str, str]:
    provider = notifications.configured_provider()
    if provider == "webhook":
        return "Notification service", destination_host(get_settings().push_webhook_url)
    return provider, ""


def integration_destination(tool_type: str, url: str) -> tuple[str, str]:
    return "MCP service" if tool_type == "mcp" else "Connected service", destination_host(url)


def disclosure(db: Session, client: Client) -> MobilePrivacy:
    destinations: dict[tuple[str, str, str], set[str]] = {}

    def add(kind: str, name: str, host: str, capabilities: list[str]) -> None:
        destinations.setdefault((kind, name, host), set()).update(capabilities)

    # An inactive agent may still process media for an existing conversation.
    agents = db.execute(select(
        Agent.id, Agent.provider, Agent.image_enabled, Agent.audio_enabled,
    ).where(Agent.client_id == client.id)).all()
    for agent in agents:
        name, host = provider_destination(db, client.agency_id, agent.provider)
        add("ai", name, host, ["conversation"])
        media = [capability for capability, enabled in (
            ("image", agent.image_enabled), ("audio", agent.audio_enabled),
        ) if enabled]
        if media:
            name, host = provider_destination(db, client.agency_id, "openai")
            add("ai", name, host, media)
    for tool_type, url in db.execute(
        select(AgentTool.type, AgentTool.url).join(Agent, Agent.id == AgentTool.agent_id)
        .where(Agent.client_id == client.id, AgentTool.enabled.is_(True))
    ):
        name, host = integration_destination(tool_type, url)
        add("integration", name, host, ["integration"])
    if db.scalar(select(WhatsAppChannel.id).where(WhatsAppChannel.client_id == client.id, WhatsAppChannel.is_enabled.is_(True))):
        add("integration", "WhatsApp", "whatsapp.com", ["messages", "uploads"])
    if db.scalar(select(WhatsAppCloudChannel.id).where(WhatsAppCloudChannel.client_id == client.id, WhatsAppCloudChannel.is_enabled.is_(True))):
        add("integration", "WhatsApp", "graph.facebook.com", ["messages", "uploads"])
    for provider in db.scalars(select(SocialChannel.provider).where(SocialChannel.client_id == client.id, SocialChannel.is_enabled.is_(True))):
        add("integration", "Instagram" if provider == "instagram" else "Messenger", "graph.facebook.com", ["messages", "uploads"])
    if notifications.push_enabled():
        name, host = notification_destination()
        add("notification", name, host, ["notifications"])
    rows = [PrivacyDestination(kind=kind, name=name, host=host, capabilities=sorted(capabilities))
            for (kind, name, host), capabilities in sorted(destinations.items())]
    canonical = json.dumps([row.model_dump() for row in rows], sort_keys=True, separators=(",", ":"))
    revision = hashlib.sha256(canonical.encode()).hexdigest()
    return MobilePrivacy(version=f"1:{revision}", destinations=rows)
