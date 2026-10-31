"""Phone calls answered by an agent.

ElevenLabs answers the number and runs the call: it hears the caller, decides
when they finished or cut in, thinks with one of its own models and speaks.
OpenLivery writes what the agent knows into the ElevenLabs agent of each line
(its business, offer, rules and the phone rules, its greeting, voice and
tools) and writes it again whenever the agent changes, so a turn never waits
on us. During a call ElevenLabs calls back twice: when the call comes in, for
who is calling (the contact, what is still to ask, their last case), and for
each tool the agent uses (the documents, saving a detail, handing over to a
person, the agent's own tools). When the call ends ElevenLabs reports it, and
it becomes a conversation on the ``phone`` channel with its transcript,
closed unless a person has it.
"""

import asyncio
import contextvars
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Literal

import anyio.from_thread
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import new_session
from ..models import Agent, AgentTool, CallAccount, Conversation, Message, PhoneCall, PhoneChannel, now_utc
from ..security import decrypt_secret, encrypt_secret
from . import contacts
from .capture import CapturedValue, FieldDefinition, apply_captures, build_capture_spec, capture_context, field_definitions
from .conversation_state import set_status
from .escalation import EscalationRequest, active_rules, apply_escalation, build_escalation_spec, escalation_enabled, escalation_prompt
from .knowledge import build_knowledge, build_system_prompt, contact_context, retrieve_knowledge
from .routing import route_new_conversation_by_tags
from .ai import Completion
from .telephony import TelephonyError, carriers, elevenlabs
from .tools.loop import execute_spec
from .tools.runner import TOOL_FAILURE_RULE
from .tools.specs import ToolSpec, build_tool_specs, find_spec
from .usage import record_usage

logger = logging.getLogger(__name__)

PROVIDERS = ("elevenlabs", *carriers.CARRIERS)
CHANNEL = "phone"
SIGNATURE_TOLERANCE_SECONDS = 30 * 60

# The models a voice agent thinks with, all run by ElevenLabs next to the
# voice. The Realtime ones are built for conversation and answer fastest; the
# others run in ElevenLabs' custom mode.
VOICE_MODELS = {
    "eleven_realtime_v1_mini": "Realtime Mini",
    "eleven_realtime_v1_max": "Realtime Max",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
}
DEFAULT_VOICE_MODEL = "eleven_realtime_v1_mini"
REALTIME_MODELS = {"eleven_realtime_v1_mini", "eleven_realtime_v1_max"}
# A Realtime agent ignores its LLM but ElevenLabs refuses one set to its own
# custom LLM (as lines connected before Realtime are), so it is named, and
# the custom LLM's settings are cleared: an update merges into what is there.
REALTIME_IDLE_LLM = "gemini-3.8-flash"

PHONE_RULES = {
    "es": (
        "LLAMADA TELEFÓNICA: estás hablando por teléfono, no escribiendo.\n"
        "- Responde con frases cortas para decir en voz alta, una o dos por turno. Sin listas, markdown, emojis ni enlaces.\n"
        "- Di los números como se dicen; los teléfonos y códigos, de a un dígito.\n"
        "- Pide los datos de a uno y no vuelvas a pedir uno que ya te dieron.\n"
        "- Antes de registrar o agendar algo con datos del cliente, repíteselos y espera a que confirme.\n"
        "- Si no entiendes una parte, pregunta solo esa parte.\n"
        "- Cuando el cliente se despida o no necesite nada más, despídete en una frase y usa end_call.\n"
    ),
    "en": (
        "PHONE CALL: you are speaking on the phone, not writing.\n"
        "- Answer in short sentences meant to be said aloud, one or two per turn. No lists, markdown, emojis or links.\n"
        "- Say numbers the way people say them; phone numbers and codes digit by digit.\n"
        "- Ask for details one at a time and never ask again for one already given.\n"
        "- Before booking or recording anything with the caller's details, read them back and wait for a yes.\n"
        "- If you miss part of what was said, ask only for that part.\n"
        "- When the caller says goodbye or needs nothing else, say goodbye in one sentence and use end_call.\n"
    ),
}
TRANSFER_RULE = {
    "es": "- Si el cliente necesita a una persona, avísale en una frase que lo vas a comunicar y usa transfer_to_number.\n",
    "en": "- If the caller needs a person, tell them in one sentence that you are putting them through and use transfer_to_number.\n",
}
CALLBACK_RULE = {
    "es": "- En una llamada no hay a quién pasar al cliente: si escalas, dile que una persona lo va a contactar.\n",
    "en": "- On a call there is nobody to put the caller through to: when you escalate, tell them a person will get back to them.\n",
}
KNOWLEDGE_RULE = {
    "es": "- Para precios, servicios, horarios o políticas que no estén arriba, consulta search_knowledge antes de responder; si no aparece, dilo y no lo inventes.\n",
    "en": "- For prices, services, hours or policies not written above, look them up with search_knowledge before answering; if they are not there, say so and do not invent them.\n",
}


# The voice of an agent that has not picked one: a conversational voice from
# the ElevenLabs library in the agent's language, among the most used there.
DEFAULT_VOICES = {
    "es": "YExhVa4bZONzeingloMX",   # Juan Carlos, Latin American Spanish
    "en": "UgBBYS2sOqTuMpoF3BR0",   # Mark, American English
}


def voice_of(agent: Agent) -> str:
    return agent.voice_id.strip() or DEFAULT_VOICES[_language(agent)]


