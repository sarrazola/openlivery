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
from app.models import Conversation, Message, PhoneCall, PhoneChannel, UsageRecord
from app.services import ai as ai_service
from app.services import phone_calls
from app.services.telephony import TelephonyError, elevenlabs

WEBHOOK_SECRET = "wsec_test"
CALLER = "+573001112233"


def _marker(call_id: str = "conv_1", caller: str = CALLER) -> str:
    return f"Task description: ...\nopenlivery-call conversation={call_id} caller={caller} called=+15550001111\n..."


def _body(turns: list[dict], *, call_id: str = "conv_1", tools: list | None = None) -> dict:
    return {
        "model": "google/gemini-3.5-flash-lite",
        "stream": True,
        "messages": [{"role": "system", "content": _marker(call_id)}, *turns],
        "tools": tools if tools is not None else [
            {"type": "function", "function": {"name": "end_call", "description": "End the call", "parameters": {"type": "object", "properties": {}}}},
        ],
    }


def _chunks(response) -> list[dict]:
    events = [line[len("data: "):] for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    return [json.loads(event) for event in events[:-1]]


def _spoken(chunks: list[dict]) -> str:
    return "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"])


@pytest.fixture
def provisioning(monkeypatch):
    """ElevenLabs as the tests see it: every call recorded, nothing on the network."""
    calls: dict = {}

    async def ensure_secret(api_key, name, value):
        calls["secret"] = value
        return "sec_1"

    async def upsert_agent(api_key, agent_id, body):
        calls["agent_body"] = body
        return agent_id or "agent_el_1"

    monkeypatch.setattr(elevenlabs, "validate_key", AsyncMock(return_value="ElevenLabs connected."))
    monkeypatch.setattr(elevenlabs, "ensure_voice", AsyncMock(return_value="Sofía"))
    monkeypatch.setattr(elevenlabs, "create_webhook", AsyncMock(return_value=("wh_1", WEBHOOK_SECRET)))
    monkeypatch.setattr(elevenlabs, "ensure_secret", ensure_secret)
    monkeypatch.setattr(elevenlabs, "upsert_agent", upsert_agent)
    monkeypatch.setattr(elevenlabs, "import_twilio_number", AsyncMock(return_value="phnum_1"))
    monkeypatch.setattr(elevenlabs, "assign_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "release_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "delete_agent", AsyncMock())
    monkeypatch.setattr(elevenlabs, "delete_secret", AsyncMock())
    monkeypatch.setattr(phone_calls.carriers, "validate", AsyncMock(return_value="Twilio connected: Dentix."))
    return calls


def _line(client: TestClient, **overrides) -> tuple[dict, dict, dict]:
    assert client.put("/api/phone/accounts/elevenlabs", json={"api_key": "xi-key"}).status_code == 200
    assert client.put("/api/phone/accounts/twilio", json={"account_sid": "AC123", "auth_token": "tok"}).status_code == 200
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    customer = client.post("/api/clients", json={"name": "Dentix", "is_active": True}).json()
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "provider": "openrouter", "model": "google/gemini-3.5-flash-lite", "name": "Sofía",
        "instructions": "Agenda citas.", "personality": "", "is_active": True,
        "kind": "voice", "voice_id": "voice_1", "greeting": "¡Hola! Hablas con Dentix.",
    }).json()
    body = {
        "agent_id": agent["id"], "provider": "twilio", "provider_number_id": "PN1", "phone_number": "+15550001111",
        **overrides,
    }
    created = client.post(f"/api/phone/clients/{customer['id']}/lines", json=body)
    assert created.status_code == 201, created.text
    return customer, agent, created.json()


def _turn(client: TestClient, line: dict, secret: str, body: dict):
    with SessionLocal() as db:
        public_id = db.get(PhoneChannel, line["id"]).public_id
    return client.post(
        f"/api/public/phone/lines/{public_id}/llm/chat/completions", json=body, headers={"Authorization": f"Bearer {secret}"}
    )


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


