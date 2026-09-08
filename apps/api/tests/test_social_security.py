import asyncio
import hashlib
import hmac
import json
import socket
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.config import get_settings
from app.models import SocialChannel, SocialWebhookEvent, now_utc
from app.routers import social_webhook
from app.security import encrypt_secret
from app.services import attachments, audio, social_media
from conftest import TestingSession
from test_social_history import setup


def test_unicode_verification_queries_return_forbidden_instead_of_server_error(authenticated_client, monkeypatch):
    setup(authenticated_client, monkeypatch)
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel_id = channel.id
    response = authenticated_client.get(f"/api/public/social/channels/{channel_id}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "ñ", "hub.challenge": "challenge"})
    assert response.status_code == 403
    response = authenticated_client.get(f"/api/public/social/media/{channel_id}/{uuid.uuid4()}",
        params={"expires": int(now_utc().timestamp()) + 60, "signature": "ñ"})
    assert response.status_code == 403


def test_non_ascii_hmac_header_is_rejected_without_type_error():
    async def run():
        request = Request({"type": "http", "headers": [(b"x-hub-signature-256", b"\xff")]},
            receive=AsyncMock(return_value={"type": "http.request", "body": b"{}", "more_body": False}))
        with pytest.raises(HTTPException) as error:
            await social_webhook._verified_payload(request, "secret")
        assert error.value.status_code == 403
    asyncio.run(run())


def test_revoked_token_keeps_signed_receipts_and_blocks_new_media_urls(authenticated_client, monkeypatch):
    setup(authenticated_client, monkeypatch)
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel.status = "reauthorization_required"
        channel_id = channel.id
        db.commit()
        monkeypatch.setattr(get_settings(), "frontend_url", "https://app.example.test")
        with pytest.raises(HTTPException) as error:
            social_media.attachment_url(channel, SimpleNamespace(id=uuid.uuid4(), size_bytes=1, data=b"a"))
        assert error.value.status_code == 409
    payload = {"object": "instagram", "entry": [{"id": "111", "messaging": [{"sender": {"id": "222"},
        "recipient": {"id": "111"}, "timestamp": int(now_utc().timestamp() * 1000), "read": {"mid": "message"}}]}]}
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    response = authenticated_client.post(f"/api/public/social/channels/{channel_id}/webhook", content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    assert response.status_code == 200
    with TestingSession() as db:
        assert db.scalar(select(SocialWebhookEvent)) is not None


def test_non_ascii_app_secret_comparison_uses_bytes(authenticated_client, monkeypatch):
    setup(authenticated_client, monkeypatch)
    secret = "secreto-ñ"
    monkeypatch.setattr(get_settings(), "instagram_app_id", "999")
    monkeypatch.setattr(get_settings(), "instagram_app_secret", secret)
    with TestingSession() as db:
        channel = db.scalar(select(SocialChannel))
        channel.encrypted_app_secret = encrypt_secret(secret)
        db.commit()
    raw = json.dumps({"object": "instagram", "entry": [{"id": "111", "messaging": []}]}).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    response = authenticated_client.post("/api/public/social/instagram/webhook", content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    assert response.status_code == 200


def test_cdn_url_rejects_foreign_hosts_and_malformed_origins():
    for url in ("http://cdn.fbcdn.net/file", "https://fbcdn.net.attacker.test/file", "https://user:pass@cdn.fbcdn.net/file",
                "https://cdn.fbcdn.net:8080/file", "https://[invalid/file", "https://cdn.fbcdn.net：443/file"):
        with pytest.raises(HTTPException) as error:
            social_media.validate_cdn_url(url)
        assert error.value.status_code == 422
    social_media.validate_cdn_url("https://scontent.example.fbcdn.net/file")


def test_cdn_dns_rejects_private_and_mixed_addresses(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        lookup = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
        monkeypatch.setattr(loop, "getaddrinfo", lookup)
        with pytest.raises(HTTPException) as error:
            await social_media._public_cdn_address("https://local.facebook.com/file")
        assert error.value.status_code == 422
        lookup.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("157.240.1.1", 443)),
                               (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))]
        with pytest.raises(HTTPException):
            await social_media._public_cdn_address("https://cdn.fbcdn.net/file")
        lookup.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("157.240.1.1", 443))]
        await social_media._public_cdn_address("https://cdn.fbcdn.net/file")
    asyncio.run(run())