# When the caller is put through, unless the agent says otherwise.
TRANSFER_WHEN = {
    "es": "Cuando el cliente pide hablar con una persona o necesita algo que no puedes resolver.",
    "en": "When the caller asks for a person or needs something you cannot resolve.",
}
# Who is calling, filled in by ElevenLabs on every call. What OpenLivery knows
# about them arrives in two dynamic variables when the call comes in: the
# contact and their last case, and the details still to ask for.
CALLER_VAR = "caller_context"
PENDING_VAR = "pending_details"
CALLER = {
    "es": "## Quien llama\n- **Teléfono desde el que llama:** {{system__caller_id}}\n\n{{" + CALLER_VAR + "}}",
    "en": "## Caller\n- **Calling from:** {{system__caller_id}}\n\n{{" + CALLER_VAR + "}}",
}

# Every tool of a line carries these, filled in by ElevenLabs and never by
# the model: which call it is and who is calling.
CALL_ARG = "openlivery_call_id"
CALLER_ARG = "openlivery_caller"
# The header ElevenLabs sends on every callback, with the account's secret.
TOKEN_HEADER = "X-OpenLivery-Token"
# Documents up to this size ride in the line's prompt; past it the agent looks
# them up, so a call does not carry a long document on every turn.
CALL_KNOWLEDGE_IN_PROMPT = 16_000
KNOWLEDGE_TOOL = "search_knowledge"


class PhoneSetupError(RuntimeError):
    """Something the operator has to fix before a line can take calls."""


def check_voice_model(model: str) -> None:
    if model not in VOICE_MODELS:
        raise ValueError(f"A voice agent thinks with one of: {', '.join(VOICE_MODELS.values())}.")


def transfer_number(value: str | None) -> str | None:
    """The number a call is put through to, in E.164; None leaves the caller
    to be called back."""
    if not value or not value.strip():
        return None
    digits = contacts.normalize_phone(value)
    if not digits:
        raise ValueError("Write the transfer number with its country code, for example +573001234567.")
    return f"+{digits}"


# --- accounts ----------------------------------------------------------------

# A deployment may lend an account to an agency that stored none of its own (a
# shared ElevenLabs workspace, say). It registers one function at startup; the
# function is asked only when the agency has no account of its own for that
# provider, and returns the account's secret as it would be stored
# (``{"api_key": ...}`` for ElevenLabs) or None.
CallAccountFallback = Callable[[Session, Any, str], "dict | None"]
_account_fallback: CallAccountFallback | None = None
AccountSource = Literal["agency", "deployment", "none"]


def register_call_account_fallback(fallback: CallAccountFallback | None) -> None:
    """Install what answers when an agency has no account of its own; None removes it."""
    global _account_fallback
    _account_fallback = fallback


def _own(account: CallAccount | None) -> bool:
    return account is not None and account.enabled and bool(account.encrypted_secret)


def _lent(db: Session, agency_id, provider: str) -> dict | None:
    return _account_fallback(db, agency_id, provider) if _account_fallback is not None else None


def account_source(db: Session, agency_id, provider: str) -> AccountSource:
    if _own(get_account(db, agency_id, provider)):
        return "agency"
    return "deployment" if _lent(db, agency_id, provider) else "none"


def get_account(db: Session, agency_id, provider: str) -> CallAccount | None:
    return db.scalar(select(CallAccount).where(CallAccount.agency_id == agency_id, CallAccount.provider == provider))


def account_secret(account: CallAccount) -> dict:
    return json.loads(decrypt_secret(account.encrypted_secret))


def secret_hint(provider: str, secret: dict) -> str:
    if provider == "twilio":
        sid = secret.get("account_sid", "")
        return f"{sid[:6]}…{sid[-4:]}" if sid else ""
    key = secret.get("api_key", "")
    return f"…{key[-4:]}" if key else ""


def clean_secret(provider: str, values: dict) -> dict:
    if provider == "twilio":
        secret = {"account_sid": str(values.get("account_sid") or "").strip(), "auth_token": str(values.get("auth_token") or "").strip()}
        if not secret["account_sid"].startswith("AC") or not secret["auth_token"]:
            raise PhoneSetupError("Enter the Account SID (it starts with AC) and the Auth Token from the Twilio console.")
        return secret
    key = str(values.get("api_key") or "").strip()
    if not key:
        raise PhoneSetupError("Enter the API key.")
    return {"api_key": key}


async def validate_account(provider: str, secret: dict) -> str:
    if provider == "elevenlabs":
        return await elevenlabs.validate_key(secret["api_key"])
    return await carriers.validate(provider, secret)


def store_account(db: Session, agency_id, provider: str, secret: dict) -> CallAccount:
    account = get_account(db, agency_id, provider)
    if account is None:
        account = CallAccount(agency_id=agency_id, provider=provider, encrypted_secret="")
        db.add(account)
    elif not account.encrypted_secret:
        # The row held a lent account's webhook and callback secret, which
        # live in the lender's workspace: the agency's own one gets its own.
        account.webhook_id = None
        account.encrypted_webhook_secret = None
        account.webhook_url = None
        account.tool_secret_id = None
        account.tool_token_hash = None
    account.encrypted_secret = encrypt_secret(json.dumps(secret))
    account.secret_hint = secret_hint(provider, secret)
    account.enabled = True
    account.last_error = None
    return account


def account_out(db: Session, agency_id, provider: str) -> dict:
    account = get_account(db, agency_id, provider)
    stored = account is not None and bool(account.encrypted_secret)
    source = account_source(db, agency_id, provider)
    return {
        "provider": provider,
        "configured": source != "none",
        "stored": stored,
        "source": source,
        "secret_hint": account.secret_hint if stored else "",
        "last_error": account.last_error if stored else None,
    }


def elevenlabs_key(db: Session, agency_id) -> tuple[CallAccount, str]:
    """The ElevenLabs key calls use, and the agency's row that keeps its
    webhook: the agency's own key, else the one the deployment lends."""
    account = get_account(db, agency_id, "elevenlabs")
    if _own(account):
        return account, account_secret(account)["api_key"]
    lent = _lent(db, agency_id, "elevenlabs")
    if not lent:
        raise PhoneSetupError("Add the ElevenLabs API key in Settings first.")
    if account is None:
        account = CallAccount(agency_id=agency_id, provider="elevenlabs", encrypted_secret="", secret_hint="")
        db.add(account)
        db.flush()
    return account, lent["api_key"]


