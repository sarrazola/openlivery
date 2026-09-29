"""The 24-hour window is enforced by the send service itself, so any caller meets it."""
import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from test_whatsapp_cloud import _post_signed, _setup_channel, _webhook_payload

from app.database import SessionLocal
from app.models import Conversation, Message, now_utc
from app.routers import whatsapp_cloud_webhook as webhook_router
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as whatsapp_inbound_service
from app.services.reply_window import WINDOW_CLOSED


def _inbound_conversation(client: TestClient, monkeypatch) -> uuid.UUID:
    _customer, _agent, channel = _setup_channel(client)
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="ok")))
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(return_value="wamid.out"))
    monkeypatch.setattr(whatsapp_service, "mark_read_with_typing", AsyncMock())
    message = {"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Hola"}}
    assert _post_signed(client, channel["id"], _webhook_payload([message])).status_code == 200
    return uuid.UUID(client.get("/api/conversations").json()[0]["id"])


def _age_visitor_messages(conversation_id: uuid.UUID, hours: int) -> None:
    with SessionLocal() as db:
        for row in db.query(Message).filter(Message.conversation_id == conversation_id, Message.sender_type == "visitor"):
            row.created_at = now_utc() - timedelta(hours=hours)
        db.commit()


def test_send_service_refuses_free_text_once_the_window_closes(authenticated_client: TestClient, monkeypatch):
    conversation_id = _inbound_conversation(authenticated_client, monkeypatch)
    sent = AsyncMock(return_value="wamid.free")
    monkeypatch.setattr(whatsapp_service, "send_text", sent)

    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        assert asyncio.run(whatsapp_service.send_channel_message(db, conversation, "Hola de nuevo")) == "wamid.free"
    assert sent.await_count == 1

    _age_visitor_messages(conversation_id, 25)
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        with pytest.raises(HTTPException) as text_refused:
            asyncio.run(whatsapp_service.send_channel_message(db, conversation, "Sigues ahi?"))
        with pytest.raises(HTTPException) as media_refused:
            asyncio.run(whatsapp_service.send_channel_media(db, conversation, kind="image", data=b"png", mime="image/png"))
    assert text_refused.value.status_code == 409 and text_refused.value.detail == WINDOW_CLOSED
    assert media_refused.value.status_code == 409 and media_refused.value.detail == WINDOW_CLOSED
    assert sent.await_count == 1

    # A new message from the person opens it again.
    _age_visitor_messages(conversation_id, 1)
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        assert asyncio.run(whatsapp_service.send_channel_message(db, conversation, "Aqui estoy")) == "wamid.free"
