import asyncio
import base64
import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.routers import agents as agents_router
from app.routers import clients as clients_router
from app.routers import providers as providers_router
from app.routers import conversations as conversations_router
from app.routers import widget as widget_router
from app.config import get_settings
from app.database import SessionLocal
from app.models import Message
from app.services import ai as ai_service
from app.services import whatsapp_inbound as whatsapp_inbound_service


def _fake_http(monkeypatch, captured, response_json):
    class FakeResponse:
        status_code = 200

        def json(self):
            return response_json

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: FakeClient())


def test_openai_uses_responses_api(monkeypatch):
    captured = {}
    _fake_http(monkeypatch, captured, {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]})
    answer = asyncio.run(
        ai_service.chat_completion(
            "openai", "https://api.openai.test/v1", "secret", "gpt-5",
            [{"role": "system", "content": "Be brief"}, {"role": "user", "content": "Hello"}],
        )
    )
    assert answer.text == "OK"
    assert captured["url"].endswith("/responses")
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["payload"]["instructions"] == "Be brief"
    assert captured["payload"]["input"] == [{"role": "user", "content": "Hello"}]
    assert "temperature" not in captured["payload"]  # no sampling params passed


def test_anthropic_uses_messages_api(monkeypatch):
    captured = {}
    _fake_http(monkeypatch, captured, {"content": [{"type": "text", "text": "Hola"}]})
    answer = asyncio.run(
        ai_service.chat_completion(
            "anthropic", "https://api.anthropic.test/v1", "key", "claude-opus-4-8",
            [{"role": "system", "content": "Be brief"}, {"role": "user", "content": "Hi"}],
            max_tokens=100,
        )
    )
    assert answer.text == "Hola"
    assert captured["url"].endswith("/messages")
    assert captured["headers"]["x-api-key"] == "key"
    assert captured["headers"]["anthropic-version"] == ai_service.ANTHROPIC_VERSION
    assert captured["payload"]["system"] == "Be brief"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert captured["payload"]["max_tokens"] == 100


def test_register_login_logout_and_me(client: TestClient):
    payload = {
        "agency_name": "North Studio",
        "name": "Laura Mendez",
        "email": "laura@norte.com",
        "password": "very-secure-key",
    }
    created = client.post("/api/auth/register", json=payload)
    assert created.status_code == 201
    assert created.json()["agency"]["name"] == "North Studio"
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": payload["email"], "password": payload["password"]}).status_code == 200


def test_single_agency_instance_closes_registration(client: TestClient):
    status = client.get("/api/auth/status").json()
    assert status == {"needs_setup": True, "registration_open": True}

    first = client.post(
        "/api/auth/register",
        json={"agency_name": "North Studio", "name": "Laura", "email": "laura@norte.com", "password": "very-secure-key"},
    )
    assert first.status_code == 201

    status = client.get("/api/auth/status").json()
    assert status == {"needs_setup": False, "registration_open": False}

    second = client.post(
        "/api/auth/register",
        json={"agency_name": "South Studio", "name": "Mario", "email": "mario@sur.com", "password": "very-secure-key"},
    )
    assert second.status_code == 403

    # Existing users still sign in normally.
    assert client.post("/api/auth/login", json={"email": "laura@norte.com", "password": "very-secure-key"}).status_code == 200