def carrier_secret(db: Session, agency_id, provider: str) -> dict:
    account = get_account(db, agency_id, provider)
    if _own(account):
        return account_secret(account)
    lent = _lent(db, agency_id, provider)
    if not lent:
        raise PhoneSetupError(f"Connect the {provider.title()} account in Settings first.")
    return lent


# --- where ElevenLabs calls back -----------------------------------------------

# ElevenLabs reaches the deployment at PHONE_PUBLIC_URL (or FRONTEND_URL). A
# deployment that serves each agency on its own address registers one
# function at startup returning the base URL for an agency, or None to use
# the configured one.
PublicBase = Callable[[Session, Any], "str | None"]
_public_base: PublicBase | None = None


def register_public_base(resolver: PublicBase | None) -> None:
    """Install what says where an agency's callbacks arrive; None removes it."""
    global _public_base
    _public_base = resolver


def public_base(db: Session, agency_id) -> str:
    base = _public_base(db, agency_id) if _public_base is not None else None
    if not base:
        settings = get_settings()
        base = settings.phone_public_url or settings.frontend_url
    return base.rstrip("/")


def webhook_url(db: Session, account: CallAccount) -> str:
    return f"{public_base(db, account.agency_id)}/api/public/phone/accounts/{account.public_id}/webhook"


def line_url(db: Session, line: PhoneChannel, path: str) -> str:
    return f"{public_base(db, line.agency_id)}/api/public/phone/lines/{line.public_id}/{path}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _callback_secret(db: Session, account: CallAccount, api_key: str) -> str:
    """The workspace secret ElevenLabs sends on the line's callbacks, created
    once per account. OpenLivery keeps only its hash."""
    if account.tool_secret_id and account.tool_token_hash:
        return account.tool_secret_id
    token = secrets.token_urlsafe(32)
    account.tool_secret_id = await elevenlabs.create_secret(api_key, f"openlivery_{secrets.token_hex(6)}", token)
    account.tool_token_hash = _token_hash(token)
    db.commit()
    return account.tool_secret_id


def callback_authorized(db: Session, line: PhoneChannel, token: str | None) -> bool:
    account = get_account(db, line.agency_id, "elevenlabs")
    if not token or account is None or not account.tool_token_hash:
        return False
    return hmac.compare_digest(account.tool_token_hash, _token_hash(token))


def _headers(secret_id: str) -> dict:
    return {TOKEN_HEADER: {"secret_id": secret_id}}


# --- lines -------------------------------------------------------------------


def _language(agent: Agent) -> str:
    return agent.prompt_language if agent.prompt_language in PHONE_RULES else "es"


# A reply that takes longer than this gets a short sound from the voice, so
# the caller hears the line is alive. Only a slow turn (a tool, a long
# answer) gets there; a phrase like "one moment" in front of a normal reply
# sounded random on calls, so it is a neutral sound, once.
FILLER_AFTER_SECONDS = 3.0
FILLERS = {"es": "Mmm...", "en": "Hmm..."}
# Twilio and SIP carry the call as 8 kHz mu-law: the voice hears and speaks
# it as is, instead of converting on every turn.
PHONE_AUDIO = "ulaw_8000"


def _turn_settings(lang: str) -> dict:
    """How the voice takes turns: it starts on the reply while the caller is
    still silent, before it is sure they finished, and fills a long wait
    instead of going quiet."""
    return {
        "speculative_turn": True,
        "soft_timeout_config": {
            "timeout_seconds": FILLER_AFTER_SECONDS,
            "message": FILLERS[lang],
            "max_soft_timeouts_per_generation": 1,
            "disable_until_first_user_message": True,
        },
    }


# --- what the agent can do on a call -------------------------------------------


@dataclass
class CallTools:
    """The tools a line's agent has on a call. Running one fills ``captured``
    or ``escalation`` for the call's conversation, as in a chat reply."""

    specs: list[ToolSpec]
    definitions: dict[str, FieldDefinition]
    captured: list[CapturedValue] = field(default_factory=list)
    escalation: list[EscalationRequest] = field(default_factory=list)
    escalation_rules: list = field(default_factory=list)


# The capture tool asks for every detail the agent collects on calls, known
# or not: the line's tools are written ahead of any call, and a caller may
# correct what is on file. What is still missing for this caller arrives with
# the call (``start_call``).
_ANY_CALLER = SimpleNamespace(contact=None, channel="phone")


def _documents(agent: Agent) -> list:
    return [doc for doc in agent.documents if doc.status == "processed" and doc.extracted_text.strip()]


def _knowledge_searched(agent: Agent) -> bool:
    return sum(len(doc.extracted_text) for doc in _documents(agent)) > CALL_KNOWLEDGE_IN_PROMPT


def _prompt_knowledge(agent: Agent) -> str:
    """The documents, when they are short enough to ride in the prompt."""
    if _knowledge_searched(agent):
        return ""
    return build_knowledge(agent, _documents(agent), "", full_up_to=CALL_KNOWLEDGE_IN_PROMPT).text


