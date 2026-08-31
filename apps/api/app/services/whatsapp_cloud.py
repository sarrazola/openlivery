"""Thin client for the WhatsApp Business Cloud API (Meta Graph API).

Each channel brings its own Meta app credentials; the access token is decrypted
by the caller and never logged. Errors surface as HTTPException with safe
messages (Meta's error detail, never the credentials).
"""

import httpx
from fastapi import HTTPException

from ..config import get_settings

MAX_MEDIA_BYTES = 20 * 1024 * 1024
# Hard limit of the Cloud API for a text message body.
MAX_TEXT_LENGTH = 4096
GRAPH_TIMEOUT = 30


def _graph_url(path: str) -> str:
    return f"{get_settings().meta_graph_base_url.rstrip('/')}/{path.lstrip('/')}"


def _graph_error(response: httpx.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message")
    except ValueError:
        message = None
    return message or f"Meta API returned status {response.status_code}"


async def _graph_request(method: str, url: str, access_token: str, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
            return await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the Meta API.") from exc


async def verify_phone_number(access_token: str, phone_number_id: str) -> dict:
    """Validate the credentials and return the number's public profile."""
    response = await _graph_request(
        "GET",
        _graph_url(f"{phone_number_id}?fields=display_phone_number,verified_name"),
        access_token,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Credential check failed: {_graph_error(response)}")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid response from the Meta API.") from exc


async def send_text(
    access_token: str, phone_number_id: str, to: str, body: str, context_message_id: str | None = None
) -> str | None:
    """Send a text message; returns the outbound message id (wamid).

    ``context_message_id`` makes it a quoted reply (the swipe-to-reply look)
    on the referenced message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:MAX_TEXT_LENGTH]},
    }
    if context_message_id:
        payload["context"] = {"message_id": context_message_id}
    response = await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"WhatsApp could not send the message: {_graph_error(response)}")
    try:
        messages = response.json().get("messages") or []
        return messages[0].get("id") if messages else None
    except ValueError:
        return None


async def send_reaction(access_token: str, phone_number_id: str, to: str, message_id: str, emoji: str) -> None:
    """React with an emoji to a message; an empty emoji removes the reaction.
    Raises on failure so the caller decides whether the gesture matters."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "reaction",
        "reaction": {"message_id": message_id, "emoji": emoji},
    }
    response = await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"WhatsApp could not send the reaction: {_graph_error(response)}")


async def mark_read(access_token: str, phone_number_id: str, message_id: str) -> None:
    """Mark the conversation as read up to ``message_id`` (blue ticks) without
    the typing indicator. Best-effort, like the fused variant below."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    except HTTPException:
        pass


async def mark_read_with_typing(access_token: str, phone_number_id: str, message_id: str) -> None:
    """Mark the conversation as read up to ``message_id`` (blue ticks) and show
    the typing indicator while the reply is being generated. Meta dismisses the
    indicator when a message is sent, or after ~25 seconds. Best-effort: the
    reply must never depend on this call."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    try:
        await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    except HTTPException:
        pass


async def upload_media(access_token: str, phone_number_id: str, data: bytes, mime: str, filename: str) -> str:
    """Upload a media file to Meta and return its media id (required before
    sending any outbound media message)."""
    response = await _graph_request(
        "POST",
        _graph_url(f"{phone_number_id}/media"),
        access_token,
        data={"messaging_product": "whatsapp", "type": mime},
        files={"file": (filename, data, mime)},
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"WhatsApp could not upload the file: {_graph_error(response)}")
    try:
        media_id = response.json().get("id")
    except ValueError:
        media_id = None
    if not media_id:
        raise HTTPException(status_code=502, detail="Invalid media upload response from the Meta API.")
    return media_id


async def send_media(
    access_token: str,
    phone_number_id: str,
    to: str,
    kind: str,
    media_id: str,
    caption: str = "",
    filename: str | None = None,
) -> str | None:
    """Send an image/audio/document message; returns the outbound message id."""
    media_object: dict = {"id": media_id}
    if caption and kind in {"image", "video", "document"}:
        media_object["caption"] = caption[:1024]
    if filename and kind == "document":
        media_object["filename"] = filename
    payload = {"messaging_product": "whatsapp", "to": to, "type": kind, kind: media_object}
    response = await _graph_request("POST", _graph_url(f"{phone_number_id}/messages"), access_token, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"WhatsApp could not send the file: {_graph_error(response)}")
    try:
        messages = response.json().get("messages") or []
        return messages[0].get("id") if messages else None
    except ValueError:
        return None


async def fetch_media(access_token: str, media_id: str) -> tuple[bytes, str]:
    """Download an inbound media file: resolve the short-lived URL, then fetch
    it with the same token. Returns (data, mime_type)."""
    lookup = await _graph_request("GET", _graph_url(media_id), access_token)
    if lookup.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Could not resolve the media file: {_graph_error(lookup)}")
    try:
        info = lookup.json()
        url, mime = info["url"], info.get("mime_type") or "application/octet-stream"
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="Invalid media response from the Meta API.") from exc
    download = await _graph_request("GET", url, access_token)
    if download.status_code >= 400 or len(download.content) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=502, detail="Could not download the media file.")
    return download.content, mime
