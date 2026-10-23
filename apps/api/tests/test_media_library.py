"""The files an agent can send: the library endpoints, image normalization and
the ``send_file`` tool that turns a model's choice into a channel attachment."""

import asyncio
import uuid
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.models import AgentMediaAsset, Agent
from app.services import ai as ai_module
from app.services import media_library
from app.services.media_library import MAX_IMAGE_SIDE, build_media_spec, media_prompt, normalize_upload
from app.services.tools.loop import tool_loop
from conftest import TestingSession
from test_agent_tools import _ScriptedLLM, _patch_httpx, _setup_agent, _text_reply, _tool_call_reply


def _png(width: int, height: int, mode: str = "RGB") -> bytes:
    image = Image.new(mode, (width, height), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 120))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _add(client: TestClient, agent_id: str, name: str, data: bytes, filename: str, mime: str, description: str = ""):
    return client.post(
        f"/api/agents/{agent_id}/media",
        data={"name": name, "description": description},
        files={"file": (filename, data, mime)},
    )


def test_images_are_normalized_and_documents_kept(authenticated_client: TestClient):
    client = authenticated_client
    agent_id = _setup_agent(client)

    # A large opaque PNG comes back as a bounded JPEG.
    response = _add(client, agent_id, "Silla Nordica", _png(3200, 2000), "IMG_0001.PNG", "image/png", "When they ask about the chair")
    assert response.status_code == 201, response.text
    photo = response.json()
    assert photo["kind"] == "image"
    assert photo["mime"] == "image/jpeg"
    assert photo["filename"] == "IMG_0001.jpg"
    assert photo["description"] == "When they ask about the chair"
    content = client.get(f"/api/agents/{agent_id}/media/{photo['id']}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/jpeg")
    assert content.headers["content-disposition"].startswith("inline")
    with Image.open(BytesIO(content.content)) as stored:
        assert stored.format == "JPEG"
        assert max(stored.size) == MAX_IMAGE_SIDE
    assert photo["size_bytes"] == len(content.content) < len(_png(3200, 2000))

    # Transparency survives as PNG.
    response = _add(client, agent_id, "Logo", _png(400, 400, "RGBA"), "logo.png", "image/png")
    assert response.status_code == 201, response.text
    assert response.json()["mime"] == "image/png"
    assert response.json()["filename"] == "logo.png"

    # A PDF is stored as uploaded, and downloads rather than rendering inline.
    pdf = b"%PDF-1.4\n" + b"0" * 2000
    response = _add(client, agent_id, "Catalogo 2026", pdf, "catalogo", "application/octet-stream")
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "file"
    assert response.json()["mime"] == "application/pdf"
    assert response.json()["filename"] == "catalogo.pdf"
    content = client.get(f"/api/agents/{agent_id}/media/{response.json()['id']}/content")
    assert content.content == pdf
    assert content.headers["content-disposition"].startswith("attachment")

    listed = client.get(f"/api/agents/{agent_id}/media").json()
    assert [item["name"] for item in listed] == ["Silla Nordica", "Logo", "Catalogo 2026"]
    assert all("data" not in item for item in listed)


def test_upload_rules(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)

    assert _add(client, agent_id, "Notas", b"hello", "notes.txt", "text/plain").status_code == 400
    assert _add(client, agent_id, "Roto", b"not an image", "photo.jpg", "image/jpeg").status_code == 400
    assert _add(client, agent_id, "   ", _png(10, 10), "a.png", "image/png").status_code == 422
    assert _add(client, agent_id, "x" * 81, _png(10, 10), "a.png", "image/png").status_code == 422
    assert _add(client, agent_id, "Vacio", b"", "a.png", "image/png").status_code == 400
    monkeypatch.setattr(media_library, "MAX_IMAGE_UPLOAD_BYTES", 1024)
    from app.routers import agents as agents_router
    monkeypatch.setattr(agents_router, "upload_limit", lambda mime: 1024)
    assert _add(client, agent_id, "Grande", _png(900, 900), "big.png", "image/png").status_code == 413
    monkeypatch.setattr(agents_router, "upload_limit", media_library.upload_limit)

    first = _add(client, agent_id, "Silla", _png(10, 10), "a.png", "image/png")
    assert first.status_code == 201
    # Names are what the model picks from: unique per agent, ignoring case.
    assert _add(client, agent_id, "silla", _png(10, 10), "b.png", "image/png").status_code == 409

    monkeypatch.setattr(agents_router, "MAX_MEDIA_ASSETS", 1)
    assert _add(client, agent_id, "Mesa", _png(10, 10), "c.png", "image/png").status_code == 409
    monkeypatch.setattr(agents_router, "MAX_MEDIA_ASSETS", media_library.MAX_MEDIA_ASSETS)

    second = _add(client, agent_id, "Mesa", _png(10, 10), "c.png", "image/png").json()
    renamed = client.patch(f"/api/agents/{agent_id}/media/{second['id']}", json={"name": "Mesa redonda", "description": "  for  tables "})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Mesa redonda"
    assert renamed.json()["description"] == "for tables"
    assert client.patch(f"/api/agents/{agent_id}/media/{second['id']}", json={"name": "SILLA"}).status_code == 409

    assert client.delete(f"/api/agents/{agent_id}/media/{first.json()['id']}").status_code == 204
    assert [item["name"] for item in client.get(f"/api/agents/{agent_id}/media").json()] == ["Mesa redonda"]
    assert client.get(f"/api/agents/{agent_id}/media/{first.json()['id']}/content").status_code == 404