def call_tools(db: Session, line: PhoneChannel) -> CallTools:
    agent = line.agent
    tools = CallTools(specs=[], definitions=field_definitions(db, line.client_id, _language(agent)))
    if _knowledge_searched(agent):
        tools.specs.append(ToolSpec(
            name=KNOWLEDGE_TOOL,
            description="Look up the business's documents: prices, services, hours, policies and anything else not in your instructions.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look up, in a few words"}},
                "required": ["query"],
            },
        ))
    capture = build_capture_spec(agent, _ANY_CALLER, tools.definitions, tools.captured)
    if capture:
        tools.specs.append(capture)
    if not agent.transfer_number:
        # With a number to put the caller through to, a person takes the call
        # there; without one, the case goes to a person to call back. Unlike
        # a chat, that holds with no team to route it to: the case is still
        # left open for whoever answers the inbox.
        rules = active_rules(db, agent)
        if agent.escalation_builtin_enabled or escalation_enabled(db, agent, rules):
            tools.escalation_rules = rules
            tools.specs.append(build_escalation_spec(rules, tools.escalation, builtin_enabled=agent.escalation_builtin_enabled))
    rows = db.scalars(select(AgentTool).where(AgentTool.agent_id == agent.id, AgentTool.enabled.is_(True))).all()
    tools.specs.extend(build_tool_specs(list(rows)))
    return tools


def _schema_property(schema: dict, name: str) -> dict:
    """A JSON schema property as ElevenLabs takes it: text, a number, an
    integer or a boolean with a description, a list with its items, or an
    object with its properties. What it cannot express (a union, a free-form
    object) is asked for as text, and ``_decoded`` reads it back."""
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "string")
    description = str(schema.get("description") or schema.get("title") or name.replace("_", " ")).strip()[:500]
    if kind == "object" and isinstance(schema.get("properties"), dict) and schema["properties"]:
        return {**_object_schema(schema), "description": description}
    if kind == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {"type": "string"}
        return {"type": "array", "description": description, "items": _schema_property(items, name)}
    if kind not in ("string", "number", "integer", "boolean"):
        return {"type": "string", "description": f"{description} (as JSON)" if kind in ("object", "array") else description}
    prop: dict = {"type": kind, "description": description}
    enum = schema.get("enum")
    if kind == "string" and isinstance(enum, list) and enum and all(isinstance(value, str) for value in enum):
        prop["enum"] = enum
    return prop


def _object_schema(schema: dict) -> dict:
    properties = {
        key: _schema_property(value if isinstance(value, dict) else {}, key)
        for key, value in (schema.get("properties") or {}).items()
    }
    return {
        "type": "object",
        "properties": properties,
        "required": [key for key in schema.get("required") or [] if key in properties],
    }


def _decoded(spec: ToolSpec, args: dict) -> dict:
    """Arguments asked for as text but meant as an object or a list, parsed."""
    properties = (spec.input_schema or {}).get("properties") or {}
    decoded = dict(args)
    for key, value in args.items():
        kind = (properties.get(key) or {}).get("type")
        if isinstance(value, str) and kind in ("object", "array"):
            try:
                decoded[key] = json.loads(value)
            except ValueError:
                pass
    return decoded


def _tool_timeout(spec: ToolSpec) -> int:
    seconds = spec.tool.timeout_seconds + 5 if spec.tool is not None and spec.tool.type == "http" else 30
    return max(5, min(int(seconds), 120)) if spec.tool is not None else 15


def _tool_config(db: Session, line: PhoneChannel, spec: ToolSpec, secret_id: str) -> dict:
    """A webhook tool of the line: ElevenLabs posts the model's arguments,
    plus the call and the caller, to OpenLivery, which runs it."""
    body = _object_schema(spec.input_schema or {})
    body["properties"][CALL_ARG] = {"type": "string", "dynamic_variable": "system__conversation_id"}
    body["properties"][CALLER_ARG] = {"type": "string", "dynamic_variable": "system__caller_id"}
    return {
        "type": "webhook",
        "name": spec.name,
        "description": spec.description[:2000],
        "response_timeout_secs": _tool_timeout(spec),
        # The voice says something natural while a slow tool runs.
        "pre_tool_speech": "auto",
        "api_schema": {
            "url": line_url(db, line, f"tools/{spec.name}"),
            "method": "POST",
            "request_headers": _headers(secret_id),
            "request_body_schema": body,
        },
    }


async def _sync_tools(db: Session, line: PhoneChannel, api_key: str, secret_id: str) -> tuple[list[str], list[str]]:
    """Write the line's tools into ElevenLabs, skipping the unchanged ones.
    Returns the tool ids the agent uses and the ones it no longer does."""
    known = dict(line.elevenlabs_tools or {})
    kept: dict = {}
    for spec in call_tools(db, line).specs:
        config = _tool_config(db, line, spec, secret_id)
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        previous = known.pop(spec.name, None) or {}
        if previous.get("id") and previous.get("hash") == digest:
            kept[spec.name] = previous
            continue
        kept[spec.name] = {"id": await elevenlabs.upsert_tool(api_key, previous.get("id"), config), "hash": digest}
        line.elevenlabs_tools = {**kept, **known}
        db.commit()
    line.elevenlabs_tools = kept
    return [item["id"] for item in kept.values()], [item["id"] for item in known.values() if item.get("id")]


def call_prompt(db: Session, line: PhoneChannel, tools: CallTools | None = None) -> str:
    """What the line's ElevenLabs agent is told: the agent's prompt as the
    chat builds it (with the documents when they are short), who is calling,
    how to speak on the phone and how to use its tools. What is still to ask
    the caller is a variable filled in when the call comes in. The date and
    time are left to ElevenLabs, which adds them on every call in the
    client's timezone; written here they would be the moment of the sync."""
    agent = line.agent
    lang = _language(agent)
    tools = tools or call_tools(db, line)
    names = {spec.name for spec in tools.specs}
    rules = PHONE_RULES[lang]
    if agent.transfer_number:
        rules += TRANSFER_RULE[lang]
    elif "escalate_to_human" in names:
        rules += CALLBACK_RULE[lang]
    if KNOWLEDGE_TOOL in names:
        rules += KNOWLEDGE_RULE[lang]
    parts = [
        build_system_prompt(agent, _prompt_knowledge(agent), "{{" + PENDING_VAR + "}}", with_time=False),
        CALLER[lang],
        rules.rstrip(),
    ]
    if "escalate_to_human" in names:
        parts.append(escalation_prompt(tools.escalation_rules, builtin_enabled=agent.escalation_builtin_enabled))
    if tools.specs:
        parts.append(TOOL_FAILURE_RULE)
    return "\n\n".join(parts)


