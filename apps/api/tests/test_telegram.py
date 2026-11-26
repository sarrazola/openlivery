"""Telegram bots as a channel, against disposable PostgreSQL and a stubbed Bot API."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import Agent, ContactIdentity, Conversation, Message, MessageAttachment, SocialChannel, SocialOutbox, SocialWebhookEvent, now_utc
from app.security import decrypt_secret
from app.services import notifications, social_connections, social_delivery, social_inbound, social_worker, telegram, telegram_api, whatsapp_inbound
from app.services.ai import Completion
from app.services.social_policy import window_fields
from conftest import TestingSession

TOKEN = "123456789:AAH-test_token_value_for_the_bot_abcdef"
BOT_ID = 123456789
PERSON = 555001


@pytest.fixture(autouse=True)
def stub_bot_api(monkeypatch):
    calls = SimpleNamespace(hooks=[], typing=[])
    monkeypatch.setattr(social_connections, "_connection_hooks", [lambda db, channel, event: calls.hooks.append((channel.id, event))])
    monkeypatch.setattr(telegram, "_public_base", lambda db, agency_id: "https://bots.example.test")
    monkeypatch.setattr(telegram_api, "get_me", AsyncMock(return_value={"id": BOT_ID, "is_bot": True, "first_name": "Shop Bot", "username": "shop_bot"}))
    monkeypatch.setattr(telegram_api, "set_webhook", AsyncMock())
    monkeypatch.setattr(telegram_api, "delete_webhook", AsyncMock())
    monkeypatch.setattr(telegram_api, "send_text", AsyncMock(side_effect=lambda token, chat, text: f"{chat}:{uuid.uuid4().int % 10**6}"))
    monkeypatch.setattr(telegram_api, "send_file", AsyncMock(side_effect=lambda token, chat, *args: f"{chat}:{uuid.uuid4().int % 10**6}"))
    monkeypatch.setattr(telegram_api, "send_typing", AsyncMock(side_effect=lambda token, chat: calls.typing.append(chat)))
    monkeypatch.setattr(telegram_api, "download", AsyncMock(return_value=b"\xff\xd8\xff" + b"0" * 64))
    monkeypatch.setattr(whatsapp_inbound, "run_completion", AsyncMock(return_value=Completion(text="**Hola**, te ayudo.")))
    monkeypatch.setattr(notifications, "notify_needs_human", AsyncMock(return_value=0))
    monkeypatch.setattr(social_inbound, "reply_delay_seconds", lambda agent: 0)
    monkeypatch.setattr(whatsapp_inbound, "reply_delay_seconds", lambda agent: 0)
    return calls


def resources(client, name="Shop"):
    customer = client.post("/api/clients", json={"name": name, "is_active": True})
    assert customer.status_code == 201, customer.text
    assert client.put("/api/providers/openrouter", json={"api_key": "test-key"}).status_code == 200
    agent = client.post("/api/agents", json={"client_id": customer.json()["id"], "provider": "openrouter", "model": "gpt-4.1-mini",
        "name": "Support", "instructions": "", "personality": "", "is_active": True,
        "reply_delay_min_seconds": 0, "reply_delay_max_seconds": 0})
    assert agent.status_code == 201, agent.text
    return SimpleNamespace(client_id=customer.json()["id"], agent_id=agent.json()["id"])


def connect(client, resource, **extra):
    return client.post(f"/api/telegram/clients/{resource.client_id}/channels",
                       json={"agent_id": resource.agent_id, "token": TOKEN, **extra})


def update(text="Hola", *, update_id=1, message_id=10, chat_type="private", **message):
    return {"update_id": update_id, "message": {
        "message_id": message_id, "date": int(now_utc().timestamp()),
        "chat": {"id": PERSON, "type": chat_type},
        "from": {"id": PERSON, "is_bot": False, "first_name": "Ana", "last_name": "Pérez", "username": "anap"},
        **({"text": text} if text is not None else {}), **message}}


def post_update(client, channel_id, payload, secret):
    return client.post(f"/api/public/social/channels/{channel_id}/webhook", json=payload,
                       headers={"X-Telegram-Bot-Api-Secret-Token": secret})


def run_worker(db):
    asyncio.run(social_inbound.process_pending(db))
    asyncio.run(social_worker.process_replies(db))
    asyncio.run(social_delivery.process_outbox(db))


def test_connecting_a_bot_checks_the_token_and_points_its_webhook_here(authenticated_client, stub_bot_api):
    resource = resources(authenticated_client)
    response = connect(authenticated_client, resource, label="Ventas")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "telegram" and body["username"] == "shop_bot" and body["label"] == "Ventas"
    assert body["status"] == "connected" and body["has_token"] and "token" not in body
    with TestingSession() as db:
        channel = db.get(SocialChannel, uuid.UUID(body["id"]))
        assert decrypt_secret(channel.encrypted_access_token) == TOKEN
        assert channel.external_account_id == channel.app_id == str(BOT_ID)
        url, secret = telegram_api.set_webhook.await_args.args[1:]
        assert url == f"https://bots.example.test/api/public/social/channels/{channel.id}/webhook"
        assert secret == channel.webhook_verify_token
    assert stub_bot_api.hooks == [(uuid.UUID(body["id"]), "linked")]
    # The same bot again updates its row instead of adding another.
    assert connect(authenticated_client, resource).status_code == 201
    listed = authenticated_client.get(f"/api/telegram/clients/{resource.client_id}/channels").json()
    assert [item["id"] for item in listed] == [body["id"]]


def test_a_malformed_token_never_reaches_telegram(authenticated_client):
    resource = resources(authenticated_client)
    response = authenticated_client.post(f"/api/telegram/clients/{resource.client_id}/channels",
                                         json={"agent_id": resource.agent_id, "token": "not-a-token"})
    assert response.status_code == 422
    telegram_api.get_me.assert_not_awaited()


def test_a_bot_answers_for_one_client_only(authenticated_client):
    first, second = resources(authenticated_client, "One"), resources(authenticated_client, "Two")
    assert connect(authenticated_client, first).status_code == 201
    response = connect(authenticated_client, second)
    assert response.status_code == 409


def test_without_a_public_https_address_the_bot_is_not_connected(authenticated_client, monkeypatch):
    monkeypatch.setattr(telegram, "_public_base", None)
    resource = resources(authenticated_client)
    response = connect(authenticated_client, resource)
    assert response.status_code == 409 and "HTTPS" in response.json()["detail"]
    with TestingSession() as db:
        assert db.scalar(select(func.count(SocialChannel.id))) == 0


def test_webhook_needs_the_secret_and_stores_each_update_once(authenticated_client):
    resource = resources(authenticated_client)
    channel = connect(authenticated_client, resource).json()
    with TestingSession() as db:
        secret = db.get(SocialChannel, uuid.UUID(channel["id"])).webhook_verify_token
    assert post_update(authenticated_client, channel["id"], update(), "wrong").status_code == 403
    assert post_update(authenticated_client, channel["id"], update(), secret).status_code == 200
    assert post_update(authenticated_client, channel["id"], update(), secret).status_code == 200
    with TestingSession() as db:
        assert db.scalar(select(func.count(SocialWebhookEvent.id))) == 1


def test_a_message_is_answered_through_the_bot(authenticated_client, stub_bot_api):
    resource = resources(authenticated_client)
    channel = connect(authenticated_client, resource).json()
    with TestingSession() as db:
        secret = db.get(SocialChannel, uuid.UUID(channel["id"])).webhook_verify_token
    assert post_update(authenticated_client, channel["id"], update("Hola, ¿tienen envíos?"), secret).status_code == 200
    with TestingSession() as db:
        run_worker(db)
        conversation = db.scalar(select(Conversation))
        assert conversation.channel == "telegram" and conversation.external_chat_id == str(PERSON)
        assert conversation.title == "Ana Pérez"
        identity = db.scalar(select(ContactIdentity))
        assert identity.provider == "telegram" and identity.username == "anap"
        messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)).all()
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].external_message_id == f"{PERSON}:10"
        assert messages[1].delivery_status == "sent"
        assert messages[1].external_message_id.startswith(f"{PERSON}:")
    token, chat, text = telegram_api.send_text.await_args.args
    assert token == TOKEN and chat == str(PERSON) and text == "**Hola**, te ayudo."
    assert stub_bot_api.typing == [str(PERSON)]


def test_start_reads_as_an_opened_chat_and_groups_are_ignored(authenticated_client):
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    with TestingSession() as db:
        channel = db.get(SocialChannel, channel_id)
        asyncio.run(telegram.process_update(db, channel, update("Hola", chat_type="group")))
        assert db.scalar(select(func.count(Conversation.id))) == 0
        asyncio.run(telegram.process_update(db, channel, update("/start")))
        message = db.scalar(select(Message).where(Message.role == "user"))
        assert message.content == "/start" and message.llm_content == telegram.OPENED_CHAT


def test_a_photo_is_kept_with_its_caption(authenticated_client):
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    photo = [{"file_id": "small", "file_size": 100}, {"file_id": "large", "file_size": 2000}]
    with TestingSession() as db:
        channel = db.get(SocialChannel, channel_id)
        asyncio.run(telegram.process_update(db, channel, update(None, photo=photo, caption="¿Lo tienen?")))
        message = db.scalar(select(Message).where(Message.role == "user"))
        assert message.content == "¿Lo tienen?"
        attachment = db.scalar(select(MessageAttachment))
        assert attachment.kind == "image" and attachment.message_id == message.id
    assert telegram_api.download.await_args.args == (TOKEN, "large")


def test_a_file_that_will_not_download_is_tried_again_before_it_is_given_up(authenticated_client, monkeypatch):
    monkeypatch.setattr(telegram_api, "download", AsyncMock(side_effect=HTTPException(502, "down")))
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    voice = {"file_id": "voice-1", "mime_type": "audio/ogg", "duration": 3}
    with TestingSession() as db:
        channel = db.get(SocialChannel, channel_id)
        with pytest.raises(social_inbound.MediaNotFetched):
            asyncio.run(telegram.process_update(db, channel, update(None, voice=voice), last_attempt=False))
        asyncio.run(telegram.process_update(db, channel, update(None, voice=voice)))
        assert db.scalar(select(Message.content).where(Message.role == "user")) == "[Attachment unavailable]"


def test_a_blocked_bot_fails_the_message_but_keeps_the_channel(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    channel = connect(authenticated_client, resource).json()
    with TestingSession() as db:
        secret = db.get(SocialChannel, uuid.UUID(channel["id"])).webhook_verify_token
    post_update(authenticated_client, channel["id"], update(), secret)
    monkeypatch.setattr(telegram_api, "send_text", AsyncMock(side_effect=HTTPException(409, "The contact blocked the bot")))
    with TestingSession() as db:
        run_worker(db)
        assert db.scalar(select(SocialOutbox.status)) == "failed"
        assert db.get(SocialChannel, uuid.UUID(channel["id"])).status == "connected"


def test_a_revoked_token_asks_for_the_bot_again(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    channel = connect(authenticated_client, resource).json()
    with TestingSession() as db:
        secret = db.get(SocialChannel, uuid.UUID(channel["id"])).webhook_verify_token
    post_update(authenticated_client, channel["id"], update(), secret)
    monkeypatch.setattr(telegram_api, "send_text", AsyncMock(side_effect=HTTPException(401, "Telegram rejected the bot token")))
    with TestingSession() as db:
        run_worker(db)
        assert db.get(SocialChannel, uuid.UUID(channel["id"])).status == "reauthorization_required"


def test_operator_files_and_text_leave_through_the_bot(authenticated_client):
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    with TestingSession() as db:
        channel = db.get(SocialChannel, channel_id)
        asyncio.run(telegram.process_update(db, channel, update()))
        conversation = db.scalar(select(Conversation))
        conversation.mode = "human"
        conversation.social_reply_due_at = None
        message = Message(conversation_id=conversation.id, role="assistant", sender_type="human", sender_name="Operator", content="Mira")
        db.add(message)
        db.flush()
        attachment = MessageAttachment(message_id=message.id, kind="image", mime="image/png", size_bytes=8, data=b"\x89PNG\r\n\x1a\n")
        db.add(attachment)
        db.flush()
        social_delivery.queue_message(db, conversation, message, attachment=attachment)
        db.commit()
        asyncio.run(social_delivery.process_outbox(db))
        assert {row.status for row in db.scalars(select(SocialOutbox))} == {"sent"}
    assert telegram_api.send_file.await_args.args[2:4] == ("image", b"\x89PNG\r\n\x1a\n")
    assert telegram_api.send_text.await_args.args[2] == "Mira"


def test_a_bot_has_no_reply_window(authenticated_client):
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    with TestingSession() as db:
        channel = db.get(SocialChannel, channel_id)
        asyncio.run(telegram.process_update(db, channel, update()))
        conversation = db.scalar(select(Conversation))
        conversation.social_last_inbound_at = now_utc().replace(year=2020)
        fields = window_fields(conversation)
        assert fields["reply_window_open"] and fields["human_reply_window_open"]
        assert fields["reply_window_until"] is None and fields["reply_block_reason"] is None


def test_token_refresh_leaves_bots_alone(authenticated_client, monkeypatch):
    resource = resources(authenticated_client)
    channel_id = uuid.UUID(connect(authenticated_client, resource).json()["id"])
    from app.services import social_graph
    monkeypatch.setattr(social_graph, "verify_account", AsyncMock(side_effect=AssertionError("Meta was called")))
    with TestingSession() as db:
        asyncio.run(social_connections.refresh_due_channels(db))
        channel = db.get(SocialChannel, channel_id)
        assert channel.status == "connected" and channel.last_error is None


def test_disconnecting_stops_the_webhook_and_releases_the_bot(authenticated_client, stub_bot_api):
    resource = resources(authenticated_client)
    channel_id = connect(authenticated_client, resource).json()["id"]
    response = authenticated_client.post(f"/api/telegram/channels/{channel_id}/disconnect")
    assert response.status_code == 204
    telegram_api.delete_webhook.assert_awaited_once_with(TOKEN)
    assert stub_bot_api.hooks[-1] == (uuid.UUID(channel_id), "unlinked")
    with TestingSession() as db:
        assert db.scalar(select(func.count(SocialChannel.id))) == 0


def test_renaming_and_reassigning_keeps_the_token(authenticated_client):
    resource = resources(authenticated_client)
    channel_id = connect(authenticated_client, resource).json()["id"]
    response = authenticated_client.patch(f"/api/telegram/channels/{channel_id}", json={"label": "Soporte"})
    assert response.status_code == 200 and response.json()["label"] == "Soporte"
    telegram_api.get_me.assert_awaited_once()


def test_markdown_becomes_telegram_html():
    shaped = telegram_api.markdown_to_telegram_html(
        "## Envíos\n**Gratis** desde $50 <hoy> & ~~mañana~~\n* uno\n`a*b*c` [web](https://shop.test/a?b=1&c=2)")
    assert shaped == ('<b>Envíos</b>\n<b>Gratis</b> desde $50 &lt;hoy&gt; &amp; <s>mañana</s>\n• uno\n'
                      '<code>a*b*c</code> <a href="https://shop.test/a?b=1&amp;c=2">web</a>')
    assert telegram_api.markdown_to_telegram_html("snake_case_name y 2*3*4") == "snake_case_name y 2*3*4"
    assert telegram_api.strip_markdown("**Hola** [web](https://x.test)") == "Hola web (https://x.test)"


def test_bot_tokens_never_reach_the_logs():
    record = SimpleNamespace(msg="HTTP Request: %s %s", args=("POST", f"https://api.telegram.org/bot{TOKEN}/sendMessage"))
    telegram_api._RedactBotTokens().filter(record)
    assert TOKEN not in record.args[1] and record.args[1].endswith("/bot[redacted]/sendMessage")


def test_typing_is_repeated_until_the_reply_leaves(monkeypatch):
    sent = []

    async def typing(token, chat):
        sent.append(chat)

    monkeypatch.setattr(telegram_api, "send_typing", typing)
    monkeypatch.setattr(telegram_api, "TYPING_REPEAT_SECONDS", 0.01)

    async def scenario():
        await telegram_api.keep_typing(TOKEN, "42")
        await asyncio.sleep(0.05)
        telegram_api.stop_typing(TOKEN, "42")
        repeated = len(sent)
        await asyncio.sleep(0.05)
        return repeated

    repeated = asyncio.run(scenario())
    assert repeated >= 2 and len(sent) == repeated
    assert not telegram_api._typing
