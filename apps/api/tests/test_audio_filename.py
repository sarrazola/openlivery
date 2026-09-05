from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.routers import conversations as conversations_router
from app.services import ai as ai_service
from app.services import whatsapp_inbound
from app.services.media import audio_filename


def test_audio_filename_follows_the_mime():
    assert audio_filename("audio/mp4") == "audio.m4a"
    assert audio_filename("audio/webm;codecs=opus") == "audio.webm"
    assert audio_filename("audio/mpeg") == "audio.mp3"
    assert audio_filename("audio/ogg") == "audio.ogg"
    assert audio_filename(None) == "audio.ogg"
    assert audio_filename("application/octet-stream") == "audio.ogg"


def test_playground_voice_note_is_transcribed_under_its_real_container(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Pizza Co"}).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Memo", "audio_enabled": True, "is_active": True},
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()

    transcribe = AsyncMock(return_value="quiero una pizza mediana")
    monkeypatch.setattr(whatsapp_inbound, "transcribe_audio", transcribe)
    completion = AsyncMock(return_value=ai_service.Completion(text="Claro"))
    monkeypatch.setattr(conversations_router, "run_completion", completion)

    # Safari records voice notes as fragmented mp4; the provider must see .m4a, not .ogg.
    sent = client.post(
        f"/api/conversations/{conversation['id']}/media",
        files={"file": ("voice-note.m4a", b"\x00\x00\x00$ftypisom-fake", "audio/mp4")},
    )
    assert sent.status_code == 200, sent.text
    args = transcribe.await_args.args
    assert args[4] == "audio.m4a" and args[5] == "audio/mp4"
    prompt_messages = completion.await_args.args[4]
    assert any("quiero una pizza mediana" in str(message.get("content")) for message in prompt_messages)