def _agent_body(db: Session, line: PhoneChannel, webhook_id: str | None, secret_id: str, tool_ids: list[str]) -> dict:
    agent = line.agent
    lang = _language(agent)
    tools: dict = {"end_call": {"type": "system", "name": "end_call", "description": "", "params": {"system_tool_type": "end_call"}}}
    if agent.transfer_number:
        tools["transfer_to_number"] = {
            "type": "system",
            "name": "transfer_to_number",
            "description": "Put the caller through to a person of the business.",
            "params": {
                "system_tool_type": "transfer_to_number",
                "transfers": [{
                    "transfer_destination": {"type": "phone", "phone_number": agent.transfer_number},
                    "condition": agent.transfer_when.strip() or TRANSFER_WHEN[lang],
                    "transfer_type": "conference",
                }],
            },
        }
    model = agent.model.strip()
    prompt: dict = {
        "prompt": call_prompt(db, line), "built_in_tools": tools, "tool_ids": tool_ids,
        "timezone": agent.client.timezone or "UTC",
        "llm": REALTIME_IDLE_LLM if model in REALTIME_MODELS else model, "custom_llm": None,
    }
    workspace_overrides: dict = {
        # Asked when a call comes in, before the greeting: who is calling.
        "conversation_initiation_client_data_webhook": {"url": line_url(db, line, "start"), "request_headers": _headers(secret_id)},
    }
    if webhook_id:
        workspace_overrides["webhooks"] = {"post_call_webhook_id": webhook_id, "events": elevenlabs.WEBHOOK_EVENTS}
    return {
        "name": f"{line.client.name} · {line.label or line.phone_number}"[:120],
        "conversation_config": {
            # Realtime replaces the LLM, speech and turn models with its own;
            # null hands the agent back to the ones set here.
            "realtime_model": model if model in REALTIME_MODELS else None,
            "asr": {"user_input_audio_format": PHONE_AUDIO},
            "tts": {"voice_id": voice_of(agent), "agent_output_audio_format": PHONE_AUDIO},
            "turn": _turn_settings(lang),
            "agent": {
                "first_message": agent.greeting, "language": lang, "prompt": prompt,
                # What a call that never asked us who is calling (a SIP call,
                # a test from the ElevenLabs dashboard) reads in their place.
                "dynamic_variables": {"dynamic_variable_placeholders": {CALLER_VAR: "", PENDING_VAR: ""}},
            },
        },
        "platform_settings": {
            "overrides": {"enable_conversation_initiation_client_data_from_webhook": True},
            "workspace_overrides": workspace_overrides,
            # The call's summary in the agent's language: left to ElevenLabs it
            # came in English on calls held in Spanish.
            "summary_language": lang,
        },
    }


async def connect_line(db: Session, line: PhoneChannel) -> None:
    """Set the line up at ElevenLabs and point its number there. Safe to run
    again: it updates what exists, which is how a change to the agent reaches
    its lines. Raises PhoneSetupError or TelephonyError; the caller stores the
    message on the line."""
    account, api_key = elevenlabs_key(db, line.agency_id)
    carrier = carrier_secret(db, line.agency_id, line.provider)
    agent = line.agent
    if agent.kind != "voice":
        raise PhoneSetupError("A phone line is answered by a voice agent. Choose one, or create one.")
    if agent.model.strip() not in VOICE_MODELS:
        raise PhoneSetupError("Choose the agent's voice model: " + ", ".join(VOICE_MODELS.values()) + ".")
    name = await elevenlabs.ensure_voice(api_key, voice_of(agent))
    if agent.voice_id:
        agent.voice_name = name or agent.voice_name
    url = webhook_url(db, account)
    if not account.webhook_id or account.webhook_url != url:
        moved = account.webhook_id is not None
        webhook_id, signing = await elevenlabs.create_webhook(api_key, "OpenLivery calls", url)
        account.webhook_id = webhook_id
        account.webhook_url = url
        account.encrypted_webhook_secret = encrypt_secret(signing) if signing else None
        db.commit()
        if moved:
            # The agency's other lines still report to the old webhook, whose
            # signature no longer checks: they take the new one in a moment.
            # The old webhook is left in place, unused.
            others = select(PhoneChannel.agent_id).where(
                PhoneChannel.agency_id == line.agency_id, PhoneChannel.agent_id != line.agent_id,
                PhoneChannel.is_enabled.is_(True), PhoneChannel.status == "connected",
            )
            for agent_id in set(db.scalars(others).all()):
                _schedule_resync(agent_id)
    secret_id = await _callback_secret(db, account, api_key)
    tool_ids, unused = await _sync_tools(db, line, api_key, secret_id)
    try:
        line.elevenlabs_agent_id = await elevenlabs.upsert_agent(
            api_key, line.elevenlabs_agent_id, _agent_body(db, line, account.webhook_id, secret_id, tool_ids)
        )
    except TelephonyError:
        # A tool ElevenLabs no longer has would refuse the agent on every
        # retry while its hash says it is up to date: write them all again.
        line.elevenlabs_tools = {name: {"id": item.get("id")} for name, item in (line.elevenlabs_tools or {}).items()}
        db.commit()
        raise
    db.commit()
    for tool_id in unused:
        try:
            await elevenlabs.delete_tool(api_key, tool_id)
        except TelephonyError:
            pass
    label = f"{line.client.name} · {line.label or line.phone_number}"[:60]
    if line.elevenlabs_phone_number_id:
        await elevenlabs.assign_number(api_key, line.elevenlabs_phone_number_id, line.elevenlabs_agent_id)
    elif line.provider == "twilio":
        line.elevenlabs_phone_number_id = await elevenlabs.import_twilio_number(
            api_key, phone_number=line.phone_number, label=label, sid=carrier["account_sid"],
            token=carrier["auth_token"], agent_id=line.elevenlabs_agent_id,
        )
    else:
        sip = await carriers.telnyx_route_to_elevenlabs(carrier, line.provider_number_id or "", label)
        line.elevenlabs_phone_number_id = await elevenlabs.import_sip_number(
            api_key, phone_number=line.phone_number, label=label, inbound=sip["inbound"], outbound=sip["outbound"],
            agent_id=line.elevenlabs_agent_id,
        )
    line.status = "connected"
    line.last_error = None
    line.last_connected_at = now_utc()
    db.commit()


