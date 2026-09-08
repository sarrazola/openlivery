"""Native playback preserves original media and the portal authorization seam."""
import asyncio
import json
import shutil
import subprocess
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models import Message, MessageAttachment
from app.services import audio
from app.services.attachments import store_attachment
from conftest import TestingSession, customer_conversation
from test_mobile_and_push import _client_with_portal, _sign_in


def _setup(client, *, mime="audio/ogg"):
    customer = _client_with_portal(client)
    session = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()
    headers = {"Authorization": f"Bearer {session['token']}"}
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Assistant"}).json()
    conversation = customer_conversation(client, agent["id"])
    with TestingSession() as db:
        message = Message(conversation_id=uuid.UUID(conversation["id"]), role="user", content="")
        db.add(message)
        db.flush()
        attachment = store_attachment(db, message, data=b"original-media", mime=mime, filename="voice.ogg")
        db.commit()
        attachment_id = str(attachment.id)
    path = f"/api/portal/{customer['portal_slug']}/conversations/{conversation['id']}/attachments/{attachment_id}"
    return path, headers, attachment_id


def test_native_audio_variant_keeps_original(authenticated_client, monkeypatch):
    client = authenticated_client
    path, headers, attachment_id = _setup(client)
    converted = AsyncMock(return_value=b"playable-m4a")
    monkeypatch.setattr(audio, "to_native_audio", converted)
    original = client.get(path, headers=headers)
    assert original.status_code == 200 and original.content == b"original-media"
    assert original.headers["content-type"].startswith("audio/ogg")
    assert not converted.called
    playback = client.get(f"{path}?format=m4a", headers=headers)
    assert playback.status_code == 200 and playback.content == b"playable-m4a"
    assert playback.headers["content-type"].startswith("audio/mp4")
    assert playback.headers["cache-control"].startswith("private")
    assert playback.headers["x-content-type-options"] == "nosniff"
    converted.assert_awaited_once_with(b"original-media")
    with TestingSession() as db:
        original = db.get(MessageAttachment, uuid.UUID(attachment_id))
        assert original.data == b"original-media" and original.mime == "audio/ogg"


def test_native_audio_variant_checks_access_before_conversion(authenticated_client, monkeypatch):
    client = authenticated_client
    path, headers, _ = _setup(client)
    converted = AsyncMock(return_value=b"playable-m4a")
    monkeypatch.setattr(audio, "to_native_audio", converted)
    assert client.get(f"{path}?format=m4a").status_code == 401
    assert client.get(f"{path}?format=m4a", headers={"Authorization": "Bearer invalid"}).status_code == 401
    parts = path.split("/")
    parts[-1] = str(uuid.uuid4())
    assert client.get(f"{'/'.join(parts)}?format=m4a", headers=headers).status_code == 404
    other = client.post("/api/clients", json={"name": "Separate client"}).json()
    other_agent = client.post("/api/agents", json={"client_id": other["id"], "name": "Other assistant"}).json()
    other_conversation = customer_conversation(client, other_agent["id"])
    parts = path.split("/")
    parts[-3] = other_conversation["id"]
    assert client.get(f"{'/'.join(parts)}?format=m4a", headers=headers).status_code == 404
    converted.assert_not_called()


def test_audio_variant_rejects_invalid_format_and_media(authenticated_client, monkeypatch):
    path, headers, _ = _setup(authenticated_client, mime="image/png")
    converted = AsyncMock(return_value=b"playable-m4a")
    monkeypatch.setattr(audio, "to_native_audio", converted)
    assert authenticated_client.get(f"{path}?format=mp3", headers=headers).status_code == 422
    assert authenticated_client.get(f"{path}?format=m4a", headers=headers).status_code == 422
    converted.assert_not_called()


def test_audio_variant_reports_failed_conversion(authenticated_client, monkeypatch):
    path, headers, _ = _setup(authenticated_client)
    monkeypatch.setattr(audio, "to_native_audio", AsyncMock(return_value=None))
    response = authenticated_client.get(f"{path}?format=m4a", headers=headers)
    assert response.status_code == 422
    assert "playback" in response.json()["detail"]
    assert authenticated_client.get(path, headers=headers).content == b"original-media"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg and ffprobe are required")
@pytest.mark.parametrize("container", ["ogg", "webm"])
def test_real_opus_converts_to_aac_m4a(tmp_path, container):
    ogg = subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
        "-c:a", "libopus", "-f", container, "pipe:1",
    ], capture_output=True, check=True, timeout=15).stdout
    assert ogg.startswith(b"OggS" if container == "ogg" else b"\x1aE\xdf\xa3")
    m4a = asyncio.run(audio.to_native_audio(ogg))
    assert m4a and b"ftyp" in m4a[:32]
    target = tmp_path / "voice.m4a"
    target.write_bytes(m4a)
    info = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target),
    ], capture_output=True, check=True, timeout=15).stdout)
    assert info["streams"][0]["codec_name"] == "aac"
    assert info["streams"][0]["codec_type"] == "audio"
    assert float(info["streams"][0]["duration"]) >= .35


def test_ffmpeg_timeout_reaps_process(monkeypatch):
    class Process:
        returncode = None
        killed = False
        waited = False
        async def communicate(self, data=None):
            if self.killed:
                await self.wait()
                return b"", b""
            await asyncio.sleep(1)
        def kill(self):
            self.killed = True
        async def wait(self):
            self.waited = True
            self.returncode = -9
    process = Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    assert asyncio.run(audio._run_ffmpeg([], timeout=.01)) is None
    assert process.killed and process.waited


def test_ffmpeg_cancellation_drains_process_and_propagates(monkeypatch):
    class Process:
        returncode = None
        killed = False
        drained = False

        async def communicate(self, data=None):
            if self.killed:
                self.drained = True
                self.returncode = -9
                return b"", b""
            raise asyncio.CancelledError

        def kill(self):
            self.killed = True

    process = Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(audio._run_ffmpeg([]))
    assert process.killed and process.drained and process.returncode == -9