def test_image_magic_and_media_kind_mismatch_are_rejected():
    for kind, mime, data in (("image", "image/png", b"<html>"), ("image", "image/jpeg", b"%PDF-1.0"),
                             ("audio", "image/png", b"image"), ("video", "video/x-flv", b"FLV")):
        with pytest.raises(HTTPException) as error:
            asyncio.run(social_media.prepare_media("instagram", data, mime, kind))
        assert error.value.status_code == 422


def test_conversion_cannot_open_nested_network_or_file_protocols(monkeypatch):
    converter = AsyncMock(return_value=b"converted")
    monkeypatch.setattr(social_media, "_run_ffmpeg", converter)
    output, mime = asyncio.run(social_media.prepare_media("instagram", b"webm-data", "audio/webm", "audio"))
    assert mime == "audio/mp4" and output == b"converted"
    args = converter.call_args.args[0]
    assert args[:2] == ["-protocol_whitelist", "pipe"]
    assert "-fs" in args
    assert social_media.converted_filename("voice.webm", mime) == "voice.m4a"
    assert social_media.converted_filename("a" * 255, "image/png").endswith(".png")
    assert len(social_media.converted_filename("a" * 255, "image/png")) == 255
    assert social_media.converted_filename(".", "image/png") == "attachment.png"


def test_attachment_response_supports_unicode_filename_without_header_injection():
    attachment = SimpleNamespace(mime="application/pdf", filename="reporte 日本語.pdf\r\nX-Evil: yes", data=b"%PDF-1.0")
    response = attachments.attachment_response(attachment)
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "%E6%97%A5%E6%9C%AC%E8%AA%9E" in disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert response.headers.get("X-Evil") is None


def test_ffmpeg_timeout_kills_and_reaps_child(monkeypatch):
    process = SimpleNamespace(returncode=None, communicate=AsyncMock(return_value=(b"", b"")), kill=Mock())
    monkeypatch.setattr(audio.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    async def timeout(awaitable, **kwargs):
        await awaitable
        raise asyncio.TimeoutError()
    monkeypatch.setattr(audio.asyncio, "wait_for", timeout)
    assert asyncio.run(audio._run_ffmpeg(["-i", "pipe:0"], b"input")) is None
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2


def test_ffmpeg_cancellation_reaps_child_and_preserves_cancellation(monkeypatch):
    process = SimpleNamespace(returncode=None, communicate=AsyncMock(return_value=(b"", b"")), kill=Mock())
    monkeypatch.setattr(audio.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    async def cancel(awaitable, **kwargs):
        await awaitable
        raise asyncio.CancelledError()
    monkeypatch.setattr(audio.asyncio, "wait_for", cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(audio._run_ffmpeg(["-i", "pipe:0"], b"input"))
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2


def test_media_redirect_cannot_escape_provider_cdn(monkeypatch):
    import httpx
    response = SimpleNamespace(is_redirect=True, url=httpx.URL("https://cdn.fbcdn.net/file"), headers={"location": "http://127.0.0.1/private"})
    class Stream:
        async def __aenter__(self):
            return response
        async def __aexit__(self, *args):
            pass
    class Client:
        calls = []
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def stream(self, method, url, **kwargs):
            self.calls.append(url)
            return Stream()
    monkeypatch.setattr(social_media.httpx, "AsyncClient", Client)
    monkeypatch.setattr(social_media, "_public_cdn_address", AsyncMock())
    with pytest.raises(HTTPException) as error:
        asyncio.run(social_media.fetch_inbound_media("https://cdn.fbcdn.net/file"))
    assert error.value.status_code == 422
    assert Client.calls == ["https://cdn.fbcdn.net/file"]


def test_media_stream_limit_is_enforced_before_accumulating_extra_chunk(monkeypatch):
    class Response:
        is_redirect = False
        status_code = 200
        headers = {"content-type": "audio/mpeg"}
        async def aiter_bytes(self):
            yield b"123"
            yield b"456"
    class Stream:
        async def __aenter__(self):
            return Response()
        async def __aexit__(self, *args):
            pass
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def stream(self, *args, **kwargs):
            return Stream()
    monkeypatch.setattr(social_media.httpx, "AsyncClient", Client)
    monkeypatch.setattr(social_media, "_public_cdn_address", AsyncMock())
    monkeypatch.setattr(social_media, "MAX_ATTACHMENT_BYTES", 4)
    with pytest.raises(HTTPException) as error:
        asyncio.run(social_media.fetch_inbound_media("https://cdn.fbcdn.net/file"))
    assert error.value.status_code == 413
