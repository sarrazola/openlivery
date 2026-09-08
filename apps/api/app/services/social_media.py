"""Bounded media downloads and short-lived provider fetch URLs."""
import asyncio
import hashlib
import ipaddress
import re
import socket
import hmac
from pathlib import PurePath
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException

from ..config import get_settings
from ..models import SocialChannel, MessageAttachment, now_utc
from ..security import decrypt_secret
from .attachments import MAX_ATTACHMENT_BYTES, ensure_uploadable, safe_filename
from .audio import _run_ffmpeg

CDN_SUFFIXES = ("fbcdn.net", "cdninstagram.com", "fbsbx.com", "facebook.com", "instagram.com")


def validate_cdn_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed_port = parsed.port in (None, 443)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="The media URL is not a supported provider CDN.") from None
    if (parsed.scheme != "https" or not allowed_port or parsed.username or parsed.password
            or not any(host == suffix or host.endswith("." + suffix) for suffix in CDN_SUFFIXES)):
        raise HTTPException(status_code=422, detail="The media URL is not a supported provider CDN.")


async def _public_cdn_address(url: str) -> None:
    """CDN-owned hostnames must still resolve only to public network addresses."""
    hostname = urlparse(url).hostname
    try:
        addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
            hostname, 443, type=socket.SOCK_STREAM), timeout=5)
        safe = addresses and all(ipaddress.ip_address(address[4][0]).is_global for address in addresses)
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(status_code=502, detail="The media host could not be resolved safely.") from None
    if not safe:
        raise HTTPException(status_code=422, detail="The media host must resolve to public addresses.")


async def fetch_inbound_media(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        for _ in range(4):
            validate_cdn_url(url)
            await _public_cdn_address(url)
            async with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers.get("location", "")))
                    continue
                if response.status_code != 200:
                    raise HTTPException(status_code=502, detail="The shared media is unavailable or expired.")
                mime = response.headers.get("content-type", "application/octet-stream").split(";")[0].lower()
                ensure_uploadable(mime)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > MAX_ATTACHMENT_BYTES:
                        raise HTTPException(status_code=413, detail="The attachment exceeds the 20 MB limit.")
                    data.extend(chunk)
                if not data:
                    raise HTTPException(status_code=502, detail="The shared media is empty or unavailable.")
                return bytes(data), mime
    raise HTTPException(status_code=502, detail="The media download redirected too many times.")


async def prepare_media(provider: str, data: bytes, mime: str, kind: str) -> tuple[bytes, str]:
    mime = mime.lower().split(";")[0].strip()
    ensure_uploadable(mime)
    if not re.fullmatch(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", mime):
        raise HTTPException(status_code=422, detail="The attachment content type is invalid.")
    if provider not in {"instagram", "messenger"} or kind not in {"image", "audio", "video", "file"}:
        raise HTTPException(status_code=422, detail="This attachment type is not supported by the channel.")
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="The attachment is empty or exceeds the 20 MB limit.")
    if ((kind == "image" and not mime.startswith("image/"))
            or (kind == "audio" and not (mime.startswith("audio/") or mime == "video/ogg"))
            or (kind == "video" and not mime.startswith("video/"))):
        raise HTTPException(status_code=422, detail="The attachment type does not match its content type.")
    if (mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n")) or (mime == "image/jpeg" and not data.startswith(b"\xff\xd8\xff")):
        raise HTTPException(status_code=422, detail="The image does not match its declared format.")
    if provider == "instagram":
        if kind == "image" and mime not in {"image/png", "image/jpeg"}:
            converted = await _run_ffmpeg(["-protocol_whitelist", "pipe", "-i", "pipe:0", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-fs", str(8 * 1024 * 1024 + 1), "pipe:1"], data)
            if not converted:
                raise HTTPException(status_code=422, detail="Convert this image to PNG or JPEG before sending.")
            data, mime = converted, "image/png"
        elif kind == "audio" and mime not in {"audio/aac", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/x-wav"}:
            converted = await _run_ffmpeg(["-protocol_whitelist", "pipe", "-i", "pipe:0", "-vn", "-c:a", "aac", "-b:a", "96k", "-f", "mp4",
                                           "-movflags", "frag_keyframe+empty_moov", "-fs", str(MAX_ATTACHMENT_BYTES + 1), "pipe:1"], data)
            if not converted:
                raise HTTPException(status_code=422, detail="Audio conversion failed. Upload an M4A or WAV file.")
            data, mime = converted, "audio/mp4"
        elif kind == "video" and mime not in {"video/mp4", "video/quicktime", "video/webm", "video/ogg", "video/avi", "video/x-msvideo"}:
            raise HTTPException(status_code=422, detail="Convert this video to MP4, MOV, WebM or AVI before sending.")
        elif kind == "file" and (mime != "application/pdf" or not data.startswith(b"%PDF-")):
            raise HTTPException(status_code=422, detail="Instagram supports PDF documents. Select a PDF file.")
    maximum = 8 * 1024 * 1024 if provider == "instagram" and kind == "image" else MAX_ATTACHMENT_BYTES
    if len(data) > maximum:
        raise HTTPException(status_code=413, detail="This attachment exceeds the channel's size limit.")
    return data, mime


def converted_filename(filename: str | None, mime: str) -> str | None:
    """Keep filenames aligned with the format produced by conversion."""
    filename = safe_filename(filename)
    if not filename:
        return None
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "audio/mp4": ".m4a", "audio/aac": ".aac",
              "audio/wav": ".wav", "audio/x-wav": ".wav", "video/mp4": ".mp4", "application/pdf": ".pdf"}.get(mime)
    if not suffix:
        return filename
    stem = PurePath(filename).stem.strip(".") or "attachment"
    return stem[:255 - len(suffix)] + suffix


def media_signature(channel: SocialChannel, attachment_id, expires: int) -> str:
    secret = decrypt_secret(channel.encrypted_app_secret or "")
    content = f"social-media:{channel.id}:{attachment_id}:{expires}"
    return hmac.new(secret.encode(), content.encode(), hashlib.sha256).hexdigest()


def attachment_url(channel: SocialChannel, attachment: MessageAttachment) -> str:
    from .social_connections import get_app_config
    config = get_app_config(channel.provider)
    origin = urlparse(config.webhook_url if config and config.webhook_url else get_settings().frontend_url)
    if origin.scheme != "https" or not origin.hostname or origin.username or origin.password:
        raise HTTPException(status_code=409, detail="A public HTTPS address is required to send attachments.")
    base = urlunparse((origin.scheme, origin.netloc, "", "", "", ""))
    if not channel.is_enabled or channel.status != "connected" or not channel.encrypted_app_secret:
        raise HTTPException(status_code=409, detail="Connect this messaging channel before sending attachments.")
    if attachment.size_bytes != len(attachment.data):
        raise HTTPException(status_code=409, detail="The attachment data is incomplete.")
    expires = int(now_utc().timestamp()) + 3600
    return (f"{base}/api/public/social/media/{channel.id}/{attachment.id}?expires={expires}"
            f"&signature={media_signature(channel, attachment.id, expires)}")
