"""Phone calls answered by an agent.

ElevenLabs answers the number and runs the call: it hears the caller, decides
when they finished or cut in, thinks with one of its own models and speaks.
OpenLivery writes what the agent knows into the ElevenLabs agent of each line
(its business, offer, rules and the phone rules, its greeting and voice) and
writes it again whenever the agent changes, so a turn never waits on us. When
the call ends ElevenLabs reports it, and it becomes a conversation on the
``phone`` channel with its transcript, closed unless a person has it.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, CallAccount, Conversation, Message, PhoneCall, PhoneChannel, now_utc
from ..security import decrypt_secret, encrypt_secret
from . import contacts
from .conversation_state import set_status
from .knowledge import build_system_prompt
from .routing import route_new_conversation_by_tags
from .ai import Completion
from .telephony import TelephonyError, carriers, elevenlabs
from .usage import record_usage

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
# Who is calling, filled in by ElevenLabs on every call.
CALLER = {
    "es": "## Quien llama\n- **Teléfono desde el que llama:** {{system__caller_id}}",
    "en": "## Caller\n- **Calling from:** {{system__caller_id}}",
}


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
        # The row held a lent account's webhook, which lives in the lender's
        # workspace: the agency's own one gets its own.
        account.webhook_id = None
        account.encrypted_webhook_secret = None
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


# --- lines -------------------------------------------------------------------


def public_base() -> str:
    settings = get_settings()
    return (settings.phone_public_url or settings.frontend_url).rstrip("/")


def webhook_url(account: CallAccount) -> str:
    return f"{public_base()}/api/public/phone/accounts/{account.public_id}/webhook"


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


def call_prompt(line: PhoneChannel) -> str:
    """What the line's ElevenLabs agent is told: the agent's prompt as the
    chat builds it, who is calling, and how to speak on the phone. The date
    and time are left to ElevenLabs, which adds them on every call in the
    client's timezone; written here they would be the moment of the sync."""
    agent = line.agent
    lang = _language(agent)
    rules = PHONE_RULES[lang] + (TRANSFER_RULE[lang] if agent.transfer_number else CALLBACK_RULE[lang])
    return "\n\n".join([build_system_prompt(agent, "", with_time=False), CALLER[lang], rules.rstrip()])


def _agent_body(line: PhoneChannel, webhook_id: str | None) -> dict:
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
        "prompt": call_prompt(line), "built_in_tools": tools, "timezone": agent.client.timezone or "UTC",
        "llm": REALTIME_IDLE_LLM if model in REALTIME_MODELS else model, "custom_llm": None,
    }
    body: dict = {
        "name": f"{line.client.name} · {line.label or line.phone_number}"[:120],
        "conversation_config": {
            # Realtime replaces the LLM, speech and turn models with its own;
            # null hands the agent back to the ones set here.
            "realtime_model": model if model in REALTIME_MODELS else None,
            "asr": {"user_input_audio_format": PHONE_AUDIO},
            "tts": {"voice_id": voice_of(agent), "agent_output_audio_format": PHONE_AUDIO},
            "turn": _turn_settings(lang),
            "agent": {"first_message": agent.greeting, "language": lang, "prompt": prompt},
        },
    }
    if webhook_id:
        body["platform_settings"] = {
            "workspace_overrides": {"webhooks": {"post_call_webhook_id": webhook_id, "events": elevenlabs.WEBHOOK_EVENTS}}
        }
    return body


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
    if not account.webhook_id:
        webhook_id, signing = await elevenlabs.create_webhook(api_key, "OpenLivery calls", webhook_url(account))
        account.webhook_id = webhook_id
        account.encrypted_webhook_secret = encrypt_secret(signing) if signing else None
        db.commit()
    line.elevenlabs_agent_id = await elevenlabs.upsert_agent(api_key, line.elevenlabs_agent_id, _agent_body(line, account.webhook_id))
    db.commit()
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


async def resync_lines(db: Session, *, agent_id=None, client_id=None) -> None:
    """Write the agent again into its connected lines; one that cannot take
    it keeps the error to show."""
    query = select(PhoneChannel).where(PhoneChannel.is_enabled.is_(True), PhoneChannel.status == "connected")
    if agent_id is not None:
        query = query.where(PhoneChannel.agent_id == agent_id)
    if client_id is not None:
        query = query.where(PhoneChannel.client_id == client_id)
    for line in db.scalars(query).all():
        try:
            await connect_line(db, line)
        except (PhoneSetupError, TelephonyError) as exc:
            db.rollback()
            line.status = "error"
            line.last_error = str(exc)
            db.commit()


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
        for step in steps:
            try:
                await step
            except TelephonyError:
                pass
    line.elevenlabs_phone_number_id = None
    line.elevenlabs_agent_id = None
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


# --- the end of a call ---------------------------------------------------------


@dataclass
class CallReport:
    """A finished call as ElevenLabs reports it, reduced to what is kept."""

    call_id: str
    caller: str | None
    started: float | None                 # unix seconds
    turns: list[tuple[str, str, float]]   # (role, text, seconds into the call)


def _known(value) -> str | None:
    value = str(value or "").strip()
    return None if value in ("", "None", "null", "undefined") else value


def _report(data: dict) -> CallReport:
    metadata = data.get("metadata") or {}
    phone_call = metadata.get("phone_call") or {}
    turns = []
    for item in data.get("transcript") or []:
        text = (item.get("message") or "").strip()
        # "..." is a turn the speech recognition heard nothing in.
        if not text or text.strip(". ") == "":
            continue
        role = "assistant" if item.get("role") == "agent" else "user"
        turns.append((role, text, float(item.get("time_in_call_secs") or 0)))
    started = metadata.get("start_time_unix_secs")
    return CallReport(
        call_id=data["conversation_id"],
        caller=_known(phone_call.get("external_number")),
        started=float(started) if isinstance(started, (int, float)) else None,
        turns=turns,
    )


def _open_call(db: Session, line: PhoneChannel, call_id: str, caller: str | None) -> Conversation:
    """The call's conversation, found by ElevenLabs' id or opened. Every call
    is a new conversation, never an open case."""
    existing = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call_id))
    if existing:
        return db.get(Conversation, existing.conversation_id)
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
    return conversation


def _store_transcript(db: Session, conversation: Conversation, report: CallReport, agent: Agent) -> None:
    """The call's turns as messages, each at the moment it was said."""
    if db.scalar(select(Message.id).where(Message.conversation_id == conversation.id, Message.external_message_id.like("turn:%")).limit(1)):
        return
    for index, (role, text, offset) in enumerate(report.turns):
        db.add(Message(
            conversation_id=conversation.id,
            role=role,
            content=text,
            external_message_id=f"turn:{index}",
            sender_type="ai" if role == "assistant" else "visitor",
            sender_name=agent.name if role == "assistant" else None,
            created_at=datetime.fromtimestamp(report.started + offset, timezone.utc) if report.started else now_utc(),
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