def test_multi_agency_flag_keeps_registration_open(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_multi_agency", True)

    first = client.post(
        "/api/auth/register",
        json={"agency_name": "North Studio", "name": "Laura", "email": "laura@norte.com", "password": "very-secure-key"},
    )
    assert first.status_code == 201

    status = client.get("/api/auth/status").json()
    assert status == {"needs_setup": False, "registration_open": True}

    second = client.post(
        "/api/auth/register",
        json={"agency_name": "South Studio", "name": "Mario", "email": "mario@sur.com", "password": "very-secure-key"},
    )
    assert second.status_code == 201


def test_provider_key_is_stored_masked(authenticated_client: TestClient):
    saved = authenticated_client.put("/api/providers/openai", json={"api_key": "sk-super-secret-key"})
    assert saved.status_code == 200
    assert saved.json()["configured"] is True
    assert saved.json()["api_key_masked"] != "sk-super-secret-key"
    assert "encrypted_api_key" not in saved.json()

    listed = authenticated_client.get("/api/providers").json()
    assert {p["provider"] for p in listed} == {"openai", "anthropic"}
    assert next(p for p in listed if p["provider"] == "openai")["configured"] is True


def test_main_crud_knowledge_and_persistent_chat(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={
            "name": "Aurora Clinic",
            "industry": "Health",
            "description": "Dermatology clinic",
            "general_context": "Open Monday through Friday.",
            "is_active": True,
        },
    )
    assert customer.status_code == 201
    client_id = customer.json()["id"]

    key = client.put("/api/providers/openai", json={"api_key": "sk-super-secret-key"})
    assert key.status_code == 200

    agent = client.post(
        "/api/agents",
        json={
            "client_id": client_id,
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "timezone": "America/Bogota",
            "name": "Aurora Advisor",
            "description": "Answers frequently asked questions",
            "instructions": "Only answer questions about the clinic's services.",
            "personality": "Warm and clear",
            "is_active": True,
        },
    )
    assert agent.status_code == 201
    assert agent.json()["timezone"] == "America/Bogota"
    agent_id = agent.json()["id"]

    context = client.put(f"/api/agents/{agent_id}/context", json={"manual_context": "Does not offer emergency care."})
    assert context.status_code == 200
    assert context.json()["manual_context"] == "Does not offer emergency care."

    class FakePage:
        def extract_text(self):
            return "The warranty on treatments lasts two years."

    class FakeReader:
        def __init__(self, _path):
            self.pages = [FakePage()]

    monkeypatch.setattr(agents_router, "PdfReader", FakeReader)
    monkeypatch.setattr(agents_router, "embed_document_chunks", AsyncMock(return_value=0))
    uploaded = client.post(
        f"/api/agents/{agent_id}/documents",
        files={"file": ("garantias.pdf", b"%PDF-test", "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["status"] == "processed"
    assert uploaded.json()["character_count"] > 0

    conversation = client.post("/api/conversations", json={"agent_id": agent_id})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    fake_completion = AsyncMock(return_value=ai_service.Completion(text="The stated warranty is two years."))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    sent = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "How long does the warranty last?"},
    )
    assert sent.status_code == 200, sent.text
    messages = sent.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["sources"][0]["filename"] == "garantias.pdf"
    prompt = fake_completion.await_args.args[4][0]["content"]
    assert "Does not offer emergency care" in prompt
    assert "warranty" in prompt

    reloaded = client.get(f"/api/conversations/{conversation_id}")
    assert reloaded.status_code == 200
    assert len(reloaded.json()["messages"]) == 2

    assert client.patch(f"/api/clients/{client_id}", json={"is_active": False}).json()["is_active"] is False
    assert client.delete(f"/api/agents/{agent_id}").status_code == 204


def test_widget_public_chat_and_gating(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Widget Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Sofia", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    public_id = agent["widget_public_id"]

    # Disabled by default -> not exposed.
    assert client.get(f"/api/widget/{public_id}").status_code == 404

    enabled = client.patch(f"/api/agents/{agent['id']}", json={"widget_enabled": True, "widget_greeting": "Hi!", "widget_color": "#075985"}).json()
    assert enabled["widget_enabled"] is True

    config = client.get(f"/api/widget/{public_id}")
    assert config.status_code == 200
    assert config.json()["title"] == "Sofia"
    assert config.json()["greeting"] == "Hi!"

    monkeypatch.setattr(widget_router, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Sure, happy to help!")))
    sent = client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "hello"})
    assert sent.status_code == 200
    assert sent.json()["reply"] == "Sure, happy to help!"

    history = client.get(f"/api/widget/{public_id}/history?session_id=s1")
    assert [m["role"] for m in history.json()["messages"]] == ["user", "assistant"]

    # A visitor message left unanswered (human mode) marks the conversation unread.
    conversation_id = client.get("/api/conversations/inbox").json()[0]["id"]
    client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"})
    client.post(f"/api/widget/{public_id}/messages", json={"session_id": "s1", "content": "still there?"})
    inbox_row = next(row for row in client.get("/api/conversations/inbox").json() if row["id"] == conversation_id)
    assert inbox_row["unread"] is True
    assert inbox_row["unread_count"] >= 1

    assert client.post(f"/api/conversations/{conversation_id}/read").status_code == 204
    inbox_row = next(row for row in client.get("/api/conversations/inbox").json() if row["id"] == conversation_id)
    assert inbox_row["unread"] is False
    assert inbox_row["unread_count"] == 0


def test_inbox_pagination_and_search(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Paged Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Pager", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    for _ in range(3):
        client.post("/api/conversations", json={"agent_id": agent["id"]})

    page = client.get("/api/conversations/inbox?limit=2&offset=0").json()
    assert len(page) == 2
    page2 = client.get("/api/conversations/inbox?limit=2&offset=2").json()
    assert len(page2) >= 1
    assert {row["id"] for row in page}.isdisjoint({row["id"] for row in page2})

    # Server-side search over the conversation title.
    assert len(client.get("/api/conversations/inbox?search=New").json()) >= 1
    assert client.get("/api/conversations/inbox?search=zzznomatch").json() == []


def test_usage_recorded_and_reported(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Usage Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Meter", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()

    monkeypatch.setattr(conversations_router, "run_completion", AsyncMock(return_value=ai_service.Completion(text="Hi", input_tokens=12, output_tokens=8)))
    client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "hello"})

    metrics = client.get("/api/dashboard/metrics").json()
    assert metrics["tokens_in"] >= 12
    assert metrics["tokens_out"] >= 8
    assert any(item["model"] == "gpt-4.1-mini" for item in metrics["usage_by_model"])


def test_dashboard_metrics(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Metrics Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Counter", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    client.post("/api/conversations", json={"agent_id": agent["id"]})
    client.post("/api/conversations", json={"agent_id": agent["id"]})

    metrics = client.get("/api/dashboard/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert len(body["daily_conversations"]) == 14
    assert body["by_channel"].get("playground") == 2
    assert body["top_agents"][0]["name"] == "Counter"
    assert body["top_agents"][0]["conversations"] == 2

    ranged = client.get("/api/dashboard/metrics?days=30")
    assert ranged.status_code == 200
    assert len(ranged.json()["daily_conversations"]) == 30
    assert client.get("/api/dashboard/metrics?days=0").status_code == 422


def test_agent_qa_pairs_reach_prompt(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "FAQ Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Faq", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()

    created = client.post(f"/api/agents/{agent['id']}/qa", json={"question": "¿Horario?", "answer": "9am a 6pm"})
    assert created.status_code == 201
    assert client.get(f"/api/agents/{agent['id']}/qa").json()[0]["answer"] == "9am a 6pm"

    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="ok"))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "hola"})
    prompt = fake_completion.await_args.args[4][0]["content"]
    assert "PREGUNTAS FRECUENTES" in prompt
    assert "9am a 6pm" in prompt

    assert client.delete(f"/api/agents/{agent['id']}/qa/{created.json()['id']}").status_code == 204
    assert client.get(f"/api/agents/{agent['id']}/qa").json() == []


def test_agent_brief_persists_and_reaches_prompt(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Brief Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini",
            "name": "Brief", "brief_summary": "A bakery", "brief_donts": "Never promise same-day delivery",
            "is_active": True,
        },
    ).json()
    assert agent["brief_summary"] == "A bakery"

    updated = client.patch(f"/api/agents/{agent['id']}", json={"brief_goal": "Take cake orders"}).json()
    assert updated["brief_goal"] == "Take cake orders"
    assert updated["brief_summary"] == "A bakery"

    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="ok"))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "hola"})
    prompt = fake_completion.await_args.args[4][0]["content"]
    assert "BRIEF DEL NEGOCIO" in prompt
    assert "A bakery" in prompt
    assert "Take cake orders" in prompt
    assert "Never promise same-day delivery" in prompt


