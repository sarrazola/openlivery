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
from app.models import Conversation, Message, PhoneCall, PhoneChannel
from app.services import phone_calls
from app.services.telephony import TelephonyError, elevenlabs

WEBHOOK_SECRET = "wsec_test"
CALLER = "+573001112233"


@pytest.fixture
def provisioning(monkeypatch):
    """ElevenLabs as the tests see it: every call recorded, nothing on the network."""
    calls: dict = {"bodies": []}

    async def upsert_agent(api_key, agent_id, body):
        calls["agent_body"] = body
        calls["bodies"].append(body)
        return agent_id or "agent_el_1"

    monkeypatch.setattr(elevenlabs, "validate_key", AsyncMock(return_value="ElevenLabs connected."))
    monkeypatch.setattr(elevenlabs, "ensure_voice", AsyncMock(return_value="Sofía"))
    monkeypatch.setattr(elevenlabs, "create_webhook", AsyncMock(return_value=("wh_1", WEBHOOK_SECRET)))
    monkeypatch.setattr(elevenlabs, "upsert_agent", upsert_agent)
    monkeypatch.setattr(elevenlabs, "import_twilio_number", AsyncMock(return_value="phnum_1"))
    monkeypatch.setattr(elevenlabs, "assign_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "release_number", AsyncMock())
    monkeypatch.setattr(elevenlabs, "delete_agent", AsyncMock())
    monkeypatch.setattr(phone_calls.carriers, "validate", AsyncMock(return_value="Twilio connected: Dentix."))
    return calls


def _line(client: TestClient, *, model: str = "eleven_realtime_v1_mini", **overrides) -> tuple[dict, dict, dict]:
    assert client.put("/api/phone/accounts/elevenlabs", json={"api_key": "xi-key"}).status_code == 200
    assert client.put("/api/phone/accounts/twilio", json={"account_sid": "AC123", "auth_token": "tok"}).status_code == 200
    customer = client.post("/api/clients", json={"name": "Dentix", "is_active": True, "timezone": "America/Bogota"}).json()
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "model": model, "name": "Sofía",
        "instructions": "Agenda citas.", "brief_products": "Limpieza: $80.000.", "personality": "", "is_active": True,
        "kind": "voice", "voice_id": "voice_1", "greeting": "¡Hola! Hablas con Dentix.",
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
    assert line["transfer_number"] == "+573005550000"

    config = provisioning["agent_body"]["conversation_config"]
    prompt = config["agent"]["prompt"]
    # ElevenLabs thinks with its Realtime model and the agent's own prompt:
    # its job, its offer, who is calling and how to speak on the phone.
    assert config["realtime_model"] == "eleven_realtime_v1_mini" and prompt["llm"] == phone_calls.REALTIME_IDLE_LLM
    assert "custom_llm" not in prompt
    assert "Agenda citas." in prompt["prompt"] and "Limpieza: $80.000." in prompt["prompt"]
    assert "{{system__caller_id}}" in prompt["prompt"] and "LLAMADA TELEFÓNICA" in prompt["prompt"]
    assert "transfer_to_number" in prompt["prompt"]
    # The clock comes from ElevenLabs on each call, in the client's timezone.
    assert prompt["timezone"] == "America/Bogota" and "2026-" not in prompt["prompt"]
    assert set(prompt["built_in_tools"]) == {"end_call", "transfer_to_number"}
    destination = prompt["built_in_tools"]["transfer_to_number"]["params"]["transfers"][0]["transfer_destination"]
    assert destination == {"type": "phone", "phone_number": "+573005550000"}
    assert config["agent"]["first_message"] == "¡Hola! Hablas con Dentix." and config["agent"]["language"] == "es"
    turn = config["turn"]
    assert turn["speculative_turn"] is True and turn["soft_timeout_config"]["message"] == phone_calls.FILLERS["es"]
    # The call's own audio, without converting it on every turn.
    assert config["asr"]["user_input_audio_format"] == "ulaw_8000" and config["tts"]["agent_output_audio_format"] == "ulaw_8000"
    assert provisioning["agent_body"]["platform_settings"]["workspace_overrides"]["webhooks"]["post_call_webhook_id"] == "wh_1"
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
    ], call_duration_secs=66, cost=880, termination_reason="Client disconnected")

    raw, headers = _signed(report, secret="wrong")
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report, at=int(time.time()) - 3 * 3600)
    assert client.post(url, content=raw, headers=headers).status_code == 401
    raw, headers = _signed(report)
    assert client.post(url, content=raw, headers=headers).status_code == 200
    assert client.post(url, content=raw, headers=headers).status_code == 200  # a retry changes nothing
    with SessionLocal() as db:
        call = db.scalar(select(PhoneCall).where(PhoneCall.external_call_id == "conv_9"))
        assert (call.duration_seconds, call.cost_credits, call.summary) == (66, 880, "The caller booked a cleaning.")
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
