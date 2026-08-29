"""Message templates and the 24-hour reply window on the WhatsApp Cloud API.

Meta lets a business write to a person only inside 24 hours of that
person's last message. Outside that window the only thing that goes
through is a template Meta approved beforehand. Templates belong to the
business's WhatsApp account (the WABA), so they are read and created
there, never stored here: Meta's answer is the truth about their status.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import HTTPException

from ..models import now_utc
from .whatsapp_cloud import _graph_error, _graph_request, _graph_url


REPLY_WINDOW_HOURS = 24
TEMPLATE_CATEGORIES = ("UTILITY", "MARKETING")
_NAME = re.compile(r"^[a-z0-9_]{1,512}$")
_VARIABLE = re.compile(r"\{\{(\d+)\}\}")


def window_open_until(last_inbound_at: datetime | None) -> datetime | None:
    """When free-form replies stop being allowed, or None if the contact
    never wrote (then nothing but a template was ever allowed)."""
    if last_inbound_at is None:
        return None
    return last_inbound_at + timedelta(hours=REPLY_WINDOW_HOURS)


def window_is_open(last_inbound_at: datetime | None) -> bool:
    until = window_open_until(last_inbound_at)
    return bool(until and until > now_utc())


def variable_count(body: str) -> int:
    numbers = [int(n) for n in _VARIABLE.findall(body or "")]
    return max(numbers) if numbers else 0


def validate_template_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME.match(name):
        raise HTTPException(status_code=422, detail="Template names use lowercase letters, digits and underscores only")
    return name


def normalize(raw: dict) -> dict:
    """The parts of a Meta template the portal shows and sends."""
    body = footer = ""
    for component in raw.get("components") or []:
        kind = (component.get("type") or "").upper()
        if kind == "BODY":
            body = component.get("text") or ""
        elif kind == "FOOTER":
            footer = component.get("text") or ""
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or "",
        "language": raw.get("language") or "",
        "category": (raw.get("category") or "").upper(),
        "status": (raw.get("status") or "").upper(),
        "body": body,
        "footer": footer,
        "variables": variable_count(body),
        "rejected_reason": raw.get("rejected_reason") or None,
    }


def render(body: str, variables: list[str]) -> str:
    """The text the person will read, with the variables filled in."""
    def fill(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        return variables[index] if 0 <= index < len(variables) else match.group(0)
    return _VARIABLE.sub(fill, body or "")


async def list_templates(access_token: str, waba_id: str) -> list[dict]:
    response = await _graph_request(
        "GET",
        _graph_url(f"{waba_id}/message_templates?fields=id,name,status,category,language,components,rejected_reason&limit=200"),
        access_token,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Could not read the templates: {_graph_error(response)}")
    try:
        data = response.json().get("data") or []
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid response from the Meta API.") from exc
    return [normalize(item) for item in data]


async def create_template(
    access_token: str,
    waba_id: str,
    *,
    name: str,
    language: str,
    category: str,
    body: str,
    footer: str = "",
    examples: list[str] | None = None,
) -> dict:
    """Submit a template for approval. Meta wants an example value for every
    variable, so it can judge the message as a person would read it."""
    count = variable_count(body)
    examples = [e for e in (examples or []) if e.strip()]
    if count and len(examples) != count:
        raise HTTPException(status_code=422, detail=f"Give one example for each of the {count} variables")
    body_component: dict = {"type": "BODY", "text": body}
    if count:
        body_component["example"] = {"body_text": [examples]}
    components = [body_component]
    if footer.strip():
        components.append({"type": "FOOTER", "text": footer.strip()})
    payload = {"name": name, "language": language, "category": category, "components": components}
    response = await _graph_request("POST", _graph_url(f"{waba_id}/message_templates"), access_token, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Meta did not accept the template: {_graph_error(response)}")
    try:
        created = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid response from the Meta API.") from exc
    return normalize({**payload, "id": created.get("id"), "status": created.get("status") or "PENDING"})


async def send_template(
    access_token: str, phone_number_id: str, to: str, *, name: str, language: str, variables: list[str]
) -> str | None:
    template: dict = {"name": name, "language": {"code": language}}
    if variables:
        template["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": value} for value in variables]}
        ]
    payload = {"messaging_product": "whatsapp", "to": to, "type": "template", "template": template}
    response = await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"WhatsApp could not send the template: {_graph_error(response)}")
    try:
        messages = response.json().get("messages") or []
        return messages[0].get("id") if messages else None
    except ValueError:
        return None
