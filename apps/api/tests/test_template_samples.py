"""Header samples go through Meta's resumable upload, under the app id."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.services import whatsapp_templates as templates


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://graph.test/x"))


@pytest.mark.anyio
async def test_a_sample_becomes_a_handle(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_app_id", "APP1")
    opened = AsyncMock(return_value=_response(200, {"id": "upload:SESSION1"}))
    monkeypatch.setattr(templates, "graph_request", opened)
    posted = AsyncMock(return_value=_response(200, {"h": "4:handle"}))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = posted
    monkeypatch.setattr(templates.httpx, "AsyncClient", MagicMock(return_value=client))

    handle = await templates.upload_sample("tok", data=b"\x89PNG", mime="image/png", filename="promo.png")
    assert handle == "4:handle"
    # The session is opened under the app, with the file's size and type.
    assert opened.call_args.args[0] == "POST" and opened.call_args.args[1].endswith("/APP1/uploads")
    assert opened.call_args.kwargs["params"] == {"file_name": "promo.png", "file_length": 4, "file_type": "image/png"}
    # The bytes go to the session with Meta's OAuth header and offset.
    assert posted.call_args.args[0].endswith("/upload:SESSION1")
    assert posted.call_args.kwargs["headers"] == {"Authorization": "OAuth tok", "file_offset": "0"}
    assert posted.call_args.kwargs["content"] == b"\x89PNG"


@pytest.mark.anyio
async def test_samples_need_the_app_id(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_app_id", "")
    with pytest.raises(HTTPException) as caught:
        await templates.upload_sample("tok", data=b"x", mime="image/png", filename="a.png")
    assert caught.value.status_code == 409 and "WHATSAPP_APP_ID" in caught.value.detail


@pytest.mark.anyio
async def test_samples_are_checked_before_leaving():
    class Upload:
        def __init__(self, content_type, filename, data):
            self.content_type, self.filename, self._data = content_type, filename, data

        async def read(self, n):
            return self._data[:n]

    data, mime, name = await templates.read_sample(Upload("image/jpg", "../a b.jpg", b"jpg"))
    assert (data, mime, name) == (b"jpg", "image/jpeg", "a b.jpg")
    with pytest.raises(HTTPException) as caught:
        await templates.read_sample(Upload("image/gif", "a.gif", b"gif"))
    assert caught.value.status_code == 415
    with pytest.raises(HTTPException) as caught:
        await templates.read_sample(Upload("application/pdf", "big.pdf", b"x" * (templates.MAX_SAMPLE_BYTES + 1)))
    assert caught.value.status_code == 413
