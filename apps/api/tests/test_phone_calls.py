import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Contact, Conversation, KnowledgeDocument, Message, PhoneCall, PhoneChannel, UsageRecord
from app.services import phone_calls
from app.services.telephony import TelephonyError, elevenlabs

WEBHOOK_SECRET = "wsec_test"
CALLER = "+573001112233"


@pytest.fixture
def provisioning(monkeypatch):
    """ElevenLabs as the tests see it: every call recorded, nothing on the network."""
    calls: dict = {"bodies": [], "tools": {}, "tool_writes": 0}

    async def upsert_agent(api_key, agent_id, body):
        calls["agent_body"] = body
        calls["bodies"].append(body)
        return agent_id or "agent_el_1"

    async def create_secret(api_key, name, value):
        calls["token"] = value
        return "sec_1"

    async def upsert_tool(api_key, tool_id, config):
        tool_id = tool_id or f"tool_{len(calls['tools']) + 1}"
        calls["tools"][tool_id] = config
        calls["tool_writes"] += 1
        return tool_id

    monkeypatch.setattr(elevenlabs, "validate_key", AsyncMock(return_value="ElevenLabs connected."))
    monkeypatch.setattr(elevenlabs, "ensure_voice", AsyncMock(return_value="Sofía"))
    monkeypatch.setattr(elevenlabs, "create_webhook", AsyncMock(return_value=("wh_1", WEBHOOK_SECRET)))
    monkeypatch.setattr(elevenlabs, "upsert_agent", upsert_agent)
    monkeypatch.setattr(elevenlabs, "import_twilio_number", AsyncMock(return_value="phnum_1"))
    monkeypatch.setattr(elevenlabs, "assign_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "release_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "delete_agent", AsyncMock())
    monkeypatch.setattr(elevenlabs, "create_secret", create_secret)
    monkeypatch.setattr(elevenlabs, "upsert_tool", upsert_tool)
    monkeypatch.setattr(elevenlabs, "delete_tool", AsyncMock())
    monkeypatch.setattr(phone_calls.carriers, "validate", AsyncMock(return_value="Twilio connected: Dentix."))
    # Edits elsewhere only note that a line is behind; tests write it themselves.
    calls["refreshed"] = []
    monkeypatch.setattr(phone_calls, "_schedule_resync", lambda agent_id: calls["refreshed"].append(str(agent_id)))
    return calls


def _tools(provisioning: dict) -> dict:
    """The line's tools as the agent last uses them, by name."""
    used = provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]["tool_ids"]
    return {provisioning["tools"][tool_id]["name"]: provisioning["tools"][tool_id] for tool_id in used}


def _resync(line_id: str) -> None:
    with SessionLocal() as db:
        line = db.get(PhoneChannel, line_id)
        asyncio.run(phone_calls.resync_lines(db, agent_id=line.agent_id))


def _public_id(line_id: str) -> str:
    with SessionLocal() as db:
        return db.get(PhoneChannel, line_id).public_id


def _line(client: TestClient, *, model: str = "eleven_realtime_v1_mini", transfer_number: str | None = None, **overrides) -> tuple[dict, dict, dict]:
    assert client.put("/api/phone/accounts/elevenlabs", json={"api_key": "xi-key"}).status_code == 200
    assert client.put("/api/phone/accounts/twilio", json={"account_sid": "AC123", "auth_token": "tok"}).status_code == 200
    customer = client.post("/api/clients", json={"name": "Dentix", "is_active": True, "timezone": "America/Bogota"}).json()
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "model": model, "name": "Sofía",
        "instructions": "Agenda citas.", "brief_products": "Limpieza: $80.000.", "personality": "", "is_active": True,
        "kind": "voice", "voice_id": "voice_1", "greeting": "¡Hola! Hablas con Dentix.", "transfer_number": transfer_number,
    })
    assert agent.status_code == 201, agent.text
    body = {
        "agent_id": agent.json()["id"], "provider": "twilio", "provider_number_id": "PN1", "phone_number": "+15550001111",
        **overrides,
    }
    created = client.post(f"/api/phone/clients/{customer['id']}/lines", json=body)
    assert created.status_code == 201, created.text
    return customer, agent.json(), created.json()