def test_adding_a_line_sets_it_up_at_elevenlabs(authenticated_client: TestClient, provisioning):
    _, _, line = _line(authenticated_client, transfer_number="+57 300 555 0000")
    assert line["status"] == "connected" and line["last_error"] is None
    assert line["transfer_number"] == "+573005550000"

    body = provisioning["agent_body"]
    prompt = body["conversation_config"]["agent"]["prompt"]
    assert prompt["prompt"] == phone_calls.MARKER
    assert prompt["llm"] == "custom-llm"
    assert prompt["custom_llm"]["url"].endswith("/llm") and "/api/public/phone/lines/" in prompt["custom_llm"]["url"]
    assert prompt["custom_llm"]["model_id"] == "google/gemini-3.5-flash-lite"
    assert prompt["custom_llm"]["api_key"] == {"secret_id": "sec_1"}
    assert set(prompt["built_in_tools"]) == {"end_call", "transfer_to_number"}
    destination = prompt["built_in_tools"]["transfer_to_number"]["params"]["transfers"][0]["transfer_destination"]
    assert destination == {"type": "phone", "phone_number": "+573005550000"}
    assert body["conversation_config"]["agent"]["first_message"] == "¡Hola! Hablas con Dentix."
    assert body["platform_settings"]["workspace_overrides"]["webhooks"]["post_call_webhook_id"] == "wh_1"
    # The bearer value is only in ElevenLabs; the line keeps its hash.
    with SessionLocal() as db:
        stored = db.get(PhoneChannel, line["id"])
        assert stored.llm_secret_hash == hashlib.sha256(provisioning["secret"].encode()).hexdigest()
        assert stored.elevenlabs_phone_number_id == "phnum_1"


def test_a_line_that_cannot_connect_says_why(authenticated_client: TestClient, provisioning, monkeypatch):
    monkeypatch.setattr(elevenlabs, "import_twilio_number", AsyncMock(side_effect=TelephonyError("ElevenLabs refused the request (400): bad number")))
    _, _, line = _line(authenticated_client)
    assert line["status"] == "error" and "bad number" in line["last_error"]


def test_a_call_is_answered_by_the_agent_and_streamed_back(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, agent, line = _line(client)
    captured = {}

    async def fake(db, agent_row, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None, model=None):
        captured.update(messages=messages, model=model, specs=[s.name for s in extra_specs or []], max_tokens=max_tokens)
        return ai_service.Completion(text="Claro que sí. ¿Para qué día?", input_tokens=12, output_tokens=8)

    monkeypatch.setattr(phone_calls, "run_completion", fake)
    greeting = {"role": "assistant", "content": "¡Hola! Hablas con Dentix."}
    first = _turn(client, line, provisioning["secret"], _body([greeting, {"role": "user", "content": "Quiero una cita"}]))
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("text/event-stream")
    chunks = _chunks(first)
    assert _spoken(chunks) == "Claro que sí. ¿Para qué día?"
    assert [c for c in chunks if c["choices"]][-1]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["usage"]["total_tokens"] == 20

    # The agent thinks with the line's model, its own prompt plus the phone rules,
    # and the call as ElevenLabs heard it; ElevenLabs' prompt is not passed on.
    assert captured["model"] == "google/gemini-3.5-flash-lite"
    assert "LLAMADA TELEFÓNICA" in captured["messages"][0]["content"] and "Task description" not in captured["messages"][0]["content"]
    assert captured["messages"][1:] == [greeting, {"role": "user", "content": "Quiero una cita"}]
    assert "end_call" in captured["specs"]

    second = _turn(client, line, provisioning["secret"], _body([
        greeting, {"role": "user", "content": "Quiero una cita"},
        {"role": "assistant", "content": "Claro que sí. ¿Para qué día?"}, {"role": "user", "content": "El martes"},
    ]))
    assert second.status_code == 200
    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.channel == "phone"))
        assert conversation.phone_channel_id is not None and conversation.contact.phone == "573001112233"
        said = [(m.role, m.content) for m in db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at))]
        assert said == [
            ("assistant", "¡Hola! Hablas con Dentix."), ("user", "Quiero una cita"),
            ("assistant", "Claro que sí. ¿Para qué día?"), ("user", "El martes"), ("assistant", "Claro que sí. ¿Para qué día?"),
        ]
        assert db.scalar(select(PhoneCall).where(PhoneCall.conversation_id == conversation.id)).caller == CALLER
        records = db.scalars(select(UsageRecord).where(UsageRecord.conversation_id == conversation.id)).all()
        assert len(records) == 2 and {r.model for r in records} == {"google/gemini-3.5-flash-lite"}