def test_custom_portal_domain_flow(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Brand", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "Owner", "email": "owner@brand.com", "password": "portal-password"},
    )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})

    body = client.put(f"/api/clients/{customer['id']}/domain", json={"domain": "Chat.Brand.com"}).json()
    assert body["domain"] == "chat.brand.com"
    assert body["verified"] is False
    assert body["txt_host"] == "_openlivery-challenge.chat.brand.com"
    token = body["txt_value"]
    assert token

    # Unverified domains are not routable.
    assert client.get("/api/public/portal-domain?domain=chat.brand.com").status_code == 404

    monkeypatch.setattr(
        clients_router.dns_service, "txt_contains",
        lambda domain, tok: domain == "chat.brand.com" and tok == token,
    )
    verify = client.post(f"/api/clients/{customer['id']}/domain/verify")
    assert verify.status_code == 200
    assert verify.json()["verified"] is True

    resolved = client.get("/api/public/portal-domain?domain=chat.brand.com")
    assert resolved.status_code == 200
    assert resolved.json()["portal_slug"] == customer["portal_slug"]

    # The same domain cannot be claimed by another client.
    other = client.post(
        "/api/clients",
        json={"name": "Other", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    assert client.put(f"/api/clients/{other['id']}/domain", json={"domain": "chat.brand.com"}).status_code == 409

    assert client.delete(f"/api/clients/{customer['id']}/domain").json()["domain"] is None
    assert client.get("/api/public/portal-domain?domain=chat.brand.com").status_code == 404


def test_media_message_uses_image_capability(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Pizza Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "image_enabled": True, "name": "Waiter", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    assert agent["image_enabled"] is True
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()

    monkeypatch.setattr(whatsapp_inbound_service, "describe_image", AsyncMock(return_value="a red pepperoni pizza"))
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Looks delicious!"))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    sent = client.post(
        f"/api/conversations/{conversation['id']}/media",
        files={"file": ("photo.jpg", b"\xff\xd8fakejpeg", "image/jpeg")},
        data={"caption": "What is this?"},
    )
    assert sent.status_code == 200, sent.text
    messages = sent.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    # The chat shows the caption plus the original file; the description only goes to the LLM.
    assert messages[0]["content"] == "What is this?"
    attachments = messages[0]["attachments"]
    assert len(attachments) == 1 and attachments[0]["kind"] == "image" and attachments[0]["mime"] == "image/jpeg"
    prompt_messages = fake_completion.await_args.args[4]
    assert any("a red pepperoni pizza" in message["content"] for message in prompt_messages)

    served = client.get(f"/api/conversations/{conversation['id']}/attachments/{attachments[0]['id']}")
    assert served.status_code == 200
    assert served.content == b"\xff\xd8fakejpeg"
    assert served.headers["content-type"].startswith("image/jpeg")


def test_media_message_without_capability_uses_placeholder(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Shop", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Bot", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Got it"))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    sent = client.post(
        f"/api/conversations/{conversation['id']}/media",
        files={"file": ("photo.jpg", b"\xff\xd8fakejpeg", "image/jpeg")},
    )
    # The attachment is stored and shown either way; the LLM just gets a placeholder.
    assert sent.status_code == 200, sent.text
    messages = sent.json()["messages"]
    assert messages[0]["content"] == ""
    assert messages[0]["attachments"][0]["kind"] == "image"
    prompt_messages = fake_completion.await_args.args[4]
    assert any("[El cliente envió una imagen]" in message["content"] for message in prompt_messages)


def test_agent_without_model_explains_configuration(authenticated_client: TestClient):
    customer = authenticated_client.post(
        "/api/clients",
        json={"name": "Client", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    agent = authenticated_client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Agent", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    conversation = authenticated_client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    response = authenticated_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "Hello"},
    )
    assert response.status_code == 400
    assert "not ready" in response.json()["detail"]


def test_white_label_portal_and_human_takeover(authenticated_client: TestClient):
    client = authenticated_client
    agency = client.patch(
        "/api/agency",
        json={"name": "Prisma Studio Agency", "slug": "prisma-studio", "brand_color": "#635BFF"},
    )
    assert agency.status_code == 200
    assert agency.json()["slug"] == "prisma-studio"
    logo = client.post("/api/agency/logo", files={"file": ("logo.png", b"fake-png", "image/png")})
    assert logo.status_code == 200
    assert logo.json()["logo_url"]

    customer = client.post(
        "/api/clients",
        json={"name": "Luna Café", "industry": "Restaurants", "description": "", "general_context": "", "is_active": True},
    ).json()
    client_id = customer["id"]
    assert customer["portal_slug"] == "luna-cafe"

    missing_credentials = client.patch(f"/api/clients/{client_id}/portal", json={"portal_enabled": True})
    assert missing_credentials.status_code == 400
    created_user = client.post(
        f"/api/clients/{client_id}/portal-users",
        json={"name": "Equipo", "email": "equipo@luna.com", "password": "secure-portal"},
    )
    assert created_user.status_code == 201
    configured = client.patch(
        f"/api/clients/{client_id}/portal",
        json={"portal_enabled": True, "portal_title": "Luna Inbox"},
    )
    assert configured.status_code == 200
    assert "password" not in str(configured.json()).lower()

    agent = client.post(
        "/api/agents",
        json={"client_id": client_id, "name": "Host", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()

    public = client.get(f"/api/portal/{customer['portal_slug']}")
    assert public.status_code == 200
    assert public.json()["portal_title"] == "Luna Inbox"
    logged_in = client.post(
        f"/api/portal/{customer['portal_slug']}/login",
        json={"email": "equipo@luna.com", "password": "secure-portal"},
    )
    assert logged_in.status_code == 200
    inbox = client.get(f"/api/portal/{customer['portal_slug']}/conversations")
    assert inbox.status_code == 200
    assert inbox.json()[0]["id"] == conversation["id"]
    assert inbox.json()[0]["preview"] == ""

    takeover = client.patch(
        f"/api/portal/{customer['portal_slug']}/conversations/{conversation['id']}/mode",
        json={"mode": "human"},
    )
    assert takeover.status_code == 200
    replied = client.post(
        f"/api/portal/{customer['portal_slug']}/conversations/{conversation['id']}/reply",
        json={"content": "Hi, I'm part of the Luna team."},
    )
    assert replied.status_code == 200
    assert replied.json()["messages"][-1]["sender_type"] == "human"
    inbox_after = client.get(f"/api/portal/{customer['portal_slug']}/conversations")
    assert inbox_after.json()[0]["preview"] == "Hi, I'm part of the Luna team."


def test_portal_inbox_pages_searches_and_tracks_unread(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Paged Portal", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "Ana", "email": "ana@paged.com", "password": "secure-portal"},
    )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Pager", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    ids = [client.post("/api/conversations", json={"agent_id": agent["id"]}).json()["id"] for _ in range(3)]
    slug = customer["portal_slug"]
    client.post(f"/api/portal/{slug}/login", json={"email": "ana@paged.com", "password": "secure-portal"})

    page = client.get(f"/api/portal/{slug}/conversations?limit=2&offset=0").json()
    assert len(page) == 2
    page2 = client.get(f"/api/portal/{slug}/conversations?limit=2&offset=2").json()
    assert len(page2) == 1
    assert {row["id"] for row in page}.isdisjoint({row["id"] for row in page2})

    assert len(client.get(f"/api/portal/{slug}/conversations?search=New").json()) == 3
    assert client.get(f"/api/portal/{slug}/conversations?search=zzznomatch").json() == []

    # A visitor message counts as unread until the portal marks the thread
    # read, but only once a person holds the conversation: while the AI
    # answers there is nothing for anyone to catch up on.
    with SessionLocal() as db:
        db.add(Message(conversation_id=uuid.UUID(ids[0]), role="user", content="Hola", sender_type="visitor"))
        db.commit()
    assert client.get(f"/api/portal/{slug}/conversations?unread=1").json() == []
    client.patch(f"/api/portal/{slug}/conversations/{ids[0]}/mode", json={"mode": "human"})
    assert client.get(f"/api/portal/{slug}/conversations/summary").json() == {"open": 3, "resolved": 0, "human": 1, "ai": 2, "unread": 1}
    unread = client.get(f"/api/portal/{slug}/conversations?unread=1").json()
    assert [row["id"] for row in unread] == [ids[0]]
    assert unread[0]["unread_count"] == 1
    assert client.post(f"/api/portal/{slug}/conversations/{ids[0]}/read").status_code == 204
    assert client.get(f"/api/portal/{slug}/conversations?unread=1").json() == []
    assert all(row["unread"] is False for row in client.get(f"/api/portal/{slug}/conversations").json())

    # Mode filtering happens server-side, so tabs and paging agree.
    client.patch(f"/api/portal/{slug}/conversations/{ids[1]}/mode", json={"mode": "human"})
    assert {row["id"] for row in client.get(f"/api/portal/{slug}/conversations?mode=human").json()} == {ids[0], ids[1]}
    assert [row["id"] for row in client.get(f"/api/portal/{slug}/conversations?mode=ai").json()] == [ids[2]]


def test_portal_resolves_reopens_and_narrates_the_thread(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Status Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.post(
        f"/api/clients/{customer['id']}/portal-users",
        json={"name": "Ana", "email": "ana@status.com", "password": "secure-portal"},
    )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    conversation_id = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()["id"]
    slug = customer["portal_slug"]
    base = f"/api/portal/{slug}/conversations"
    client.post(f"/api/portal/{slug}/login", json={"email": "ana@status.com", "password": "secure-portal"})

    assert client.get(f"{base}/{conversation_id}").json()["status"] == "open"
    assert [row["id"] for row in client.get(f"{base}?status=open").json()] == [conversation_id]
    assert client.get(f"{base}?status=resolved").json() == []

    resolved = client.patch(f"{base}/{conversation_id}/status", json={"status": "resolved"})
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved" and body["resolved_at"]
    trail = body["messages"][-1]
    assert trail["kind"] == "activity"
    assert trail["activity"] == {"event": "resolved"}
    assert trail["sender_name"] == "Ana"
    assert client.get(f"{base}?status=open").json() == []
    assert [row["id"] for row in client.get(f"{base}?status=resolved").json()] == [conversation_id]
    # Pressing the button twice leaves a single line in the thread.
    again = client.patch(f"{base}/{conversation_id}/status", json={"status": "resolved"}).json()
    assert len([m for m in again["messages"] if m["kind"] == "activity"]) == 1
    assert client.patch(f"{base}/{conversation_id}/status", json={"status": "snoozed"}).status_code == 422

    reopened = client.patch(f"{base}/{conversation_id}/status", json={"status": "open"}).json()
    assert reopened["status"] == "open" and reopened["resolved_at"] is None
    assert reopened["messages"][-1]["activity"] == {"event": "reopened"}

    # Who answers is narrated too, and the preview never shows an activity line.
    taken = client.patch(f"{base}/{conversation_id}/mode", json={"mode": "human"}).json()
    assert taken["messages"][-1]["activity"] == {"event": "taken_over"}
    assert client.get(base).json()[0]["preview"] == ""
    client.post(f"{base}/{conversation_id}/reply", json={"content": "On it."})
    detail = client.get(f"{base}/{conversation_id}").json()
    assert detail["first_reply_at"] and detail["waiting_since"] is None


def test_activity_never_reaches_the_model_and_a_resolved_case_stays_closed(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Reopen Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Host", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    headers = {"X-Bridge-Token": get_settings().whatsapp_bridge_token}
    completion = AsyncMock(return_value=ai_service.Completion(text="Hello!", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", completion)
    monkeypatch.setattr(whatsapp_inbound_service.get_settings(), "reply_debounce_seconds", 0)

    def inbound(message_id: str, text: str):
        return client.post(
            f"/api/internal/whatsapp/channels/{channel['id']}/inbound",
            json={"external_message_id": message_id, "remote_jid": "573001112233@s.whatsapp.net", "sender_name": "Sam", "text": text},
            headers=headers,
        )

    first = inbound("m1", "Hola")
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["first_reply_at"] and detail["waiting_since"] is None

    # Taking over and handing back leave activity lines in the thread...
    client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"})
    client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "ai"})
    inbound("m2", "Una cosa más")
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    events = [m["activity"]["event"] for m in detail["messages"] if m["kind"] == "activity"]
    assert events == ["taken_over", "returned_to_ai"]
    # ...that the model never sees: it only gets what was exchanged.
    sent = completion.call_args.args[4]
    assert [m["role"] for m in sent if m["role"] != "system"] == ["user", "assistant", "user"]
    assert not any("took over" in m["content"] for m in sent)

    # Once resolved, a case stays resolved; the next message opens a new one.
    client.patch(f"/api/conversations/{conversation_id}/status", json={"status": "resolved"})
    third = inbound("m3", "Otra cosa").json()
    assert third["conversation_id"] != conversation_id
    assert client.get(f"/api/conversations/{conversation_id}").json()["status"] == "resolved"
    assert client.get(f"/api/conversations/{third['conversation_id']}").json()["status"] == "open"


def test_idle_ai_conversations_resolve_themselves_but_human_ones_wait(authenticated_client: TestClient):
    from datetime import timedelta

    from app.models import Conversation, now_utc
    from app.services.conversation_state import resolve_idle_ai_conversations

    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Idle Co", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "description": "", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    ai_id = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()["id"]
    human_id = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()["id"]
    fresh_id = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()["id"]
    client.patch(f"/api/conversations/{human_id}/mode", json={"mode": "human"})

    two_days_ago = now_utc() - timedelta(days=2)
    with SessionLocal() as db:
        for cid in (ai_id, human_id):
            db.add(Message(conversation_id=uuid.UUID(cid), role="user", content="Hola", sender_type="visitor", created_at=two_days_ago))
            db.get(Conversation, uuid.UUID(cid)).created_at = two_days_ago
        db.add(Message(conversation_id=uuid.UUID(fresh_id), role="user", content="Hola", sender_type="visitor"))
        db.commit()
        assert resolve_idle_ai_conversations(db, hours=24) == 1
        assert resolve_idle_ai_conversations(db, hours=24) == 0

    idle = client.get(f"/api/conversations/{ai_id}").json()
    assert idle["status"] == "resolved"
    assert idle["messages"][-1]["activity"] == {"event": "auto_resolved", "hours": 24}
    assert client.get(f"/api/conversations/{human_id}").json()["status"] == "open"
    assert client.get(f"/api/conversations/{fresh_id}").json()["status"] == "open"


def test_provider_test_returns_models(authenticated_client: TestClient, monkeypatch):
    authenticated_client.put("/api/providers/openai", json={"api_key": "secret"})
    fake = AsyncMock(return_value={"ok": True, "message": "Key verified. 2 models available.", "models": ["model-a", "model-b"]})
    monkeypatch.setattr(providers_router, "test_provider", fake)
    tested = authenticated_client.post("/api/providers/openai/test")
    assert tested.status_code == 200
    assert tested.json()["models"] == ["model-a", "model-b"]


def test_whatsapp_inbound_image_uses_capability(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Bistro", "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "image_enabled": True, "name": "Host", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    channel = client.put(f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}).json()
    headers = {"X-Bridge-Token": get_settings().whatsapp_bridge_token}

    monkeypatch.setattr(whatsapp_inbound_service, "describe_image", AsyncMock(return_value="a photo of the menu"))
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Here are the dishes!"))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    inbound = client.post(
        f"/api/internal/whatsapp/channels/{channel['id']}/inbound",
        headers=headers,
        json={
            "external_message_id": "wa-img-1",
            "remote_jid": "573001112233@s.whatsapp.net",
            "sender_name": "Ana",
            "media_kind": "image",
            "media_base64": base64.b64encode(b"fake-image-bytes").decode(),
            "media_mime": "image/jpeg",
        },
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["reply"] == "Here are the dishes!"
    conversation_id = inbound.json()["conversation_id"]
    stored = client.get(f"/api/conversations/{conversation_id}").json()
    # No caption: the visible message is just the attachment; the description feeds the LLM.
    assert stored["messages"][0]["content"] == ""
    attachments = stored["messages"][0]["attachments"]
    assert len(attachments) == 1 and attachments[0]["kind"] == "image"
    served = client.get(f"/api/conversations/{conversation_id}/attachments/{attachments[0]['id']}")
    assert served.status_code == 200 and served.content == b"fake-image-bytes"
    prompt_messages = fake_completion.await_args.args[4]
    assert any("a photo of the menu" in message["content"] for message in prompt_messages)


def test_whatsapp_channel_inbound_ai_takeover_and_session(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Sol Store", "industry": "Retail", "description": "", "general_context": "Open Monday through Saturday.", "is_active": True},
    ).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Sol Advisor", "description": "", "instructions": "Help the customers.", "personality": "Friendly", "is_active": True},
    ).json()

    configured = client.put(
        f"/api/whatsapp/channels/{customer['id']}", json={"agent_id": agent["id"]}
    )
    assert configured.status_code == 200
    channel_id = configured.json()["id"]
    assert configured.json()["client_id"] == customer["id"]
    assert "encrypted_auth_state" not in configured.json()

    headers = {"X-Bridge-Token": get_settings().whatsapp_bridge_token}
    assert client.put(
        f"/api/internal/whatsapp/channels/{channel_id}/auth",
        headers=headers,
        json={"auth_state": {"creds": {"registered": True}, "keys": {"session": {"one": {"type": "Buffer", "data": [1, 2]}}}}},
    ).status_code == 204
    assert client.put(
        f"/api/internal/whatsapp/channels/{channel_id}/status",
        headers=headers,
        json={"status": "qr", "qr_code": "data:image/png;base64,cXItc2VndXJv"},
    ).status_code == 204
    public_channel = client.get(f"/api/whatsapp/channels/{customer['id']}").json()
    assert public_channel["has_session"] is True
    assert public_channel["qr_code"] == "data:image/png;base64,cXItc2VndXJv"
    assert client.get(f"/api/internal/whatsapp/channels/{channel_id}").status_code == 401
    restored = client.get(f"/api/internal/whatsapp/channels/{channel_id}", headers=headers).json()
    assert restored["auth_state"]["creds"]["registered"] is True

    fake_completion = AsyncMock(return_value=ai_service.Completion(text="Yes, we are open Monday through Saturday."))
    monkeypatch.setattr(whatsapp_inbound_service, "run_completion", fake_completion)
    inbound = client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers=headers,
        json={
            "external_message_id": "wa-in-1",
            "remote_jid": "573001112233@s.whatsapp.net",
            "sender_name": "Maria",
            "text": "What days are you open?",
        },
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["reply"] == "Yes, we are open Monday through Saturday."
    conversation_id = inbound.json()["conversation_id"]
    inbox = client.get(f"/api/conversations/{conversation_id}").json()
    assert inbox["channel"] == "whatsapp"
    assert inbox["contact_name"] == "Maria"
    assert [item["sender_type"] for item in inbox["messages"]] == ["visitor", "ai"]

    duplicate = client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers=headers,
        json={"external_message_id": "wa-in-1", "remote_jid": "573001112233@s.whatsapp.net", "sender_name": "Maria", "text": "What days are you open?"},
    )
    assert duplicate.json()["accepted"] is False
    assert fake_completion.await_count == 1

    assert client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "human"}).status_code == 200
    human_inbound = client.post(
        f"/api/internal/whatsapp/channels/{channel_id}/inbound",
        headers=headers,
        json={"external_message_id": "wa-in-2", "remote_jid": "573001112233@s.whatsapp.net", "sender_name": "Maria", "text": "I need to speak with someone."},
    )
    assert human_inbound.json()["reply"] is None
    assert human_inbound.json()["mode"] == "human"
    assert fake_completion.await_count == 1

    sender = AsyncMock(return_value="wa-out-human-1")
    monkeypatch.setattr(conversations_router, "send_channel_message", sender)
    reply = client.post(
        f"/api/conversations/{conversation_id}/reply", json={"content": "Hi Maria, I'll assist you personally."}
    )
    assert reply.status_code == 200
    assert reply.json()["messages"][-1]["external_message_id"] == "wa-out-human-1"
    sender.assert_awaited_once()
    assert client.patch(f"/api/conversations/{conversation_id}/mode", json={"mode": "ai"}).json()["mode"] == "ai"