# What a line's ElevenLabs agent carries from the agent and from its client:
# a change to any of them is written again into every connected line.
AGENT_LINE_FIELDS = {
    "name", "voice_id", "greeting", "model", "prompt_language", "instructions", "personality", "transfer_number", "transfer_when",
    "brief_summary", "brief_products", "brief_audience", "brief_policies", "brief_dos", "brief_donts",
}
CLIENT_LINE_FIELDS = {"name", "industry", "business_type", "business_custom", "timezone"}


def _connected(query, *, agent_id=None, client_id=None):
    query = query.where(PhoneChannel.is_enabled.is_(True), PhoneChannel.status == "connected")
    if agent_id is not None:
        query = query.where(PhoneChannel.agent_id == agent_id)
    if client_id is not None:
        query = query.where(PhoneChannel.client_id == client_id)
    return query


async def resync_lines(db: Session, *, agent_id=None, client_id=None) -> None:
    """Write the agent again into its connected lines; one that cannot take
    it keeps the error to show."""
    for line in db.scalars(_connected(select(PhoneChannel), agent_id=agent_id, client_id=client_id)).all():
        try:
            await connect_line(db, line)
        except (PhoneSetupError, TelephonyError) as exc:
            db.rollback()
            line.status = "error"
            line.last_error = str(exc)
            db.commit()


# The rest of what a line carries (its documents and questions, its tools,
# the details it collects, who it hands over to) is edited across many
# endpoints, some of them in a burst (an import, a list replaced item by
# item). Those only note the change; the lines are written a moment later,
# once, from a task with its own session.
RESYNC_DELAY_SECONDS = 2.0
_pending_resyncs: dict = {}


def refresh_lines_soon(db: Session, *, agent_id=None, client_id=None) -> None:
    """Schedule the agent's connected lines (or the client's) to be written
    again. Works from async and threadpool endpoints; a no-op without lines."""
    for line_agent_id in set(db.scalars(_connected(select(PhoneChannel.agent_id), agent_id=agent_id, client_id=client_id)).all()):
        _schedule_resync(line_agent_id)


def _schedule_resync(agent_id) -> None:
    # The task runs in the caller's context, so whatever the request selected
    # through context variables (a database schema, say) holds there too.
    context = contextvars.copy_context()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = anyio.from_thread.run_sync(asyncio.get_running_loop)
        except RuntimeError:
            return  # no event loop at all (a script): nothing to schedule on
    loop.call_soon_threadsafe(_debounce_resync, loop, agent_id, context)


def _debounce_resync(loop: asyncio.AbstractEventLoop, agent_id, context: contextvars.Context) -> None:
    previous = _pending_resyncs.pop(agent_id, None)
    if previous is not None:
        previous.cancel()
    _pending_resyncs[agent_id] = loop.call_later(RESYNC_DELAY_SECONDS, _start_resync, loop, agent_id, context=context)


def _start_resync(loop: asyncio.AbstractEventLoop, agent_id) -> None:
    _pending_resyncs.pop(agent_id, None)
    loop.create_task(_resync_agent(agent_id))


async def _resync_agent(agent_id) -> None:
    db = new_session()
    try:
        await resync_lines(db, agent_id=agent_id)
    except Exception:
        logger.exception("Could not write the phone lines of agent %s", agent_id)
    finally:
        db.close()


async def disconnect_line(db: Session, line: PhoneChannel) -> None:
    """Take the number and the agent out of ElevenLabs. Best effort on each
    step: whatever is already gone does not stop the rest."""
    try:
        _, api_key = elevenlabs_key(db, line.agency_id)
    except PhoneSetupError:
        api_key = None
    if api_key:
        steps = []
        if line.elevenlabs_phone_number_id:
            steps.append(elevenlabs.release_number(api_key, line.elevenlabs_phone_number_id))
        if line.elevenlabs_agent_id:
            steps.append(elevenlabs.delete_agent(api_key, line.elevenlabs_agent_id))
        steps.extend(elevenlabs.delete_tool(api_key, item["id"]) for item in (line.elevenlabs_tools or {}).values() if item.get("id"))
        for step in steps:
            try:
                await step
            except TelephonyError:
                pass
    line.elevenlabs_phone_number_id = None
    line.elevenlabs_agent_id = None
    line.elevenlabs_tools = {}
    line.status = "disconnected"
    db.commit()


def line_out(line: PhoneChannel) -> dict:
    return {
        "id": line.id,
        "client_id": line.client_id,
        "agent_id": line.agent_id,
        "label": line.label,
        "phone_number": line.phone_number,
        "provider": line.provider,
        "provider_number_id": line.provider_number_id,
        "status": line.status,
        "is_enabled": line.is_enabled,
        "last_error": line.last_error,
        "last_connected_at": line.last_connected_at,
        "created_at": line.created_at,
        "updated_at": line.updated_at,
    }


# --- during a call ----------------------------------------------------------------


