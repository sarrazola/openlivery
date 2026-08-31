import base64
import uuid

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..config import get_settings
from ..models import Conversation, Message, WhatsAppCloudChannel
from ..security import decrypt_secret
from .audio import audio_duration_seconds, to_whatsapp_voice
from .whatsapp_cloud import mark_read, mark_read_with_typing, send_media, send_reaction, send_text, upload_media
from .whatsapp_format import markdown_to_whatsapp


async def bridge_command(method: str, path: str, payload: dict | None = None, timeout: float = 20) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                f"{settings.whatsapp_bridge_url.rstrip('/')}{path}",
                headers={"X-Bridge-Token": settings.whatsapp_bridge_token},
                json=payload,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="The local WhatsApp service is not available. Start it with go run . inside apps/whatsapp/.",
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("error")
        except ValueError:
            detail = None
        raise HTTPException(status_code=502, detail=detail or "WhatsApp could not complete the operation")
    if response.status_code == 204:
        return {}
    return response.json()


async def send_channel_message(
    db: Session, conversation: Conversation, content: str, *, quoted_external_id: str | None = None
) -> str | None:
    """Deliver an operator message through the conversation's channel. Returns
    the external message id, or None for channels without outbound delivery.

    ``quoted_external_id`` sends it as a quoted reply."""
    if conversation.channel == "whatsapp":
        if not conversation.whatsapp_channel_id or not conversation.external_chat_id:
            raise HTTPException(status_code=409, detail="This conversation does not have a valid WhatsApp destination")
        payload = {"remote_jid": conversation.external_chat_id, "text": markdown_to_whatsapp(content)}
        if quoted_external_id:
            payload["quote_external_id"] = quoted_external_id
        result = await bridge_command(
            "POST",
            f"/channels/{conversation.whatsapp_channel_id}/send",
            payload,
        )
        return result.get("external_message_id")
    if conversation.channel == "whatsapp_cloud":
        if not conversation.whatsapp_cloud_channel_id or not conversation.external_chat_id:
            raise HTTPException(status_code=409, detail="This conversation does not have a valid WhatsApp destination")
        channel = db.get(WhatsAppCloudChannel, conversation.whatsapp_cloud_channel_id)
        if not channel or not channel.encrypted_access_token or not channel.phone_number_id:
            raise HTTPException(status_code=409, detail="The WhatsApp API channel is not configured")
        return await send_text(
            decrypt_secret(channel.encrypted_access_token),
            channel.phone_number_id,
            conversation.external_chat_id,
            markdown_to_whatsapp(content),
            context_message_id=quoted_external_id,
        )
    return None


async def send_channel_media(
    db: Session,
    conversation: Conversation,
    *,
    kind: str,
    data: bytes,
    mime: str,
    filename: str | None = None,
    caption: str = "",
) -> str | None:
    """Deliver an operator media message (image/audio/video/file) through the
    conversation's channel. Returns the external message id, or None for
    channels without outbound delivery (playground, widget)."""
    caption = markdown_to_whatsapp(caption)
    seconds = None
    if kind == "audio" and conversation.channel in ("whatsapp", "whatsapp_cloud"):
        # WhatsApp only plays ogg/opus voice notes; browsers record webm/mp4.
        data, mime = await to_whatsapp_voice(data, mime)
        seconds = await audio_duration_seconds(data)
        if mime == "audio/ogg":
            # The filename must match the transcoded bytes: Meta classifies the
            # upload by extension, and an ogg named .mp4/.webm comes out as
            # application/octet-stream and fails delivery (error 131053).
            filename = "voice-note.ogg"
    if conversation.channel == "whatsapp":
        if not conversation.whatsapp_channel_id or not conversation.external_chat_id:
            raise HTTPException(status_code=409, detail="This conversation does not have a valid WhatsApp destination")
        result = await bridge_command(
            "POST",
            f"/channels/{conversation.whatsapp_channel_id}/send",
            {
                "remote_jid": conversation.external_chat_id,
                "text": caption,
                "media_kind": kind,
                "media_mime": mime,
                "media_base64": base64.b64encode(data).decode(),
                "media_seconds": seconds,
                "filename": filename,
            },
            timeout=90,
        )
        return result.get("external_message_id")
    if conversation.channel == "whatsapp_cloud":
        if not conversation.whatsapp_cloud_channel_id or not conversation.external_chat_id:
            raise HTTPException(status_code=409, detail="This conversation does not have a valid WhatsApp destination")
        channel = db.get(WhatsAppCloudChannel, conversation.whatsapp_cloud_channel_id)
        if not channel or not channel.encrypted_access_token or not channel.phone_number_id:
            raise HTTPException(status_code=409, detail="The WhatsApp API channel is not configured")
        access_token = decrypt_secret(channel.encrypted_access_token)
        cloud_kind = {"image": "image", "audio": "audio", "video": "video"}.get(kind, "document")
        media_id = await upload_media(
            access_token, channel.phone_number_id, data, mime, filename or f"{kind}.bin"
        )
        external_id = await send_media(
            access_token,
            channel.phone_number_id,
            conversation.external_chat_id,
            cloud_kind,
            media_id,
            caption=caption,
            filename=filename,
        )
        # The Cloud API has no caption field for audio; deliver it as a follow-up text.
        if caption and cloud_kind == "audio":
            await send_text(access_token, channel.phone_number_id, conversation.external_chat_id, caption)
        return external_id
    return None