def test_normalize_bakes_exif_rotation():
    image = Image.new("RGB", (300, 100), (10, 20, 30))
    exif = image.getexif()
    exif[0x0112] = 6  # rotated 90 degrees clockwise
    out = BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    normalized = normalize_upload(out.getvalue(), "image/jpeg", "photo.jpeg")
    with Image.open(BytesIO(normalized.data)) as stored:
        assert stored.size == (100, 300)
        assert not stored.getexif().get(0x0112)


def test_send_file_tool_delivers_the_stored_bytes(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    photo = _add(client, agent_id, "Silla Nordica", _png(50, 50), "silla.png", "image/png", "When they ask about the chair").json()
    _add(client, agent_id, "Catalogo", b"%PDF-1.4\n" + b"0" * 2000, "catalogo.pdf", "application/pdf")

    with TestingSession() as db:
        agent = db.get(Agent, uuid.UUID(agent_id))
        spec = build_media_spec(db, agent)
        assert spec is not None
        assert spec.name == "send_file"
        assert spec.input_schema["properties"]["name"]["enum"] == ["Silla Nordica", "Catalogo"]
        assert "Silla Nordica: When they ask about the chair" in spec.description
        assert "send_file" in media_prompt(agent)
        stored = db.scalar(select(AgentMediaAsset.data).where(AgentMediaAsset.id == uuid.UUID(photo["id"])))

        llm_calls: list[dict] = []
        _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
            _tool_call_reply("call_1", "send_file", '{"name": "silla nordica"}'),
            _tool_call_reply("call_2", "send_file", '{"name": "Silla Nordica"}'),
            _tool_call_reply("call_3", "send_file", '{"name": "Mesa"}'),
            _text_reply("Here is the chair."),
        ], llm_calls))
        completion = asyncio.run(tool_loop(
            "https://openrouter.test/api/v1", "key", "openai/gpt-5.6-luna",
            [{"role": "user", "content": "Show me the chair"}], [spec], None, None,
        ))

    # The bytes rode out once, however many times the model asked, and never
    # entered the model's context.
    assert len(completion.attachments) == 1
    assert completion.attachments[0].data == stored
    assert completion.attachments[0].mime == "image/jpeg"
    assert completion.attachments[0].filename == "silla.jpg"
    assert completion.text == "Here is the chair."
    tool_messages = [m for m in llm_calls[-1]["payload"]["messages"] if m["role"] == "tool"]
    assert "delivered to the customer" in tool_messages[0]["content"]
    assert "already sent" in tool_messages[1]["content"]
    assert tool_messages[2]["content"].startswith("Tool call failed")
    assert "Silla Nordica, Catalogo" in tool_messages[2]["content"]
    for message in tool_messages:
        assert len(message["content"]) < 500


def test_playground_reply_carries_the_file(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    _add(client, agent_id, "Silla Nordica", _png(50, 50), "silla.png", "image/png", "When they ask about the chair")

    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
        _tool_call_reply("call_1", "send_file", '{"name": "Silla Nordica"}'),
        _text_reply("Here is the chair."),
    ], llm_calls))
    conversation = client.post("/api/conversations", json={"agent_id": agent_id}).json()
    detail = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Show me the chair"})
    assert detail.status_code == 200, detail.text

    # The model was offered the tool and the rules for it.
    first = llm_calls[0]["payload"]
    assert [tool["function"]["name"] for tool in first["tools"]] == ["send_file"]
    assert "send_file" in first["messages"][0]["content"]
    # The reply text and the image are two assistant messages, the image as an
    # attachment the playground renders like any operator photo.
    assistant = [m for m in detail.json()["messages"] if m["role"] == "assistant"]
    assert [m["content"] for m in assistant] == ["Here is the chair.", ""]
    attachments = assistant[1]["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["kind"] == "image"
    assert attachments[0]["filename"] == "silla.jpg"


def test_agent_without_files_gets_no_tool(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    with TestingSession() as db:
        agent = db.get(Agent, uuid.UUID(agent_id))
        assert build_media_spec(db, agent) is None

    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([_text_reply("Hello.")], llm_calls))
    conversation = client.post("/api/conversations", json={"agent_id": agent_id}).json()
    assert client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Hi"}).status_code == 200
    assert "tools" not in llm_calls[0]["payload"]
    assert "send_file" not in llm_calls[0]["payload"]["messages"][0]["content"]