def test_every_call_is_its_own_conversation(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, _, line = _line(client)
    monkeypatch.setattr(phone_calls, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hola.")))
    for call_id in ("conv_a", "conv_b"):
        assert _turn(client, line, provisioning["secret"], _body([{"role": "user", "content": "Hola"}], call_id=call_id)).status_code == 200
    with SessionLocal() as db:
        conversations = db.scalars(select(Conversation).where(Conversation.channel == "phone")).all()
        assert len(conversations) == 2 and len({c.contact_id for c in conversations}) == 1


def test_a_turn_without_the_lines_secret_is_refused(authenticated_client: TestClient, provisioning):
    _, _, line = _line(authenticated_client)
    assert _turn(authenticated_client, line, "olv_wrong", _body([{"role": "user", "content": "Hola"}])).status_code == 401
    unnamed = {"messages": [{"role": "user", "content": "Hola"}]}
    assert _turn(authenticated_client, line, provisioning["secret"], unnamed).status_code == 400


def test_hanging_up_is_handed_back_to_elevenlabs(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, _, line = _line(client)

    async def fake(db, agent_row, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None, model=None):
        end_call = next(s for s in extra_specs if s.name == "end_call")
        result, is_error = end_call.handler({})
        assert not is_error and "Say one short sentence" in result
        return ai_service.Completion(text="Con gusto, que estés muy bien.")

    monkeypatch.setattr(phone_calls, "run_completion", fake)
    chunks = _chunks(_turn(client, line, provisioning["secret"], _body([{"role": "user", "content": "Eso era todo, gracias"}])))
    assert _spoken(chunks) == "Con gusto, que estés muy bien."
    calls = [c["choices"][0]["delta"]["tool_calls"][0] for c in chunks if c["choices"] and "tool_calls" in c["choices"][0]["delta"]]
    assert [call["function"]["name"] for call in calls] == ["end_call"]
    assert [c for c in chunks if c["choices"]][-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_a_transfer_puts_a_person_on_the_conversation(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, _, line = _line(client, transfer_number="+573005550000")
    transfer_tool = {"type": "function", "function": {"name": "transfer_to_number", "description": "Transfer", "parameters": {
        "type": "object", "properties": {"transfer_number": {"type": "string"}, "client_message": {"type": "string"},
                                         "agent_message": {"type": "string"}, "reason": {"type": "string"}}}}}

    async def fake(db, agent_row, base_url, api_key, messages, temperature=None, max_tokens=None, extra_specs=None, model=None):
        assert "escalate_to_human" not in [s.name for s in extra_specs]
        assert "transfer_to_number" in messages[0]["content"]
        transfer = next(s for s in extra_specs if s.name == "transfer_to_number")
        transfer.handler({"transfer_number": "+573005550000", "client_message": "Te comunico", "agent_message": "Quiere hablar con alguien", "reason": "pide una persona"})
        return ai_service.Completion(text="Te comunico con una persona.")

    monkeypatch.setattr(phone_calls, "run_completion", fake)
    chunks = _chunks(_turn(client, line, provisioning["secret"], _body([{"role": "user", "content": "Quiero hablar con alguien"}], tools=[transfer_tool])))
    names = [c["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] for c in chunks if c["choices"] and "tool_calls" in c["choices"][0]["delta"]]
    assert names == ["transfer_to_number"]
    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.channel == "phone"))
        assert conversation.mode == "human"
        assert any(m.activity and m.activity.get("event") == "escalated" for m in conversation.messages)


def _signed(payload: dict, secret: str = WEBHOOK_SECRET, at: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps(payload).encode()
    timestamp = str(at or int(time.time()))
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"ElevenLabs-Signature": f"t={timestamp},v0={digest}", "Content-Type": "application/json"}


def test_the_end_of_call_report_closes_the_call(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, _, line = _line(client)
    monkeypatch.setattr(phone_calls, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hola.")))
    _turn(client, line, provisioning["secret"], _body([{"role": "user", "content": "Hola"}], call_id="conv_9"))
    with SessionLocal() as db:
        account = phone_calls.get_account(db, db.get(PhoneChannel, line["id"]).agency_id, "elevenlabs")
        url = f"/api/public/phone/accounts/{account.public_id}/webhook"
    report = {"type": "post_call_transcription", "data": {
        "conversation_id": "conv_9", "agent_id": "agent_el_1",
        "metadata": {"call_duration_secs": 66, "cost": 880, "termination_reason": "Client disconnected"},
        "analysis": {"transcript_summary": "The caller asked about an appointment."},
    }}

    raw, headers = _signed(report, secret="wrong")
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report, at=int(time.time()) - 3 * 3600)
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report)
    assert client.post(url, content=raw, headers=headers).status_code == 200
    assert client.post(url, content=raw, headers=headers).status_code == 200  # a retry changes nothing
    with SessionLocal() as db:
        call = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == "conv_9"))
        assert (call.duration_seconds, call.cost_credits, call.summary) == (66, 880, "The caller asked about an appointment.")
        assert db.get(Conversation, call.conversation_id).status == "resolved"


def test_a_call_hung_up_before_any_turn_still_shows_up(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _line(client)
    with SessionLocal() as db:
        account = db.scalar(select(phone_calls.CallAccount).where(phone_calls.CallAccount.provider == "elevenlabs"))
        url = f"/api/public/phone/accounts/{account.public_id}/webhook"
    raw, headers = _signed({"type": "post_call_transcription", "data": {
        "conversation_id": "conv_short", "agent_id": "agent_el_1",
        "transcript": [{"role": "agent", "message": "¡Hola! Hablas con Dentix."}],
        "metadata": {"call_duration_secs": 4, "phone_call": {"external_number": CALLER}},
    }})
    assert client.post(url, content=raw, headers=headers).status_code == 200
    with SessionLocal() as db:
        call = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == "conv_short"))
        conversation = db.get(Conversation, call.conversation_id)
        assert conversation.status == "resolved" and conversation.contact.phone == "573001112233"
        assert [m.content for m in conversation.messages if m.kind == "message"] == ["¡Hola! Hablas con Dentix."]


def test_removing_a_line_takes_it_out_of_elevenlabs_and_keeps_its_calls(authenticated_client: TestClient, provisioning, monkeypatch):
    client = authenticated_client
    _, _, line = _line(client)
    monkeypatch.setattr(phone_calls, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hola.")))
    _turn(client, line, provisioning["secret"], _body([{"role": "user", "content": "Hola"}]))
    assert client.delete(f"/api/phone/lines/{line['id']}").status_code == 204
    elevenlabs.release_number.assert_awaited_with("xi-key", "phnum_1")
    elevenlabs.delete_agent.assert_awaited_with("xi-key", "agent_el_1")
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


def test_changing_the_voice_updates_the_lines_at_elevenlabs(authenticated_client: TestClient, provisioning):
    client = authenticated_client
    _, agent, _ = _line(client)
    assert client.patch(f"/api/agents/{agent['id']}", json={"voice_id": "voice_2", "greeting": "Hola, Dentix."}).status_code == 200
    tts = provisioning["agent_body"]["conversation_config"]
    assert tts["tts"]["voice_id"] == "voice_2" and tts["agent"]["first_message"] == "Hola, Dentix."