def _signed(payload: dict, secret: str = WEBHOOK_SECRET, at: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps(payload).encode()
    timestamp = str(at or int(time.time()))
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"ElevenLabs-Signature": f"t={timestamp},v0={digest}", "Content-Type": "application/json"}


def _webhook_url() -> str:
    with SessionLocal() as db:
        account = db.scalar(select(phone_calls.CallAccount).where(phone_calls.CallAccount.provider == "elevenlabs"))
        return f"/api/public/phone/accounts/{account.public_id}/webhook"


def _report(call_id: str, transcript: list[dict], **metadata) -> dict:
    return {"type": "post_call_transcription", "data": {
        "conversation_id": call_id, "agent_id": "agent_el_1", "transcript": transcript,
        "metadata": {"start_time_unix_secs": 1_800_000_000, "phone_call": {"external_number": CALLER}, **metadata},
        "analysis": {"transcript_summary": "The caller booked a cleaning."},
    }}


def test_a_key_without_the_webhook_permission_is_refused_by_name(monkeypatch):
    missing = {"detail": {"status": "missing_permissions", "message": "The API key you used is missing the permission webhooks_write to execute this operation."}}
    webhook_status = {"code": 401}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/workspace/webhooks"):
            return httpx.Response(webhook_status["code"], json=missing if webhook_status["code"] == 401 else {"detail": [{"msg": "Field required"}]})
        return httpx.Response(200, json={"agents": []})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(TelephonyError, match="missing the webhooks_write permission"):
        asyncio.run(elevenlabs.validate_key("xi-restricted"))

    # With the permission the empty body is refused for its content, and the key passes.
    webhook_status["code"] = 422
    assert asyncio.run(elevenlabs.validate_key("xi-full")) == "ElevenLabs connected."


