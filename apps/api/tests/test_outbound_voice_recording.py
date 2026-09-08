"""Recorded AAC survives voice conversion and both outbound channel contracts."""

import asyncio
import base64
import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import audio, whatsapp

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg and ffprobe are required",
)


def _recording(tmp_path, *, fragmented=False):
    target = tmp_path / "voice-note.m4a"
    args = [
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
    ]
    if fragmented:
        args += ["-movflags", "+frag_keyframe+empty_moov"]
    subprocess.run([*args, str(target)], check=True)
    return target.read_bytes()


def _assert_voice(data, tmp_path):
    assert data.startswith(b"OggS")
    target = tmp_path / "outbound.ogg"
    target.write_bytes(data)
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target),
    ], check=True, capture_output=True, text=True)
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    assert stream["codec_name"] == "opus"
    assert stream["channels"] == 1
    assert stream["sample_rate"] == "48000"
    assert 9.9 <= float(info["format"]["duration"]) <= 10.2
    # Container headers alone are not audio, even when ffmpeg exits with zero.
    pcm = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(target), "-f", "s16le", "pipe:1",
    ], check=True, capture_output=True).stdout
    assert len(pcm) >= 9 * 48000 * 2
    assert any(pcm)


@pytest.mark.parametrize("fragmented", [False, True])
def test_recorded_mp4_voice_preserves_audio_duration_and_samples(tmp_path, fragmented):
    original = _recording(tmp_path, fragmented=fragmented)
    if not fragmented:
        # This placement is ordinary for native recorders and needs seeking.
        assert original.index(b"moov") > original.index(b"mdat")
    converted, mime = asyncio.run(audio.to_whatsapp_voice(original, "audio/mp4"))
    assert mime == "audio/ogg"
    assert converted != original
    _assert_voice(converted, tmp_path)
    assert asyncio.run(audio.audio_duration_seconds(converted)) == 10


@pytest.mark.parametrize("channel", ["whatsapp", "whatsapp_cloud"])
def test_both_outbound_channels_receive_valid_voice_media(tmp_path, monkeypatch, channel):
    original = _recording(tmp_path)
    bridge = AsyncMock(return_value={"external_message_id": "message-1"})
    upload = AsyncMock(return_value="media-1")
    send = AsyncMock(return_value="message-1")
    caption = AsyncMock(return_value="caption-1")
    monkeypatch.setattr(whatsapp, "bridge_command", bridge)
    monkeypatch.setattr(whatsapp, "upload_media", upload)
    monkeypatch.setattr(whatsapp, "send_media", send)
    monkeypatch.setattr(whatsapp, "send_text", caption)
    monkeypatch.setattr(whatsapp, "decrypt_secret", lambda value: "test-token")
    conversation = SimpleNamespace(
        channel=channel, whatsapp_channel_id="qr-line", whatsapp_cloud_channel_id="api-line",
        external_chat_id="573001234567",
    )
    db = SimpleNamespace(get=lambda model, key: SimpleNamespace(encrypted_access_token="encrypted", phone_number_id="phone-id", coexistence=False))
    result = asyncio.run(whatsapp.send_channel_media(
        db, conversation, kind="audio", data=original, mime="audio/mp4", filename="voice-note.m4a", caption="Listen to this",
    ))
    assert result == "message-1"
    if channel == "whatsapp":
        payload = bridge.call_args.args[2]
        assert payload["media_kind"] == "audio"
        assert payload["media_mime"] == "audio/ogg"
        assert payload["media_seconds"] == 10
        assert payload["filename"] == "voice-note.ogg"
        assert payload["text"] == "Listen to this"
        _assert_voice(base64.b64decode(payload["media_base64"]), tmp_path)
        upload.assert_not_called()
    else:
        _, _, converted, mime, filename = upload.call_args.args
        assert mime == "audio/ogg" and filename == "voice-note.ogg"
        _assert_voice(converted, tmp_path)
        assert send.call_args.args[3:5] == ("audio", "media-1")
        assert caption.call_args.args[-1] == "Listen to this"
        bridge.assert_not_called()


def test_portal_voice_upload_keeps_the_recording_original(authenticated_client, monkeypatch, tmp_path):
    import uuid

    from app.models import Conversation
    from conftest import TestingSession, customer_conversation
    from test_mobile_and_push import _client_with_portal, _sign_in

    client = authenticated_client
    customer = _client_with_portal(client)
    session = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()
    headers = {"Authorization": f"Bearer {session['token']}"}
    agent = client.post("/api/agents", json={
        "client_id": customer["id"], "name": "Assistant", "audio_enabled": False,
    }).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    conversation = customer_conversation(client, agent["id"])
    with TestingSession() as db:
        row = db.get(Conversation, uuid.UUID(conversation["id"]))
        row.channel = "whatsapp"
        row.whatsapp_channel_id = uuid.UUID(channel["id"])
        row.external_chat_id = "573001234567@s.whatsapp.net"
        row.mode = "human"
        db.commit()
    bridge = AsyncMock(return_value={"external_message_id": "voice-1"})
    monkeypatch.setattr(whatsapp, "bridge_command", bridge)
    original = _recording(tmp_path)
    path = f"/api/portal/{customer['portal_slug']}/conversations/{conversation['id']}"
    response = client.post(f"{path}/reply-media", headers=headers,
                           files={"file": ("voice-note.m4a", original, "audio/mp4")})
    assert response.status_code == 200
    attachment = response.json()["messages"][-1]["attachments"][0]
    assert attachment["kind"] == "audio" and attachment["mime"] == "audio/mp4"
    assert attachment["filename"] == "voice-note.m4a" and attachment["size_bytes"] == len(original)
    downloaded = client.get(f"{path}/attachments/{attachment['id']}", headers=headers)
    assert downloaded.status_code == 200 and downloaded.content == original
    converted = base64.b64decode(bridge.call_args.args[2]["media_base64"])
    _assert_voice(converted, tmp_path)