def _known(value) -> str | None:
    value = str(value or "").strip()
    return None if value in ("", "None", "null", "undefined") else value


def _open_call(db: Session, line: PhoneChannel, call_id: str, caller: str | None) -> Conversation:
    """The call's conversation, found by ElevenLabs' id or opened. Every call
    is a new conversation, never an open case."""
    existing = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call_id))
    if existing:
        return db.get(Conversation, existing.conversation_id)
    try:
        # Two tools at once on a call that never said who is calling may
        # both get here; the second finds what the first opened.
        with db.begin_nested():
            phone = contacts.normalize_phone(caller)
            contact = contacts.resolve_contact(db, line.client_id, phone=phone) if phone else None
            title = contacts.display_name(contact)[:240] if contact else (caller or "Phone call")
            conversation = Conversation(
                agency_id=line.agency_id,
                client_id=line.client_id,
                agent_id=line.agent_id,
                channel=CHANNEL,
                phone_channel_id=line.id,
                external_chat_id=f"call:{call_id}",
                contact_id=contact.id if contact else None,
                contact_name=(contact.name.strip()[:180] if contact and contact.name.strip() else None),
                title=title,
            )
            db.add(conversation)
            db.flush()
            db.add(PhoneCall(conversation_id=conversation.id, phone_channel_id=line.id, external_call_id=call_id, caller=caller))
            route_new_conversation_by_tags(db, conversation, contact)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call_id))
        if existing is None:
            raise
        return db.get(Conversation, existing.conversation_id)
    return conversation


def start_call(db: Session, line: PhoneChannel, payload: dict) -> dict:
    """Who is calling, asked by ElevenLabs when a call comes in, before the
    greeting: the contact as the chat knows them with their last case, and
    the details still to ask for. The call's conversation opens now, so it
    is in the inbox while it rings."""
    agent = line.agent
    lang = _language(agent)
    variables = {CALLER_VAR: "", PENDING_VAR: ""}
    call_id = _known(payload.get("conversation_id"))
    if call_id:
        conversation = _open_call(db, line, call_id, _known(payload.get("caller_id")))
        definitions = field_definitions(db, line.client_id, lang)
        variables[PENDING_VAR] = capture_context(agent, conversation, definitions, lang)
        known = [contact_context(conversation, lang, definitions), contacts.previous_conversation_recap(db, conversation)]
        variables[CALLER_VAR] = "\n\n".join(part for part in known if part)
        db.commit()
    return {"type": "conversation_initiation_client_data", "dynamic_variables": variables}


async def run_tool(db: Session, line: PhoneChannel, name: str, payload: dict) -> tuple[str, bool]:
    """One tool the agent used on a call, as ElevenLabs posts it. Returns the
    text the model reads back and whether it failed. What a built-in tool
    recorded (a detail, a hand-over) lands on the call's conversation."""
    args = dict(payload)
    call_id = _known(args.pop(CALL_ARG, None))
    caller = _known(args.pop(CALLER_ARG, None))
    tools = call_tools(db, line)
    spec = find_spec(tools.specs, name)
    if spec is None:
        return f"Unknown tool '{name}'.", True
    conversation = _open_call(db, line, call_id, caller) if call_id else None
    if name == KNOWLEDGE_TOOL:
        found = await retrieve_knowledge(db, line.agent, str(args.get("query") or ""), full_up_to=0)
        result, is_error = found.text or "Nothing in the documents matches that.", False
    else:
        result, is_error, _ = await execute_spec(spec, _decoded(spec, args))
    if conversation is not None:
        apply_captures(db, conversation, tools.captured, tools.definitions)
    db.commit()
    if conversation is not None and tools.escalation:
        await apply_escalation(db, conversation, line.agent, tools.escalation[-1])
    return result, is_error


# --- the end of a call ---------------------------------------------------------


# The voice's delivery cues ("[friendly]", "[laughs]"): spoken as tone, never
# as words, so they are not kept in the transcript.
_DELIVERY_CUE = re.compile(r"\[[^\W\d_]+(?: [^\W\d_]+){0,3}\]\s*")


@dataclass
class CallTurn:
    role: str
    text: str
    offset: float                   # seconds into the call
    tool_calls: list[dict] | None   # what the agent used before saying it, as a chat reply lists them


@dataclass
class CallReport:
    """A finished call as ElevenLabs reports it, reduced to what is kept."""

    call_id: str
    caller: str | None
    started: float | None   # unix seconds
    turns: list[CallTurn]


def _report(data: dict) -> CallReport:
    metadata = data.get("metadata") or {}
    phone_call = metadata.get("phone_call") or {}
    turns: list[CallTurn] = []
    used: dict[str, dict] = {}   # tool calls not yet followed by something the agent said
    for item in data.get("transcript") or []:
        for call in item.get("tool_calls") or []:
            try:
                arguments = json.loads(call.get("params_as_json") or "{}")
            except ValueError:
                arguments = {}
            if isinstance(arguments, dict):
                arguments = {key: value for key, value in arguments.items() if key not in (CALL_ARG, CALLER_ARG)}
            used[call.get("request_id") or str(len(used))] = {
                "name": call.get("tool_name") or "", "arguments": arguments, "result_preview": "", "is_error": False,
            }
        for result in item.get("tool_results") or []:
            entry = used.get(result.get("request_id") or "")
            if entry is not None:
                value = str(result.get("result_value") or "")
                entry["result_preview"] = value[:500] + ("…" if len(value) > 500 else "")
                entry["is_error"] = bool(result.get("is_error"))
        text = (item.get("message") or "").strip()
        if item.get("role") == "agent":
            text = _DELIVERY_CUE.sub("", text).strip()
        # "..." is a turn the speech recognition heard nothing in.
        if not text or text.strip(". ") == "":
            continue
        role = "assistant" if item.get("role") == "agent" else "user"
        calls = list(used.values()) if role == "assistant" and used else None
        if calls:
            used = {}
        turns.append(CallTurn(role, text, float(item.get("time_in_call_secs") or 0), calls))
    if used:
        last = next((turn for turn in reversed(turns) if turn.role == "assistant"), None)
        if last is not None:
            last.tool_calls = [*(last.tool_calls or []), *used.values()]
    started = metadata.get("start_time_unix_secs")
    return CallReport(
        call_id=data["conversation_id"],
        caller=_known(phone_call.get("external_number")),
        started=float(started) if isinstance(started, (int, float)) else None,
        turns=turns,
    )


