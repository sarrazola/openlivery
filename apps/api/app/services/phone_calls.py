"""Phone calls answered by an agent.

ElevenLabs answers the number, hears the caller and speaks; for every reply it
calls the line's "custom LLM" URL with the call so far, and OpenLivery answers
with the same agent as in the chat: its instructions, knowledge, contact
fields, tools and escalation. A call is its own conversation on the ``phone``
channel, closed when ElevenLabs reports the hang-up.

ElevenLabs' own tools (hang up, transfer to a number) reach the model as
pass-through tools: when the model calls one, the reply ends and the call is
streamed back to ElevenLabs, which runs it after speaking the text.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, CallAccount, Conversation, Message, PhoneCall, PhoneChannel, now_utc
from ..security import decrypt_secret, encrypt_secret
from . import contacts
from .capture import apply_captures, build_capture_spec, capture_context, field_definitions
from .conversation_state import set_status
from .escalation import EscalationRequest, active_rules, apply_escalation, build_escalation_spec, escalation_enabled, escalation_prompt
from .knowledge import build_system_prompt, contact_context, retrieve_knowledge
from .providers import resolve_agent_credentials
from .routing import route_new_conversation_by_tags
from .telephony import TelephonyError, carriers, elevenlabs
from .tools import run_completion
from .tools.specs import ToolSpec
from .usage import record_usage

PROVIDERS = ("elevenlabs", *carriers.CARRIERS)
CHANNEL = "phone"
# What OpenLivery sets as the ElevenLabs agent's prompt. ElevenLabs fills the
# variables on every call and sends the result as part of the system message,
# which is how a turn names its call: no other field carries it.
MARKER = (
    "openlivery-call conversation={{system__conversation_id}} "
    "caller={{system__caller_id}} called={{system__called_number}}"
)
_MARKER_RE = re.compile(r"openlivery-call conversation=(\S+) caller=(\S+) called=(\S+)")
SIGNATURE_TOLERANCE_SECONDS = 30 * 60
# A spoken reply is short; this caps a model that forgets it.
MAX_REPLY_TOKENS = 400

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


class PhoneSetupError(RuntimeError):
    """Something the operator has to fix before a line can take calls."""


# --- accounts ----------------------------------------------------------------


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
    account.encrypted_secret = encrypt_secret(json.dumps(secret))
    account.secret_hint = secret_hint(provider, secret)
    account.enabled = True
    account.last_error = None
    return account


def account_out(account: CallAccount | None, provider: str) -> dict:
    return {
        "provider": provider,
        "configured": bool(account and account.enabled),
        "stored": account is not None,
        "secret_hint": account.secret_hint if account else "",
        "last_error": account.last_error if account else None,
    }


def elevenlabs_key(db: Session, agency_id) -> tuple[CallAccount, str]:
    account = get_account(db, agency_id, "elevenlabs")
    if not account or not account.enabled:
        raise PhoneSetupError("Add the ElevenLabs API key in Settings > Phone calls first.")
    return account, account_secret(account)["api_key"]


def carrier_secret(db: Session, agency_id, provider: str) -> dict:
    account = get_account(db, agency_id, provider)
    if not account or not account.enabled:
        raise PhoneSetupError(f"Connect the {provider.title()} account in Settings > Phone calls first.")
    return account_secret(account)


# --- lines -------------------------------------------------------------------


def public_base() -> str:
    settings = get_settings()
    return (settings.phone_public_url or settings.frontend_url).rstrip("/")


def llm_url(line: PhoneChannel) -> str:
    # ElevenLabs appends /chat/completions to this.
    return f"{public_base()}/api/public/phone/lines/{line.public_id}/llm"


def webhook_url(account: CallAccount) -> str:
    return f"{public_base()}/api/public/phone/accounts/{account.public_id}/webhook"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secret_name(line: PhoneChannel) -> str:
    return f"openlivery-line-{line.public_id}"


def _language(agent: Agent) -> str:
    return agent.prompt_language if agent.prompt_language in PHONE_RULES else "es"


def _agent_body(line: PhoneChannel, secret_id: str, webhook_id: str | None) -> dict:
    agent = line.agent
    tools: dict = {"end_call": {"type": "system", "name": "end_call", "description": "", "params": {"system_tool_type": "end_call"}}}
    if line.transfer_number:
        tools["transfer_to_number"] = {
            "type": "system",
            "name": "transfer_to_number",
            "description": "Put the caller through to a person of the business.",
            "params": {
                "system_tool_type": "transfer_to_number",
                "transfers": [{
                    "transfer_destination": {"type": "phone", "phone_number": line.transfer_number},
                    "condition": "When the caller needs a person.",
                    "transfer_type": "conference",
                }],
            },
        }
    body: dict = {
        "name": f"{line.client.name} · {line.label or line.phone_number}"[:120],
        "conversation_config": {
            "tts": {"voice_id": agent.voice_id},
            "agent": {
                "first_message": agent.greeting,
                "language": _language(agent),
                "prompt": {
                    "prompt": MARKER,
                    "llm": "custom-llm",
                    "custom_llm": {
                        "url": llm_url(line),
                        "model_id": agent.model.strip(),
                        "api_key": {"secret_id": secret_id},
                    },
                    "built_in_tools": tools,
                },
            },
        },
    }
    if webhook_id:
        body["platform_settings"] = {
            "workspace_overrides": {"webhooks": {"post_call_webhook_id": webhook_id, "events": elevenlabs.WEBHOOK_EVENTS}}
        }
    return body


async def connect_line(db: Session, line: PhoneChannel) -> None:
    """Set the line up at ElevenLabs and point its number there. Safe to run
    again: it updates what exists. Raises PhoneSetupError or TelephonyError;
    the caller stores the message on the line."""
    account, api_key = elevenlabs_key(db, line.agency_id)
    carrier = carrier_secret(db, line.agency_id, line.provider)
    agent = line.agent
    if agent.kind != "voice":
        raise PhoneSetupError("A phone line is answered by a voice agent. Choose one, or create one.")
    if not agent.voice_id or not agent.model.strip():
        raise PhoneSetupError("The agent has no voice or no model yet. Choose them in the agent's Voice tab.")
    agent.voice_name = (await elevenlabs.ensure_voice(api_key, agent.voice_id)) or agent.voice_name
    if not account.webhook_id:
        webhook_id, signing = await elevenlabs.create_webhook(api_key, "OpenLivery calls", webhook_url(account))
        account.webhook_id = webhook_id
        account.encrypted_webhook_secret = encrypt_secret(signing) if signing else None
        db.commit()
    token = "olv_" + secrets.token_urlsafe(32)
    secret_id = await elevenlabs.ensure_secret(api_key, secret_name(line), token)
    line.llm_secret_hash = _hash(token)
    line.elevenlabs_agent_id = await elevenlabs.upsert_agent(
        api_key, line.elevenlabs_agent_id, _agent_body(line, secret_id, account.webhook_id)
    )
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


async def disconnect_line(db: Session, line: PhoneChannel) -> None:
    """Take the number and the agent out of ElevenLabs. Best effort on each
    step: whatever is already gone does not stop the rest."""
    account = get_account(db, line.agency_id, "elevenlabs")
    if account:
        api_key = account_secret(account)["api_key"]
        steps = []
        if line.elevenlabs_phone_number_id:
            steps.append(elevenlabs.release_number(api_key, line.elevenlabs_phone_number_id))
        if line.elevenlabs_agent_id:
            steps.append(elevenlabs.delete_agent(api_key, line.elevenlabs_agent_id))
        steps.append(elevenlabs.delete_secret(api_key, secret_name(line)))
        for step in steps:
            try:
                await step
            except TelephonyError:
                pass
    line.elevenlabs_phone_number_id = None
    line.elevenlabs_agent_id = None
    line.llm_secret_hash = ""
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
        "transfer_number": line.transfer_number,
        "status": line.status,
        "is_enabled": line.is_enabled,
        "last_error": line.last_error,
        "last_connected_at": line.last_connected_at,
        "created_at": line.created_at,
        "updated_at": line.updated_at,
    }


# --- a turn ------------------------------------------------------------------


def secret_matches(line: PhoneChannel, authorization: str | None) -> bool:
    scheme, _, presented = (authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer" or not presented.strip() or not line.llm_secret_hash:
        return False
    return hmac.compare_digest(_hash(presented.strip()), line.llm_secret_hash)


@dataclass
class CallTurn:
    """What ElevenLabs sent, reduced to what a reply needs."""

    call_id: str
    caller: str | None
    turns: list[dict]           # user/assistant turns as said on the call, oldest first
    tools: list[dict]           # ElevenLabs' tools, OpenAI format


def _known(value: str) -> str | None:
    return None if value in ("", "None", "null", "undefined") or value.startswith("{{") else value


def parse_turn(body: dict) -> CallTurn:
    messages = body.get("messages") or []
    marker = None
    for message in messages:
        if message.get("role") == "system":
            marker = _MARKER_RE.search(str(message.get("content") or ""))
            if marker:
                break
    if not marker or not _known(marker.group(1)):
        raise ValueError("The request does not name its call")
    turns = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip() and content != "None":
            turns.append({"role": role, "content": content.strip()})
    return CallTurn(call_id=marker.group(1), caller=_known(marker.group(2)), turns=turns, tools=list(body.get("tools") or []))


def _open_call(db: Session, line: PhoneChannel, call: CallTurn) -> Conversation:
    """The call's conversation: found by ElevenLabs' id, or opened on its
    first turn. Every call is a new conversation, never an open case."""
    existing = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call.call_id))
    if existing:
        return db.get(Conversation, existing.conversation_id)
    phone = contacts.normalize_phone(call.caller)
    contact = contacts.resolve_contact(db, line.client_id, phone=phone) if phone else None
    title = contacts.display_name(contact)[:240] if contact else (call.caller or "Phone call")
    conversation = Conversation(
        agency_id=line.agency_id,
        client_id=line.client_id,
        agent_id=line.agent_id,
        channel=CHANNEL,
        phone_channel_id=line.id,
        external_chat_id=f"call:{call.call_id}",
        contact_id=contact.id if contact else None,
        contact_name=(contact.name.strip()[:180] if contact and contact.name.strip() else None),
        title=title,
    )
    db.add(conversation)
    db.flush()
    db.add(PhoneCall(conversation_id=conversation.id, phone_channel_id=line.id, external_call_id=call.call_id, caller=call.caller))
    route_new_conversation_by_tags(db, conversation, contact)
    db.flush()
    return conversation


def _store_turns(db: Session, conversation: Conversation, call: CallTurn, agent: Agent) -> str:
    """Store what was said since the last stored turn; returns the caller's
    latest words, for knowledge retrieval. Turns are keyed by their position
    in the call, so a retried request stores nothing twice.

    The history moves under a stored turn in two ways. A caller who keeps
    talking comes back as the same turn, longer, and the stored text follows
    it. A reply the caller talked over can drop out of the history, so its
    position now holds what the caller said: the reply keeps its text under
    another key and the position goes to the caller."""
    stored = {
        message.external_message_id: message
        for message in db.scalars(select(Message).where(Message.conversation_id == conversation.id, Message.external_message_id.like("turn:%")))
    }
    latest = ""
    for index, turn in enumerate(call.turns):
        key = f"turn:{index}"
        if turn["role"] == "user":
            latest = turn["content"]
        existing = stored.get(key)
        if existing is not None and existing.role == turn["role"]:
            if turn["role"] == "user" and existing.content != turn["content"]:
                existing.content = turn["content"]
            continue
        if existing is not None:
            existing.external_message_id = f"unheard:{existing.id}"
            db.flush()
        db.add(Message(
            conversation_id=conversation.id,
            role=turn["role"],
            content=turn["content"],
            external_message_id=key,
            sender_type="ai" if turn["role"] == "assistant" else "visitor",
            sender_name=agent.name if turn["role"] == "assistant" else None,
        ))
    conversation.updated_at = now_utc()
    return latest


def _passthrough_specs(tools: list[dict], holder: list[dict]) -> list[ToolSpec]:
    """ElevenLabs' tools as tools the model can call. Calling one ends the
    reply: it is recorded here and handed back to ElevenLabs to run."""
    specs = []
    for tool in tools:
        function = tool.get("function") or {}
        name = function.get("name")
        if not name:
            continue

        def handler(args: dict, _name: str = name) -> tuple[str, bool]:
            holder.append({"name": _name, "arguments": args})
            return "Done: it runs right after this reply. Say one short sentence to the caller now, nothing else.", False

        specs.append(ToolSpec(
            name=name,
            description=function.get("description") or name,
            input_schema=function.get("parameters") or {"type": "object", "properties": {}},
            handler=handler,
        ))
    return specs


def _store_call(db: Session, line: PhoneChannel, call: CallTurn) -> tuple[Conversation, str]:
    """Open the call's conversation and store its turns. ElevenLabs can ask
    for the same turn twice at once; the slower request loses the insert, and
    a second pass finds what the other one stored."""
    try:
        conversation = _open_call(db, line, call)
        query = _store_turns(db, conversation, call, line.agent)
        db.commit()
    except IntegrityError:
        db.rollback()
        conversation = _open_call(db, line, call)
        query = _store_turns(db, conversation, call, line.agent)
        db.commit()
    return conversation, query


@dataclass
class Reply:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


async def answer_turn(db: Session, line: PhoneChannel, body: dict) -> Reply:
    """One reply of the call, with the agent behind the line."""
    call = parse_turn(body)
    agent = line.agent
    conversation, query = _store_call(db, line, call)

    credentials = resolve_agent_credentials(db, agent)
    model = agent.model.strip()
    if not agent.is_active or not credentials or not model:
        line.last_error = "A call came in, but the agent is not ready (model or provider key missing)."
        db.commit()
        return Reply(text="")

    lang = _language(agent)
    knowledge = await retrieve_knowledge(db, agent, query)
    definitions = field_definitions(db, agent.client_id, agent.prompt_language)
    capture_holder: list = []
    system_content = build_system_prompt(agent, knowledge.text, capture_context(agent, conversation, definitions, agent.prompt_language))
    for block in (
        contact_context(conversation, agent.prompt_language, definitions),
        contacts.previous_conversation_recap(db, conversation),
    ):
        if block:
            system_content += "\n\n" + block
    system_content += "\n\n" + PHONE_RULES[lang]

    passthrough: list[dict] = []
    tools = call.tools
    escalation_holder: list = []
    extra_specs: list[ToolSpec] = []
    if line.transfer_number:
        system_content += TRANSFER_RULE[lang]
    else:
        tools = [t for t in tools if (t.get("function") or {}).get("name") != "transfer_to_number"]
        rules = active_rules(db, agent)
        if escalation_enabled(db, agent, rules):
            system_content += CALLBACK_RULE[lang] + "\n" + escalation_prompt(rules, builtin_enabled=agent.escalation_builtin_enabled)
            extra_specs.append(build_escalation_spec(rules, escalation_holder, builtin_enabled=agent.escalation_builtin_enabled))
    capture_spec = build_capture_spec(agent, conversation, definitions, capture_holder)
    if capture_spec:
        extra_specs.append(capture_spec)
    extra_specs.extend(_passthrough_specs(tools, passthrough))

    history = call.turns[-agent.memory_limit:] if agent.memory_limit else call.turns
    messages = [{"role": "system", "content": system_content}, *history]
    base_url, api_key = credentials
    max_tokens = min(agent.max_tokens, MAX_REPLY_TOKENS) if agent.max_tokens else MAX_REPLY_TOKENS
    completion = await run_completion(
        db, agent, base_url, api_key, messages,
        temperature=agent.temperature, max_tokens=max_tokens, extra_specs=extra_specs or None, model=model,
    )

    outbound = None
    if completion.text:
        # The same history asked again (a retry, or the caller still talking)
        # replaces the reply it got before, which the caller never heard.
        key = f"turn:{len(call.turns)}"
        outbound = db.scalar(select(Message).where(Message.conversation_id == conversation.id, Message.external_message_id == key))
        if outbound is None:
            outbound = Message(
                conversation_id=conversation.id, role="assistant", content=completion.text, sources=knowledge.sources,
                tool_calls=completion.tool_calls, sender_type="ai", sender_name=agent.name, external_message_id=key,
            )
            db.add(outbound)
        else:
            outbound.content, outbound.sources, outbound.tool_calls = completion.text, knowledge.sources, completion.tool_calls
    record_usage(db, agent.agency_id, agent.id, agent.provider, model, completion, conversation=conversation, message=outbound)
    apply_captures(db, conversation, capture_holder, definitions)
    line.last_error = None
    try:
        db.commit()
    except IntegrityError:
        # A request for the same turn running alongside stored its reply
        # first; this one is still said, which is what the caller waits for.
        db.rollback()

    transfer = next((item for item in passthrough if item["name"] == "transfer_to_number"), None)
    if transfer and not escalation_holder:
        args = transfer["arguments"]
        reason = str(args.get("reason") or args.get("agent_message") or "")[:300]
        escalation_holder.append(EscalationRequest(reason=reason, trigger="human_request"))
    if escalation_holder:
        await apply_escalation(db, conversation, agent, escalation_holder[-1])
        db.commit()
    return Reply(
        text=completion.text,
        tool_calls=passthrough,
        model=model,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
    )


_SENTENCE = re.compile(r"(?<=[.!?¿¡…])\s+")


def stream_reply(reply: Reply):
    """The reply as an OpenAI chat-completion stream, sentence by sentence so
    the voice starts on the first one."""
    stream_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def chunk(delta: dict | None = None, finish: str | None = None, usage: dict | None = None) -> str:
        payload: dict = {"id": stream_id, "object": "chat.completion.chunk", "created": created, "model": reply.model}
        payload["choices"] = [] if usage else [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
        if usage:
            payload["usage"] = usage
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield chunk({"role": "assistant", "content": ""})
    sentences = [s for s in _SENTENCE.split(reply.text.strip()) if s] if reply.text.strip() else []
    for index, sentence in enumerate(sentences):
        yield chunk({"content": sentence + (" " if index < len(sentences) - 1 else "")})
    for index, call in enumerate(reply.tool_calls):
        yield chunk({"tool_calls": [{
            "index": index, "id": f"call_{uuid.uuid4().hex[:24]}", "type": "function",
            "function": {"name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False)},
        }]})
    yield chunk(finish="tool_calls" if reply.tool_calls else "stop")
    yield chunk(usage={
        "prompt_tokens": reply.input_tokens,
        "completion_tokens": reply.output_tokens,
        "total_tokens": reply.input_tokens + reply.output_tokens,
    })
    yield "data: [DONE]\n\n"


# --- the end of a call ---------------------------------------------------------


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


def finish_call(db: Session, account: CallAccount, payload: dict) -> None:
    """Record the report ElevenLabs sends when a call ends and close the
    conversation, unless a person has it now."""
    if payload.get("type") != "post_call_transcription":
        return
    data = payload.get("data") or {}
    call_id = data.get("conversation_id")
    if not call_id:
        return
    record = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call_id))
    metadata = data.get("metadata") or {}
    if record is None:
        # The caller hung up before saying anything: no turn ever reached us.
        line = db.scalar(select(PhoneChannel).where(
            PhoneChannel.agency_id == account.agency_id, PhoneChannel.elevenlabs_agent_id == data.get("agent_id")
        ))
        if line is None:
            return
        phone_call = metadata.get("phone_call") or {}
        caller = phone_call.get("external_number")
        greeting = next((t.get("message") for t in data.get("transcript") or [] if t.get("role") == "agent" and t.get("message")), None)
        call = CallTurn(call_id=call_id, caller=caller, turns=[{"role": "assistant", "content": greeting}] if greeting else [], tools=[])
        conversation = _open_call(db, line, call)
        _store_turns(db, conversation, call, line.agent)
        db.flush()
        record = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == call_id))
    if record.ended_at is not None:
        return
    record.ended_at = now_utc()
    duration = metadata.get("call_duration_secs")
    record.duration_seconds = int(duration) if isinstance(duration, (int, float)) else None
    cost = metadata.get("cost")
    record.cost_credits = int(cost) if isinstance(cost, (int, float)) else None
    record.end_reason = str(metadata.get("termination_reason") or "")[:180] or None
    record.summary = ((data.get("analysis") or {}).get("transcript_summary") or None)
    conversation = db.get(Conversation, record.conversation_id)
    if conversation and conversation.mode != "human" and conversation.status != "resolved":
        agent = db.get(Agent, conversation.agent_id)
        set_status(db, conversation, "resolved", actor=agent.name if agent else None)
    db.commit()
