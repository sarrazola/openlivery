"""Phone calls: the agency's accounts (ElevenLabs and its carriers) and the
lines its clients' agents answer."""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, CallAccount, Client, PhoneChannel, User
from ..ratelimit import phone_call_rate_limit
from ..schemas_phone import (
    CallAccountIn,
    CallAccountOut,
    CallAccountTest,
    CarrierNumberOut,
    PhoneLineCreate,
    PhoneLineOut,
    PhoneLineUpdate,
    PhoneModelOut,
    PhoneVoiceOut,
)
from ..services import phone_calls
from ..services.contacts import normalize_phone
from ..services.telephony import TelephonyError, carriers, elevenlabs

log = logging.getLogger(__name__)

router = APIRouter(prefix="/phone", tags=["Phone calls"])
public_router = APIRouter(prefix="/public/phone", tags=["Phone calls"])


def _provider(provider: str) -> str:
    if provider not in phone_calls.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown phone provider")
    return provider


def _setup_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# --- accounts ----------------------------------------------------------------


@router.get("/accounts", response_model=list[CallAccountOut])
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [phone_calls.account_out(db, user.agency_id, p) for p in phone_calls.PROVIDERS]


@router.post("/accounts/{provider}/validate", response_model=CallAccountTest)
async def validate_account(provider: str, payload: CallAccountIn, user: User = Depends(get_current_user)):
    try:
        secret = phone_calls.clean_secret(_provider(provider), payload.model_dump())
        return CallAccountTest(ok=True, message=await phone_calls.validate_account(provider, secret))
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        return CallAccountTest(ok=False, message=str(exc))