def _store_transcript(db: Session, conversation: Conversation, report: CallReport, agent: Agent) -> None:
    """The call's turns as messages, each at the moment it was said."""
    if db.scalar(select(Message.id).where(Message.conversation_id == conversation.id, Message.external_message_id.like("turn:%")).limit(1)):
        return
    for index, turn in enumerate(report.turns):
        db.add(Message(
            conversation_id=conversation.id,
            role=turn.role,
            content=turn.text,
            tool_calls=turn.tool_calls,
            external_message_id=f"turn:{index}",
            sender_type="ai" if turn.role == "assistant" else "visitor",
            sender_name=agent.name if turn.role == "assistant" else None,
            created_at=datetime.fromtimestamp(report.started + turn.offset, timezone.utc) if report.started else now_utc(),
        ))
    conversation.updated_at = now_utc()


def signature_valid(account: CallAccount, raw_body: bytes, header: str | None, *, now: float | None = None) -> bool:
    """ElevenLabs signs ``{t}.{body}`` with HMAC-SHA256 and sends
    ``t=<unix>,v0=<hex>``; stale timestamps are refused."""
    if not account.encrypted_webhook_secret or not header:
        return False
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    timestamp, signature = parts.get("t", ""), parts.get("v0", "")
    if not timestamp.isdigit() or not signature:
        return False
    if abs((now or time.time()) - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    secret = decrypt_secret(account.encrypted_webhook_secret)
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _cost(metadata: dict) -> tuple[float | None, dict]:
    """What a call cost in USD (the voice's minutes plus the model) and the
    model's tokens, as ElevenLabs reports them on the finished call."""
    charging = metadata.get("charging") or {}
    prices = [charging.get(key) for key in ("platform_price", "llm_price")]
    cost = sum(float(price) for price in prices if isinstance(price, (int, float))) if any(isinstance(p, (int, float)) for p in prices) else None
    usage = ((charging.get("llm_usage") or {}).get("irreversible_generation") or {}).get("model_usage") or {}
    tokens = {"model": next(iter(usage), ""), "input": 0, "cached": 0, "output": 0}
    for entry in usage.values():
        count = lambda part: int((entry.get(part) or {}).get("tokens") or 0)  # noqa: E731
        tokens["input"] += count("input") + count("input_cache_read") + count("input_cache_write")
        tokens["cached"] += count("input_cache_read")
        tokens["output"] += count("output_total")
    return cost, tokens


def finish_call(db: Session, account: CallAccount, payload: dict) -> None:
    """Record the report ElevenLabs sends when a call ends: its transcript,
    duration and cost, and close the conversation unless a person has it."""
    if payload.get("type") == "call_initiation_failure":
        _call_failed(db, payload.get("data") or {})
        return
    if payload.get("type") != "post_call_transcription":
        return
    data = payload.get("data") or {}
    if not data.get("conversation_id"):
        return
    report = _report(data)
    record = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == report.call_id))
    if record is not None and record.ended_at is not None:
        return
    line = db.scalar(select(PhoneChannel).where(
        PhoneChannel.agency_id == account.agency_id, PhoneChannel.elevenlabs_agent_id == data.get("agent_id")
    )) if record is None else db.get(PhoneChannel, record.phone_channel_id)
    if line is None:
        return
    conversation = _open_call(db, line, report.call_id, report.caller)
    _store_transcript(db, conversation, report, line.agent)
    db.flush()
    record = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == report.call_id))
    metadata = data.get("metadata") or {}
    record.ended_at = now_utc()
    duration = metadata.get("call_duration_secs")
    record.duration_seconds = int(duration) if isinstance(duration, (int, float)) else None
    cost, tokens = _cost(metadata)
    record.cost_usd = cost
    # The call is one usage record, like a reply: Reports prices and lists it.
    record_usage(
        db, line.agency_id, line.agent_id, "elevenlabs", tokens["model"] or line.agent.model,
        Completion(
            "", tokens["input"], tokens["output"], cost_usd=cost, cached_tokens=tokens["cached"], served_by="ElevenLabs",
            duration_ms=record.duration_seconds * 1000 if record.duration_seconds is not None else None,
        ),
        conversation=conversation, purpose="call",
    )
    record.end_reason = str(metadata.get("termination_reason") or "")[:180] or None
    record.summary = ((data.get("analysis") or {}).get("transcript_summary") or None)
    if conversation.mode != "human" and conversation.status != "resolved":
        set_status(db, conversation, "resolved", actor=line.agent.name)
    db.commit()


def _call_failed(db: Session, data: dict) -> None:
    """A call that never connected. Its conversation opened when it came in,
    so it is closed with the reason rather than left waiting."""
    record = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == str(data.get("conversation_id") or "")))
    if record is None or record.ended_at is not None:
        return
    record.ended_at = now_utc()
    record.end_reason = str(data.get("failure_reason") or "call_initiation_failure")[:180]
    conversation = db.get(Conversation, record.conversation_id)
    if conversation is not None and conversation.mode != "human" and conversation.status != "resolved":
        line = db.get(PhoneChannel, record.phone_channel_id) if record.phone_channel_id else None
        set_status(db, conversation, "resolved", actor=line.agent.name if line else None)
    db.commit()
