"""Contact details an agent collects in conversation.

A client defines custom contact fields once (``ContactField``); every agent of
that client can then ask for any of them, and for the built-in name, email and
phone, on the channels it chooses (``AgentCaptureField``). At reply time the
prompt lists what is still unknown about the contact with the operator's
instruction for each field, and the model saves what the customer said through
the ``save_contact_field`` tool. The handler only validates and records; the
values are written to the contact after the generation loop, like escalation.

What is saved lands on the contact, so the next conversation with that person
lists it under "Contact" and the agent does not ask again.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, AgentCaptureField, Contact, ContactField, Conversation, now_utc
from .contacts import find_contact, normalize_phone, rename_conversations
from .tools.specs import ToolSpec

FIELD_KINDS = ("text", "number", "email", "phone")
FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,59}$"
_FIELD_KEY_RE = re.compile(FIELD_KEY_PATTERN)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_VALUE_CHARS = 500

# Channel groups an agent can limit a field to. Both WhatsApp lines are one
# choice to the operator; the playground rehearses every field.
CAPTURE_CHANNELS = ("whatsapp", "instagram", "messenger", "widget")
_CHANNEL_GROUP = {"whatsapp": "whatsapp", "whatsapp_cloud": "whatsapp", "instagram": "instagram", "messenger": "messenger", "widget": "widget"}

TOOL_NAME = "save_contact_field"

# Built-in fields live in their own contact columns and exist for every client.
BUILTIN_FIELDS = {
    "name": {"kind": "text", "label": {"es": "Nombre", "en": "Name"}},
    "email": {"kind": "email", "label": {"es": "Correo", "en": "Email"}},
    "phone": {"kind": "phone", "label": {"es": "Teléfono", "en": "Phone"}},
}

_TEXT = {
    "es": {
        "title": "Datos por capturar",
        "rule": (
            "Estos datos del contacto aún no se conocen. Pregúntalos con naturalidad dentro de la conversación, "
            "de uno en uno y en el momento que indica cada instrucción, nunca como un formulario. Cuando el cliente "
            "dé uno, guárdalo de inmediato con la herramienta save_contact_field, tal como lo dijo, y sigue con la "
            "conversación. Nunca inventes ni deduzcas un valor: solo guarda lo que el cliente dijo explícitamente."
        ),
    },
    "en": {
        "title": "Details to collect",
        "rule": (
            "These contact details are not known yet. Ask for them naturally within the conversation, one at a "
            "time and when each instruction says, never as a form. When the customer gives one, save it right away "
            "with the save_contact_field tool, as they said it, and carry on. Never invent or infer a value: only "
            "save what the customer stated explicitly."
        ),
    },
}


@dataclass
class FieldDefinition:
    key: str
    label: str
    kind: str
    description: str = ""
    builtin: bool = False


@dataclass
class CapturedValue:
    key: str
    value: str


def valid_key(key: str) -> bool:
    return bool(_FIELD_KEY_RE.match(key or ""))


def channel_group(channel: str | None) -> str | None:
    return _CHANNEL_GROUP.get(channel or "")


def field_definitions(db: Session, client_id, lang: str = "es") -> dict[str, FieldDefinition]:
    """Every field a contact of this client can hold, built-ins first."""
    lang = lang if lang in ("es", "en") else "es"
    definitions = {
        key: FieldDefinition(key=key, label=spec["label"][lang], kind=spec["kind"], builtin=True)
        for key, spec in BUILTIN_FIELDS.items()
    }
    rows = db.scalars(select(ContactField).where(ContactField.client_id == client_id).order_by(ContactField.position, ContactField.created_at))
    for row in rows:
        definitions[row.key] = FieldDefinition(key=row.key, label=row.label, kind=row.kind, description=row.description)
    return definitions


def contact_value(contact: Contact | None, key: str) -> str | None:
    """What the contact already holds for a field, None when nothing."""
    if contact is None:
        return None
    if key == "name":
        return (contact.name or "").strip() or (contact.whatsapp_contact_name or "").strip() or None
    if key == "email":
        return (contact.email or "").strip() or None
    if key == "phone":
        return contact.phone or None
    value = (contact.attributes or {}).get(key)
    return str(value).strip() or None if value is not None else None


def active_capture_fields(agent: Agent, channel: str | None) -> list[AgentCaptureField]:
    """The agent's capture rows that apply on this channel. The playground has
    no channel group and rehearses them all."""
    if not agent.capture_enabled:
        return []
    group = channel_group(channel)
    return [
        row for row in agent.capture_fields
        if not row.channels or group is None or group in row.channels
    ]


def missing_fields(
    agent: Agent, conversation: Conversation, definitions: dict[str, FieldDefinition]
) -> list[tuple[AgentCaptureField, FieldDefinition]]:
    contact = getattr(conversation, "contact", None)
    pending = []
    for row in active_capture_fields(agent, getattr(conversation, "channel", None)):
        definition = definitions.get(row.field_key)
        if definition is None or contact_value(contact, row.field_key):
            continue
        pending.append((row, definition))
    return pending


def capture_context(
    agent: Agent, conversation: Conversation, definitions: dict[str, FieldDefinition], lang: str | None = None
) -> str:
    """The prompt section listing what is still unknown, with the operator's
    instruction per field. Empty when nothing is pending."""
    pending = missing_fields(agent, conversation, definitions)
    if not pending:
        return ""
    lang = lang if lang in _TEXT else "es"
    text = _TEXT[lang]
    lines = []
    for row, definition in pending:
        line = f"- **{definition.label}** (`{definition.key}`)"
        detail = " ".join(part.strip() for part in (definition.description, row.instruction) if part and part.strip())
        if detail:
            line += f": {detail}"
        lines.append(line)
    return f"## {text['title']}\n" + "\n".join(lines) + "\n\n" + text["rule"]


def validate_value(kind: str, raw: str) -> tuple[str | None, str | None]:
    """The value as it will be stored, or the reason it cannot be."""
    value = " ".join(str(raw or "").split())[:MAX_VALUE_CHARS]
    if not value:
        return None, "The value is empty."
    if kind == "email":
        value = value.lower()
        if not _EMAIL_RE.match(value):
            return None, "That is not a valid email address; ask the customer to confirm it."
    elif kind == "phone":
        digits = normalize_phone(value)
        if not digits:
            return None, "That is not a valid phone number; ask for it with the country code."
        value = digits
    elif kind == "number":
        try:
            float(value.replace(",", "."))
        except ValueError:
            return None, "That is not a number."
    return value, None


def build_capture_spec(
    agent: Agent, conversation: Conversation, definitions: dict[str, FieldDefinition], holder: list[CapturedValue]
) -> ToolSpec | None:
    """The ``save_contact_field`` tool, offered only while something is pending.
    Its handler validates the value by kind and records it in ``holder``;
    ``apply_captures`` writes it once the reply is generated."""
    pending = missing_fields(agent, conversation, definitions)
    if not pending:
        return None
    allowed = {definition.key: definition for _, definition in pending}

    def handler(args: dict) -> tuple[str, bool]:
        key = str(args.get("field") or "").strip()
        definition = allowed.get(key)
        if definition is None:
            return f"Unknown field. Save one of: {', '.join(allowed)}.", True
        value, problem = validate_value(definition.kind, str(args.get("value") or ""))
        if problem:
            return problem, True
        holder[:] = [item for item in holder if item.key != key]
        holder.append(CapturedValue(key=key, value=value))
        return f"Saved {key}. Continue the conversation without repeating it back unnecessarily.", False

    return ToolSpec(
        name=TOOL_NAME,
        description=(
            "Save a detail the customer just gave about themselves on their contact record. "
            "Call it once per detail, only with what the customer stated explicitly."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": list(allowed), "description": "Which detail"},
                "value": {"type": "string", "description": "The value as the customer said it"},
            },
            "required": ["field", "value"],
        },
        handler=handler,
    )


def apply_captures(
    db: Session, conversation: Conversation, holder: list[CapturedValue], definitions: dict[str, FieldDefinition]
) -> list[str]:
    """Write what the model recorded onto the conversation's contact. Returns
    the keys that were saved. A phone another contact already holds is left
    alone: merging people is a decision for the portal."""
    contact = getattr(conversation, "contact", None)
    if contact is None or not holder:
        return []
    saved: list[str] = []
    for item in holder:
        definition = definitions.get(item.key)
        if definition is None:
            continue
        if item.key == "name":
            contact.name = item.value[:180]
            rename_conversations(db, contact)
        elif item.key == "email":
            contact.email = item.value[:255]
        elif item.key == "phone":
            if contact.phone:
                continue
            other = find_contact(db, contact.client_id, item.value)
            if other is not None and other.id != contact.id:
                continue
            contact.phone = item.value[:40]
        else:
            contact.attributes = {**(contact.attributes or {}), item.key: item.value}
        saved.append(item.key)
    if saved:
        contact.updated_at = now_utc()
    return saved
