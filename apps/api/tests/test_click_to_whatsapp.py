"""The ad referral a click-to-chat message carries is kept on the conversation."""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from test_whatsapp_cloud import _post_signed, _setup_channel, _webhook_payload

from app.routers import whatsapp_cloud_webhook as webhook_router
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services import whatsapp_inbound as whatsapp_inbound_service

REFERRAL = {
    "source_url": "https://fb.me/abc",
    "source_type": "ad",
    "source_id": "120210000000001",
    "headline": "Gafas al 20%",
    "body": "Escríbenos por WhatsApp",
    "media_type": "image",
    "image_url": "https://cdn.example/expiring.jpg",
    "ctwa_clid": "AfQ3x",
}


def test_parse_referral_keeps_what_identifies_the_ad():
    assert webhook_router.parse_referral(REFERRAL) == {
        "source_type": "ad",
        "source_id": "120210000000001",
        "source_url": "https://fb.me/abc",
        "headline": "Gafas al 20%",
        "body": "Escríbenos por WhatsApp",
        "media_type": "image",
        "ctwa_clid": "AfQ3x",
    }
    assert webhook_router.parse_referral(None) is None
    assert webhook_router.parse_referral({}) is None
    assert webhook_router.parse_referral({"image_url": "x"}) is None
    assert webhook_router.parse_referral("junk") is None

    message = {"from": "5730011", "id": "wamid.1", "type": "text", "text": {"body": "Hola"}, "referral": REFERRAL}
    inbound = webhook_router.parse_message(message, {})
    assert inbound.referral["ctwa_clid"] == "AfQ3x"
    assert webhook_router.parse_message({"from": "5730011", "id": "wamid.2", "type": "text", "text": {"body": "Hola"}}, {}).referral is None


def _silence_replies(monkeypatch):
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", AsyncMock(return_value=ai_service.Completion(text="ok")))
    monkeypatch.setattr(webhook_router, "send_text", AsyncMock(side_effect=[f"wamid.out-{n}" for n in range(9)]))
    monkeypatch.setattr(whatsapp_service, "mark_read_with_typing", AsyncMock())


def test_the_case_keeps_the_referral_of_the_message_that_opened_it(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    _silence_replies(monkeypatch)

    first = {"from": "5730011", "id": "wamid.in-1", "type": "text", "text": {"body": "Vi el anuncio"}, "referral": REFERRAL}
    assert _post_signed(client, channel["id"], _webhook_payload([first])).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["acquisition"]["source_id"] == "120210000000001"
    assert detail["acquisition"]["ctwa_clid"] == "AfQ3x"
    assert "image_url" not in detail["acquisition"]

    # A later click on another ad lands in the open case and does not replace what opened it.
    second = {"from": "5730011", "id": "wamid.in-2", "type": "text", "text": {"body": "Y este?"}, "referral": {**REFERRAL, "source_id": "999"}}
    assert _post_signed(client, channel["id"], _webhook_payload([second])).status_code == 200
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["acquisition"]["source_id"] == "120210000000001"
    assert len(client.get("/api/conversations").json()) == 1


def test_a_message_without_referral_leaves_acquisition_empty(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _customer, _agent, channel = _setup_channel(client)
    _silence_replies(monkeypatch)
    plain = {"from": "5730022", "id": "wamid.in-3", "type": "text", "text": {"body": "Hola"}}
    assert _post_signed(client, channel["id"], _webhook_payload([plain])).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert client.get(f"/api/conversations/{conversation['id']}").json()["acquisition"] is None