def test_a_key_is_checked_with_the_provider_before_it_is_stored(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    monkeypatch.setattr(elevenlabs, "validate_key", AsyncMock(side_effect=TelephonyError("ElevenLabs rejected the API key.")))
    refused = client.put("/api/phone/accounts/elevenlabs", json={"api_key": "wrong"})
    assert refused.status_code == 400 and "rejected" in refused.json()["detail"]
    assert not next(a for a in client.get("/api/phone/accounts").json() if a["provider"] == "elevenlabs")["stored"]

    monkeypatch.setattr(elevenlabs, "validate_key", AsyncMock(return_value="ElevenLabs connected."))
    saved = client.put("/api/phone/accounts/elevenlabs", json={"api_key": "xi-abcdef1234"}).json()
    assert saved["configured"] and saved["secret_hint"] == "…1234"
    assert client.put("/api/phone/accounts/twilio", json={"account_sid": "nope", "auth_token": ""}).status_code == 400


def test_a_line_carries_the_agent_into_elevenlabs(authenticated_client: TestClient, provisioning):
    _, _, line = _line(authenticated_client, transfer_number="+57 300 555 0000")
    assert line["status"] == "connected" and line["last_error"] is None
    with SessionLocal() as db:
        assert db.get(PhoneChannel, line["id"]).agent.transfer_number == "+573005550000"

    config = provisioning["agent_body"]["conversation_config"]
    prompt = config["agent"]["prompt"]
    # ElevenLabs thinks with its Realtime model and the agent's own prompt:
    # its job, its offer, who is calling and how to speak on the phone.
    assert config["realtime_model"] == "eleven_realtime_v1_mini" and prompt["llm"] == phone_calls.REALTIME_IDLE_LLM
    assert prompt["custom_llm"] is None
    assert "Agenda citas." in prompt["prompt"] and "Limpieza: $80.000." in prompt["prompt"]
    assert "{{system__caller_id}}" in prompt["prompt"] and "LLAMADA TELEFÓNICA" in prompt["prompt"]
    assert "transfer_to_number" in prompt["prompt"]
    # The clock comes from ElevenLabs on each call, in the client's timezone.
    assert prompt["timezone"] == "America/Bogota" and "2026-" not in prompt["prompt"]
    assert set(prompt["built_in_tools"]) == {"end_call", "transfer_to_number"}
    transfer = prompt["built_in_tools"]["transfer_to_number"]["params"]["transfers"][0]
    assert transfer["transfer_destination"] == {"type": "phone", "phone_number": "+573005550000"}
    assert transfer["condition"] == phone_calls.TRANSFER_WHEN["es"]
    assert config["agent"]["first_message"] == "¡Hola! Hablas con Dentix." and config["agent"]["language"] == "es"
    turn = config["turn"]
    assert turn["speculative_turn"] is True and turn["soft_timeout_config"]["message"] == phone_calls.FILLERS["es"]
    # The call's own audio, without converting it on every turn.
    assert config["asr"]["user_input_audio_format"] == "ulaw_8000" and config["tts"]["agent_output_audio_format"] == "ulaw_8000"
    platform = provisioning["agent_body"]["platform_settings"]
    assert platform["workspace_overrides"]["webhooks"]["post_call_webhook_id"] == "wh_1"
    # When a call comes in ElevenLabs asks who is calling, with the account's
    # secret; a call that does not ask reads empty details instead.
    start = platform["workspace_overrides"]["conversation_initiation_client_data_webhook"]
    assert start["url"].endswith(f"/api/public/phone/lines/{_public_id(line['id'])}/start")
    assert start["request_headers"] == {phone_calls.TOKEN_HEADER: {"secret_id": "sec_1"}}
    assert platform["overrides"]["enable_conversation_initiation_client_data_from_webhook"] is True
    assert config["agent"]["dynamic_variables"]["dynamic_variable_placeholders"] == {"caller_context": "", "pending_details": ""}
    assert "{{caller_context}}" in prompt["prompt"] and "{{pending_details}}" in prompt["prompt"]
    # With a transfer number the person takes the call there: no hand-over tool.
    assert "escalate_to_human" not in _tools(provisioning)
    with SessionLocal() as db:
        assert db.get(PhoneChannel, line["id"]).elevenlabs_phone_number_id == "phnum_1"


def test_a_model_outside_realtime_runs_in_custom_mode(authenticated_client: TestClient, provisioning):
    _line(authenticated_client, model="gemini-3.8-flash")
    config = provisioning["agent_body"]["conversation_config"]
    assert config["realtime_model"] is None and config["agent"]["prompt"]["llm"] == "gemini-3.8-flash"


def test_a_voice_agent_thinks_with_a_voice_model(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Dentix", "is_active": True}).json()
    refused = client.post("/api/agents", json={
        "client_id": customer["id"], "model": "google/gemini-3.5-flash-lite", "name": "Sofía", "kind": "voice",
    })
    assert refused.status_code == 422 and "Realtime Mini" in refused.json()["detail"]
    models = client.get("/api/phone/models").json()
    assert models[0] == {"id": "eleven_realtime_v1_mini", "label": "Realtime Mini", "realtime": True}


def test_a_line_that_cannot_connect_says_why(authenticated_client: TestClient, provisioning, monkeypatch):
    monkeypatch.setattr(elevenlabs, "import_twilio_number", AsyncMock(side_effect=TelephonyError("ElevenLabs refused the request (400): bad number")))
    _, _, line = _line(authenticated_client)
    assert line["status"] == "error" and "bad number" in line["last_error"]


def test_the_end_of_call_report_keeps_the_call(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _line(client)
    url = _webhook_url()
    report = _report("conv_9", [
        {"role": "agent", "message": "¡Hola! Hablas con Dentix.", "time_in_call_secs": 0},
        {"role": "user", "message": "Quiero una limpieza", "time_in_call_secs": 4},
        {"role": "user", "message": "...", "time_in_call_secs": 5},
        {"role": "agent", "message": "Claro, ¿para qué día?", "time_in_call_secs": 6},
    ], call_duration_secs=66, cost=880, termination_reason="Client disconnected", charging={
        "platform_price": 0.105, "llm_price": 0.004,
        "llm_usage": {"irreversible_generation": {"model_usage": {"eleven_realtime_v1_mini": {
            "input": {"tokens": 1200}, "input_cache_read": {"tokens": 800}, "input_cache_write": {"tokens": 100},
            "output_total": {"tokens": 90},
        }}}},
    })

    raw, headers = _signed(report, secret="wrong")
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report, at=int(time.time()) - 3 * 3600)
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report)
    assert client.post(url, content=raw, headers=headers).status_code == 200
    assert client.post(url, content=raw, headers=headers).status_code == 200  # a retry changes nothing
    with SessionLocal() as db:
        call = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == "conv_9"))
        assert (call.duration_seconds, float(call.cost_usd), call.summary) == (66, 0.109, "The caller booked a cleaning.")
        # The call is one usage record, priced in USD, that Reports lists with the conversation.
        usage = db.scalar(select(UsageRecord).where(UsageRecord.conversation_id == call.conversation_id))
        assert (usage.provider, usage.model, usage.purpose) == ("elevenlabs", "eleven_realtime_v1_mini", "call")
        assert (usage.input_tokens, usage.cached_tokens, usage.output_tokens, usage.duration_ms) == (2100, 800, 90, 66_000)
        assert round(float(usage.cost_usd), 3) == 0.109
        assert db.scalar(select(UsageRecord.id).where(UsageRecord.purpose == "call").offset(1)) is None  # the retry added none
        conversation = db.get(Conversation, call.conversation_id)
        assert conversation.status == "resolved" and conversation.contact.phone == "573001112233"
        # The transcript, without the turns nothing was heard in, each at the moment it was said.
        said = db.scalars(select(Message).where(Message.conversation_id == conversation.id, Message.kind == "message").order_by(Message.created_at)).all()
        assert [(m.role, m.content) for m in said] == [
            ("assistant", "¡Hola! Hablas con Dentix."), ("user", "Quiero una limpieza"), ("assistant", "Claro, ¿para qué día?"),
        ]
        assert int(said[1].created_at.timestamp()) == 1_800_000_004