def resolve_quote(
    db: Session, conversation: Conversation, quoted_message_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, str | None]:
    """Validate that the quoted message belongs to the conversation and return
    ``(quoted_message_id, quoted_external_id)`` for storing and delivery. A
    message without an external id can still be quoted in the portal, it just
    cannot be rendered as a quote on WhatsApp."""
    if not quoted_message_id:
        return None, None
    quoted = db.scalar(
        select(Message).where(Message.id == quoted_message_id, Message.conversation_id == conversation.id)
    )
    if not quoted:
        raise HTTPException(status_code=404, detail="The quoted message is not part of this conversation")
    return quoted.id, quoted.external_message_id


async def signal_channel_read(
    db: Session, conversation: Conversation, message_external_ids: list[str], *, typing: bool
) -> None:
    """Blue-tick the given visitor messages on WhatsApp, optionally showing the
    typing indicator afterwards. Best-effort on both channels: reading is a
    gesture, never worth failing the caller over."""
    ids = [item for item in message_external_ids if item]
    if not ids or not conversation.external_chat_id:
        return
    if conversation.channel == "whatsapp" and conversation.whatsapp_channel_id:
        try:
            await bridge_command(
                "POST",
                f"/channels/{conversation.whatsapp_channel_id}/read",
                {"remote_jid": conversation.external_chat_id, "message_ids": ids, "typing": typing},
            )
        except HTTPException:
            pass
        return
    if conversation.channel == "whatsapp_cloud" and conversation.whatsapp_cloud_channel_id:
        channel = db.get(WhatsAppCloudChannel, conversation.whatsapp_cloud_channel_id)
        if not channel or not channel.encrypted_access_token or not channel.phone_number_id:
            return
        access_token = decrypt_secret(channel.encrypted_access_token)
        # Meta reads "up to" a message, so the newest id covers the burst.
        if typing:
            await mark_read_with_typing(access_token, channel.phone_number_id, ids[-1])
        else:
            await mark_read(access_token, channel.phone_number_id, ids[-1])


async def deliver_reaction(db: Session, conversation: Conversation, target, emoji: str) -> None:
    """Send an emoji reaction to ``target`` (a Message with an external id)
    through the conversation's channel; empty emoji removes it. Raises when the
    channel cannot deliver it."""
    if not target.external_message_id or not conversation.external_chat_id:
        raise HTTPException(status_code=409, detail="This message cannot receive a reaction")
    if conversation.channel == "whatsapp":
        if not conversation.whatsapp_channel_id:
            raise HTTPException(status_code=409, detail="This conversation does not have a valid WhatsApp destination")
        await bridge_command(
            "POST",
            f"/channels/{conversation.whatsapp_channel_id}/react",
            {
                "remote_jid": conversation.external_chat_id,
                "external_message_id": target.external_message_id,
                "emoji": emoji,
                "target_from_me": target.role != "user",
            },
        )
        return
    if conversation.channel == "whatsapp_cloud":
        channel = db.get(WhatsAppCloudChannel, conversation.whatsapp_cloud_channel_id)
        if not channel or not channel.encrypted_access_token or not channel.phone_number_id:
            raise HTTPException(status_code=409, detail="The WhatsApp API channel is not configured")
        await send_reaction(
            decrypt_secret(channel.encrypted_access_token),
            channel.phone_number_id,
            conversation.external_chat_id,
            target.external_message_id,
            emoji,
        )
        return
    raise HTTPException(status_code=409, detail="This channel does not support reactions")