@router.put("/accounts/{provider}", response_model=CallAccountOut)
async def save_account(provider: str, payload: CallAccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Validated against the provider before it is stored: a wrong key never
    replaces a working one."""
    try:
        secret = phone_calls.clean_secret(_provider(provider), payload.model_dump())
        await phone_calls.validate_account(provider, secret)
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        raise _setup_error(exc) from exc
    phone_calls.store_account(db, user.agency_id, provider, secret)
    db.commit()
    return phone_calls.account_out(db, user.agency_id, provider)


@router.delete("/accounts/{provider}", status_code=204)
def remove_account(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    account = phone_calls.get_account(db, user.agency_id, _provider(provider))
    # A row without a secret only keeps the webhook of a lent account.
    if account and account.encrypted_secret:
        in_use = db.scalar(select(PhoneChannel.id).where(
            PhoneChannel.agency_id == user.agency_id,
            PhoneChannel.status == "connected",
            *([PhoneChannel.provider == provider] if provider != "elevenlabs" else []),
        ).limit(1))
        if in_use:
            raise HTTPException(status_code=409, detail="A connected phone line uses this account. Disconnect its lines first.")
        db.delete(account)
        db.commit()
    return Response(status_code=204)


@router.get("/voices/{voice_id}", response_model=PhoneVoiceOut)
async def find_voice(voice_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        _, api_key = phone_calls.elevenlabs_key(db, user.agency_id)
        voice = await elevenlabs.find_voice(api_key, voice_id.strip()[:80])
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        raise _setup_error(exc) from exc
    if voice is None:
        raise HTTPException(status_code=404, detail="ElevenLabs has no voice with that ID in its library.")
    return voice


@router.get("/default-voice", response_model=PhoneVoiceOut)
async def default_voice(language: str = "es", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The voice an agent in ``language`` speaks with until it picks one."""
    voice_id = phone_calls.DEFAULT_VOICES.get(language[:2], phone_calls.DEFAULT_VOICES["es"])
    try:
        _, api_key = phone_calls.elevenlabs_key(db, user.agency_id)
        voice = await elevenlabs.find_voice(api_key, voice_id)
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        raise _setup_error(exc) from exc
    if voice is None:
        raise HTTPException(status_code=404, detail="The default voice is not in the ElevenLabs library any more.")
    return voice


@router.get("/models", response_model=list[PhoneModelOut])
def list_models(user: User = Depends(get_current_user)):
    """What a voice agent can think with, the default first."""
    return [
        {"id": model, "label": label, "realtime": model in phone_calls.REALTIME_MODELS}
        for model, label in phone_calls.VOICE_MODELS.items()
    ]


@router.get("/numbers", response_model=list[CarrierNumberOut])
async def list_numbers(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if provider not in carriers.CARRIERS:
        raise HTTPException(status_code=404, detail="Unknown phone provider")
    try:
        return await carriers.list_numbers(provider, phone_calls.carrier_secret(db, user.agency_id, provider))
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        raise _setup_error(exc) from exc


# --- lines -------------------------------------------------------------------


def _owned_client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _client_agent(db: Session, user: User, client_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    agent = db.scalar(select(Agent).where(
        Agent.id == agent_id, Agent.client_id == client_id, Agent.agency_id == user.agency_id, Agent.deleted_at.is_(None)
    ))
    if not agent:
        raise HTTPException(status_code=400, detail="Select an agent that belongs to this client")
    if agent.kind != "voice":
        raise HTTPException(status_code=400, detail="A phone line is answered by a voice agent. Choose one, or create one.")
    return agent


def _line(db: Session, user: User, line_id: uuid.UUID) -> PhoneChannel:
    line = db.scalar(select(PhoneChannel).where(PhoneChannel.id == line_id, PhoneChannel.agency_id == user.agency_id))
    if not line:
        raise HTTPException(status_code=404, detail="Phone line not found")
    return line


async def _connect(db: Session, line: PhoneChannel) -> None:
    try:
        await phone_calls.connect_line(db, line)
    except (phone_calls.PhoneSetupError, TelephonyError) as exc:
        db.rollback()
        line.status = "error"
        line.last_error = str(exc)
        db.commit()


@router.get("/clients/{client_id}/lines", response_model=list[PhoneLineOut])
def list_lines(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_client(db, user, client_id)
    lines = db.scalars(select(PhoneChannel).where(PhoneChannel.client_id == client_id).order_by(PhoneChannel.created_at)).all()
    return [phone_calls.line_out(line) for line in lines]


@router.post("/clients/{client_id}/lines", response_model=PhoneLineOut, status_code=201)
async def create_line(client_id: uuid.UUID, payload: PhoneLineCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Adding a line connects it: the number starts ringing the agent."""
    client = _owned_client(db, user, client_id)
    _client_agent(db, user, client.id, payload.agent_id)
    taken = db.scalar(select(PhoneChannel.id).where(
        PhoneChannel.agency_id == user.agency_id, PhoneChannel.phone_number == payload.phone_number
    ))
    if taken:
        raise HTTPException(status_code=409, detail="That number already rings an agent.")
    line = PhoneChannel(
        agency_id=user.agency_id, client_id=client.id, **payload.model_dump(),
    )
    db.add(line)
    db.commit()
    await _connect(db, line)
    return phone_calls.line_out(line)


@router.put("/lines/{line_id}", response_model=PhoneLineOut)
async def update_line(line_id: uuid.UUID, payload: PhoneLineUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    line = _line(db, user, line_id)
    values = payload.model_dump(exclude_unset=True)
    if "agent_id" in values and values["agent_id"]:
        _client_agent(db, user, line.client_id, values["agent_id"])
    enabled = values.pop("is_enabled", None)
    for key, value in values.items():
        if value is not None or key == "label":
            setattr(line, key, value)
    if enabled is not None:
        line.is_enabled = enabled
    db.commit()
    # Every change reaches ElevenLabs: voice, greeting, agent and transfer
    # number live in its agent too.
    if line.is_enabled:
        await _connect(db, line)
    else:
        await phone_calls.disconnect_line(db, line)
    return phone_calls.line_out(line)


@router.post("/lines/{line_id}/connect", response_model=PhoneLineOut)
async def reconnect_line(line_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    line = _line(db, user, line_id)
    line.is_enabled = True
    await _connect(db, line)
    return phone_calls.line_out(line)


@router.delete("/lines/{line_id}", status_code=204)
async def remove_line(line_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The number stops ringing the agent; its calls stay as conversations."""
    line = _line(db, user, line_id)
    await phone_calls.disconnect_line(db, line)
    db.delete(line)
    db.commit()
    return Response(status_code=204)


# --- what ElevenLabs calls -----------------------------------------------------


@public_router.post("/accounts/{public_id}/webhook")
async def call_report(public_id: str, request: Request, db: Session = Depends(get_db)):
    """ElevenLabs' report at the end of a call, signed with the webhook's secret."""
    account = db.scalar(select(CallAccount).where(CallAccount.public_id == public_id, CallAccount.provider == "elevenlabs"))
    raw = await request.body()
    if not account or not phone_calls.signature_valid(account, raw, request.headers.get("elevenlabs-signature")):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    phone_calls.finish_call(db, account, payload)
    return {"ok": True}


def _calling_line(db: Session, public_id: str, request: Request) -> PhoneChannel:
    """The line an ElevenLabs callback names, once its secret checks out."""
    line = db.scalar(select(PhoneChannel).where(PhoneChannel.public_id == public_id))
    if not line or not phone_calls.callback_authorized(db, line, request.headers.get(phone_calls.TOKEN_HEADER)):
        raise HTTPException(status_code=401, detail="Invalid token")
    return line


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    return body if isinstance(body, dict) else {}


@public_router.post("/lines/{public_id}/start", dependencies=[Depends(phone_call_rate_limit)])
async def call_starts(public_id: str, request: Request, db: Session = Depends(get_db)):
    """ElevenLabs asks who is calling when a call comes in. A failure here
    must not keep the phone from being answered: the agent then starts with
    what it always knows."""
    line = _calling_line(db, public_id, request)
    payload = await _json_body(request)
    try:
        return phone_calls.start_call(db, line, payload)
    except Exception:
        log.exception("Could not say who is calling on line %s", line.id)
        db.rollback()
        return {"type": "conversation_initiation_client_data",
                "dynamic_variables": {phone_calls.CALLER_VAR: "", phone_calls.PENDING_VAR: ""}}


@public_router.post("/lines/{public_id}/tools/{name}", dependencies=[Depends(phone_call_rate_limit)])
async def call_tool(public_id: str, name: str, request: Request, db: Session = Depends(get_db)):
    """A tool the agent used on a call. The model reads the answer, so a
    failure is answered as text it can act on, never as an HTTP error."""
    line = _calling_line(db, public_id, request)
    payload = await _json_body(request)
    try:
        result, is_error = await phone_calls.run_tool(db, line, name, payload)
    except Exception:
        log.exception("Tool %s failed on line %s", name, line.id)
        db.rollback()
        result, is_error = "The tool is not available right now.", True
    return {"error": result} if is_error else {"result": result}