def test_every_call_is_its_own_conversation(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _line(client)
    url = _webhook_url()
    for call_id in ("conv_a", "conv_b"):
        raw, headers = _signed(_report(call_id, [{"role": "user", "message": "Hola", "time_in_call_secs": 2}]))
        assert client.post(url, content=raw, headers=headers).status_code == 200
    with SessionLocal() as db:
        conversations = db.scalars(select(Conversation).where(Conversation.channel == "phone")).all()
        assert len(conversations) == 2 and len({c.contact_id for c in conversations}) == 1


def test_removing_a_line_takes_it_out_of_elevenlabs_and_keeps_its_calls(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, _, line = _line(client)
    raw, headers = _signed(_report("conv_1", [{"role": "user", "message": "Hola", "time_in_call_secs": 2}]))
    assert client.post(_webhook_url(), content=raw, headers=headers).status_code == 200
    tool_ids = set(provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]["tool_ids"])
    assert tool_ids
    assert client.delete(f"/api/phone/lines/{line['id']}").status_code == 204
    elevenlabs.release_number.assert_awaited_with("xi-key", "phnum_1")
    elevenlabs.delete_agent.assert_awaited_with("xi-key", "agent_el_1")
    assert {call.args[1] for call in elevenlabs.delete_tool.await_args_list} == tool_ids
    with SessionLocal() as db:
        assert db.scalar(select(Conversation).where(Conversation.channel == "phone")) is not None


def test_voice_and_chat_agents_keep_to_their_channels(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    customer, voice_agent, line = _line(client)
    chat_agent = client.post("/api/agents", json={
        "client_id": customer["id"], "provider": "openrouter", "model": "openai/gpt-4.1", "name": "Chat",
        "instructions": "", "personality": "", "is_active": True,
    }).json()
    assert chat_agent["kind"] == "chat"
    refused = client.put(f"/api/phone/lines/{line['id']}", json={"agent_id": chat_agent["id"]})
    assert refused.status_code == 400 and "voice agent" in refused.json()["detail"]
    refused = client.put(f"/api/webchat/channels/{customer['id']}", json={"agent_id": voice_agent["id"], "is_enabled": True})
    assert refused.status_code == 400 and "phone calls only" in refused.json()["detail"]


def test_changing_the_agent_or_its_client_rewrites_the_lines(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    customer, agent, _ = _line(client)
    assert client.patch(f"/api/agents/{agent['id']}", json={"voice_id": "voice_2", "greeting": "Hola, Dentix."}).status_code == 200
    config = provisioning["agent_body"]["conversation_config"]
    assert config["tts"]["voice_id"] == "voice_2" and config["agent"]["first_message"] == "Hola, Dentix."

    assert client.patch(f"/api/agents/{agent['id']}", json={"brief_policies": "Abrimos de 8 a 6."}).status_code == 200
    assert "Abrimos de 8 a 6." in provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]["prompt"]

    assert client.patch(f"/api/clients/{customer['id']}", json={"name": "Dentix Norte"}).status_code == 200
    assert "Dentix Norte" in provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]["prompt"]

    # A setting the call does not carry leaves ElevenLabs alone.
    pushed = len(provisioning["bodies"])
    assert client.patch(f"/api/agents/{agent['id']}", json={"temperature": 0.3}).status_code == 200
    assert len(provisioning["bodies"]) == pushed


def test_a_deployment_can_lend_its_elevenlabs_account(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    lent = {"elevenlabs": {"api_key": "xi-deployment"}}
    phone_calls.register_call_account_fallback(lambda db, agency_id, provider: lent.get(provider))
    try:
        account = next(a for a in client.get("/api/phone/accounts").json() if a["provider"] == "elevenlabs")
        assert (account["configured"], account["stored"], account["source"]) == (True, False, "deployment")

        # A line connects on the lent key, and the agency's row keeps its webhook.
        assert client.put("/api/phone/accounts/twilio", json={"account_sid": "AC123", "auth_token": "tok"}).status_code == 200
        customer = client.post("/api/clients", json={"name": "Dentix", "is_active": True}).json()
        agent = client.post("/api/agents", json={"client_id": customer["id"], "model": "eleven_realtime_v1_mini", "name": "Sofía", "kind": "voice", "voice_id": "voice_1"}).json()
        line = client.post(f"/api/phone/clients/{customer['id']}/lines", json={
            "agent_id": agent["id"], "provider": "twilio", "provider_number_id": "PN1", "phone_number": "+15550001111",
        }).json()
        assert line["status"] == "connected"
        assert elevenlabs.create_webhook.await_args.args[0] == "xi-deployment"
        with SessionLocal() as db:
            row = db.scalar(select(phone_calls.CallAccount).where(phone_calls.CallAccount.provider == "elevenlabs"))
            assert row.webhook_id == "wh_1" and row.encrypted_secret == ""
        # Removing the lent account is not the agency's to do; storing its own takes over.
        assert client.delete("/api/phone/accounts/elevenlabs").status_code == 204
        assert client.put("/api/phone/accounts/elevenlabs", json={"api_key": "xi-own"}).json()["source"] == "agency"
        with SessionLocal() as db:
            assert db.scalar(select(phone_calls.CallAccount).where(phone_calls.CallAccount.provider == "elevenlabs")).webhook_id is None
    finally:
        phone_calls.register_call_account_fallback(None)


def test_a_voice_agent_says_when_and_where_a_call_goes_to_a_person(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, agent, _ = _line(client)
    prompt = provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]
    # Without a number nobody takes the call: the case goes to a person, who
    # calls back, even with no team to route it to.
    assert "transfer_to_number" not in prompt["built_in_tools"] and "una persona lo va a contactar" in prompt["prompt"]
    assert "escalate_to_human" in _tools(provisioning)

    refused = client.patch(f"/api/agents/{agent['id']}", json={"transfer_number": "300 555"})
    assert refused.status_code == 422 and "country code" in refused.json()["detail"]
    saved = client.patch(f"/api/agents/{agent['id']}", json={"transfer_number": "+57 300 555 0000", "transfer_when": "Si pide un descuento."})
    assert saved.json()["transfer_number"] == "+573005550000"
    transfer = provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]["built_in_tools"]["transfer_to_number"]
    assert transfer["params"]["transfers"][0]["condition"] == "Si pide un descuento."


def test_an_agent_without_a_voice_speaks_with_the_default_one(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, agent, line = _line(client)
    assert client.patch(f"/api/agents/{agent['id']}", json={"voice_id": "", "voice_name": ""}).status_code == 200
    assert provisioning["agent_body"]["conversation_config"]["tts"]["voice_id"] == phone_calls.DEFAULT_VOICES["es"]
    with SessionLocal() as db:
        assert db.get(PhoneChannel, line["id"]).status == "connected"


def _call(client: TestClient, line_id: str, path: str, body: dict, token: str | None) -> httpx.Response:
    headers = {phone_calls.TOKEN_HEADER: token} if token else {}
    return client.post(f"/api/public/phone/lines/{_public_id(line_id)}/{path}", json=body, headers=headers)


def _tool_body(name: str, call_id: str = "conv_live", **args) -> dict:
    return {**args, phone_calls.CALL_ARG: call_id, phone_calls.CALLER_ARG: CALLER}


def _capture_name(client: TestClient, agent_id: str) -> None:
    saved = client.put(f"/api/agents/{agent_id}/capture", json={"enabled": True, "fields": [{"field_key": "name", "channels": ["phone"]}]})
    assert saved.status_code == 200, saved.text


def test_a_caller_already_on_file_is_known_when_the_call_comes_in(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    customer, agent, line = _line(client)
    _capture_name(client, agent["id"])
    token = provisioning["token"]

    assert _call(client, line["id"], "start", {"conversation_id": "conv_1", "caller_id": CALLER}, None).status_code == 401
    assert _call(client, line["id"], "start", {"conversation_id": "conv_1", "caller_id": CALLER}, "wrong").status_code == 401

    # A first call: nothing is known yet, so the name is still to ask for.
    first = _call(client, line["id"], "start", {"conversation_id": "conv_1", "caller_id": CALLER}, token).json()
    assert first["type"] == "conversation_initiation_client_data"
    assert "`name`" in first["dynamic_variables"]["pending_details"]
    # The call is in the inbox while it rings.
    with SessionLocal() as db:
        ringing = db.scalar(select(Conversation).where(Conversation.external_chat_id == "call:conv_1"))
        assert ringing.status == "open" and ringing.channel == "phone"
        ringing.contact.name = "Ana Gómez"
        db.commit()
    raw, headers = _signed(_report("conv_1", [{"role": "user", "message": "Hola", "time_in_call_secs": 2}]))
    assert client.post(_webhook_url(), content=raw, headers=headers).status_code == 200

    # The next call knows her, her last case, and has nothing left to ask.
    again = _call(client, line["id"], "start", {"conversation_id": "conv_2", "caller_id": CALLER}, token).json()["dynamic_variables"]
    assert "Ana Gómez" in again["caller_context"] and "Hola" in again["caller_context"]
    assert again["pending_details"] == ""


def test_a_caller_on_file_in_another_client_is_a_new_contact_here(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    customer, agent, line = _line(client)
    other = client.post("/api/clients", json={"name": "Pizzería", "is_active": True}).json()
    with SessionLocal() as db:
        db.add(Contact(client_id=other["id"], phone="573001112233", name="Ana de la pizzería"))
        db.commit()
    known = _call(client, line["id"], "start", {"conversation_id": "conv_x", "caller_id": CALLER}, provisioning["token"]).json()
    # Contacts belong to each client: the number is somebody else's contact.
    assert "Ana de la pizzería" not in known["dynamic_variables"]["caller_context"]


def test_the_agent_saves_what_the_caller_says_and_hands_the_case_over(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, agent, line = _line(client)
    _capture_name(client, agent["id"])
    assert provisioning["refreshed"] == [agent["id"]]  # the capture change is written to the line soon
    _resync(line["id"])
    tools = _tools(provisioning)
    save = tools["save_contact_field"]
    schema = save["api_schema"]["request_body_schema"]
    # The model fills the detail; ElevenLabs fills which call and who is calling.
    assert schema["properties"]["field"]["enum"] == ["name"] and schema["required"] == ["field", "value"]
    assert schema["properties"][phone_calls.CALL_ARG] == {"type": "string", "dynamic_variable": "system__conversation_id"}
    assert save["api_schema"]["url"].endswith(f"/lines/{_public_id(line['id'])}/tools/save_contact_field")
    assert save["api_schema"]["request_headers"] == {phone_calls.TOKEN_HEADER: {"secret_id": "sec_1"}}

    token = provisioning["token"]
    assert _call(client, line["id"], "tools/save_contact_field", _tool_body("save_contact_field", field="name", value="Ana"), None).status_code == 401
    saved = _call(client, line["id"], "tools/save_contact_field", _tool_body("save_contact_field", field="name", value="Ana Gómez"), token)
    assert saved.status_code == 200 and "Saved name" in saved.json()["result"]
    refused = _call(client, line["id"], "tools/save_contact_field", _tool_body("save_contact_field", field="email", value="x"), token)
    assert "error" in refused.json()
    unknown = _call(client, line["id"], "tools/book_table", _tool_body("book_table"), token)
    assert "Unknown tool" in unknown.json()["error"]

    handed = _call(client, line["id"], "tools/escalate_to_human", _tool_body("escalate_to_human", reason="Quiere un descuento", trigger="human_request"), token)
    assert "Escalation registered" in handed.json()["result"]
    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.external_chat_id == "call:conv_live"))
        assert conversation.contact.name == "Ana Gómez" and conversation.mode == "human"
    # Hanging up leaves the case open for the person who calls back.
    raw, headers = _signed(_report("conv_live", [{"role": "user", "message": "Quiero hablar con alguien", "time_in_call_secs": 2}]))
    assert client.post(_webhook_url(), content=raw, headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(Conversation).where(Conversation.external_chat_id == "call:conv_live")).status == "open"


def test_the_agent_uses_its_own_tools_on_a_call(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, agent, line = _line(client)
    created = client.post(f"/api/agents/{agent['id']}/tools", json={
        "type": "http", "name": "book_slot", "description": "Book a cleaning.", "url": "https://example.com/book", "http_method": "POST",
        "body_params": [{"name": "day", "type": "string", "description": "The day", "required": True}, {"name": "people", "type": "integer"}],
        "timeout_seconds": 20,
    })
    assert created.status_code == 201, created.text
    assert provisioning["refreshed"] == [agent["id"]]
    _resync(line["id"])
    book = _tools(provisioning)["book_slot"]
    assert book["response_timeout_secs"] == 25 and book["pre_tool_speech"] == "auto"
    properties = book["api_schema"]["request_body_schema"]["properties"]
    # Every argument carries a description, which ElevenLabs requires.
    assert properties["day"] == {"type": "string", "description": "The day"} and properties["people"]["description"] == "people"

    received = {}

    async def execute(tool, args):
        received.update(args)
        return "Booked for Monday.", False, []

    monkeypatch.setattr("app.services.tools.loop.execute_http_tool", execute)
    done = _call(client, line["id"], "tools/book_slot", _tool_body("book_slot", day="lunes", people=2), provisioning["token"])
    assert done.json() == {"result": "Booked for Monday."}
    # The tool gets the model's arguments and nothing of the call's own.
    assert received == {"day": "lunes", "people": 2}

    # An unchanged tool is not written again; a removed one leaves the agent.
    writes = provisioning["tool_writes"]
    _resync(line["id"])
    assert provisioning["tool_writes"] == writes
    tool_id = created.json()["id"]
    assert client.delete(f"/api/agents/{agent['id']}/tools/{tool_id}").status_code == 204
    _resync(line["id"])
    assert "book_slot" not in _tools(provisioning)
    assert elevenlabs.delete_tool.await_count == 1


def test_short_documents_ride_in_the_prompt_and_long_ones_are_looked_up(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, agent, line = _line(client)
    with SessionLocal() as db:
        db.add(KnowledgeDocument(agent_id=agent["id"], filename="precios.pdf", file_data=b"", status="processed",
                                 extracted_text="Blanqueamiento: $300.000."))
        db.commit()
    _resync(line["id"])
    prompt = provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]
    assert "Blanqueamiento: $300.000." in prompt["prompt"] and "search_knowledge" not in _tools(provisioning)

    with SessionLocal() as db:
        long_text = "\n\n".join(f"Servicio {n}: ortodoncia invisible, sesión {n}." for n in range(1200))
        db.add(KnowledgeDocument(agent_id=agent["id"], filename="manual.pdf", file_data=b"", status="processed", extracted_text=long_text))
        db.commit()
    _resync(line["id"])
    prompt = provisioning["agent_body"]["conversation_config"]["agent"]["prompt"]
    assert "Servicio 5:" not in prompt["prompt"] and "search_knowledge" in prompt["prompt"]
    assert "search_knowledge" in _tools(provisioning)

    async def no_embeddings(db, agent, query):
        return None

    monkeypatch.setattr("app.services.knowledge._semantic_search", no_embeddings)
    found = _call(client, line["id"], "tools/search_knowledge", _tool_body("search_knowledge", query="blanqueamiento"), provisioning["token"])
    assert "Blanqueamiento: $300.000." in found.json()["result"]


def test_the_transcript_lists_the_tools_the_agent_used(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _line(client)
    report = _report("conv_t", [
        {"role": "user", "message": "Me llamo Ana", "time_in_call_secs": 2},
        {"role": "agent", "message": None, "time_in_call_secs": 3, "tool_calls": [{
            "request_id": "r1", "tool_name": "save_contact_field",
            "params_as_json": json.dumps({"field": "name", "value": "Ana", phone_calls.CALL_ARG: "conv_t"}),
        }]},
        {"role": "agent", "message": None, "time_in_call_secs": 3, "tool_results": [{
            "request_id": "r1", "tool_name": "save_contact_field", "result_value": "Saved name.", "is_error": False,
        }]},
        {"role": "agent", "message": "Gracias, Ana.", "time_in_call_secs": 4},
    ])
    raw, headers = _signed(report)
    assert client.post(_webhook_url(), content=raw, headers=headers).status_code == 200
    with SessionLocal() as db:
        said = db.scalars(select(Message).join(Conversation).where(
            Conversation.external_chat_id == "call:conv_t", Message.role == "assistant")).all()
        assert [m.content for m in said] == ["Gracias, Ana."]
        assert said[0].tool_calls == [{"name": "save_contact_field", "arguments": {"field": "name", "value": "Ana"},
                                       "result_preview": "Saved name.", "is_error": False}]


def test_a_call_that_never_connects_closes_its_conversation(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, _, line = _line(client)
    _call(client, line["id"], "start", {"conversation_id": "conv_f", "caller_id": CALLER}, provisioning["token"])
    raw, headers = _signed({"type": "call_initiation_failure", "data": {"conversation_id": "conv_f", "failure_reason": "busy"}})
    assert client.post(_webhook_url(), content=raw, headers=headers).status_code == 200
    with SessionLocal() as db:
        call = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == "conv_f"))
        assert call.end_reason == "busy" and db.get(Conversation, call.conversation_id).status == "resolved"


def test_a_tool_schema_is_written_the_way_elevenlabs_takes_it():
    schema = {"type": "object", "required": ["to", "ghost"], "properties": {
        "to": {"type": ["string", "null"], "title": "Recipient"},
        "labels": {"type": "array", "items": {"type": "string"}},
        "payload": {"type": "object"},
        "when": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        "kind": {"type": "string", "enum": ["a", "b"], "description": "Kind"},
        "where": {"type": "object", "properties": {"city": {"type": "string"}}},
    }}
    body = phone_calls._object_schema(schema)
    assert body["required"] == ["to"]
    assert body["properties"]["to"] == {"type": "string", "description": "Recipient"}
    assert body["properties"]["labels"] == {"type": "array", "description": "labels", "items": {"type": "string", "description": "labels"}}
    # What ElevenLabs cannot express is asked as text, and read back.
    assert body["properties"]["payload"] == {"type": "string", "description": "payload (as JSON)"}
    assert body["properties"]["when"]["type"] == "string"
    assert body["properties"]["kind"]["enum"] == ["a", "b"]
    assert body["properties"]["where"]["properties"]["city"]["description"] == "city"
    spec = phone_calls.ToolSpec("send", "", schema)
    assert phone_calls._decoded(spec, {"payload": '{"a": 1}', "to": "x"}) == {"payload": {"a": 1}, "to": "x"}


def test_a_burst_of_changes_writes_the_lines_once(monkeypatch):
    written = []

    async def resync(agent_id):
        written.append(agent_id)

    monkeypatch.setattr(phone_calls, "_resync_agent", resync)
    monkeypatch.setattr(phone_calls, "RESYNC_DELAY_SECONDS", 0.05)

    async def burst():
        for _ in range(5):
            phone_calls._schedule_resync("agent_1")
        phone_calls._schedule_resync("agent_2")
        await asyncio.sleep(0.2)

    asyncio.run(burst())
    assert sorted(written) == ["agent_1", "agent_2"]


def test_a_deployment_can_say_where_an_agency_is_called_back(authenticated_client: TestClient, provisioning):
    phone_calls.register_public_base(lambda db, agency_id: "https://dentix.example.com")
    try:
        _, _, line = _line(authenticated_client)
        start = provisioning["agent_body"]["platform_settings"]["workspace_overrides"]["conversation_initiation_client_data_webhook"]
        assert start["url"] == f"https://dentix.example.com/api/public/phone/lines/{_public_id(line['id'])}/start"
        assert elevenlabs.create_webhook.await_args.args[2].startswith("https://dentix.example.com/api/public/phone/accounts/")
    finally:
        phone_calls.register_public_base(None)
