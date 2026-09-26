import asyncio
import base64
import json
import types
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.models import AgentTool
from app.routers import agent_tools as agent_tools_router
from app.security import encrypt_secret
from app.services import ai as ai_module
from app.services.tool_files import extract_tool_files
from app.services.tools import http_exec as http_exec_module
from app.services.tools.loop import MAX_TOOL_ITERATIONS, tool_loop
from app.services.tools.specs import build_tool_specs


def _setup_agent(client: TestClient) -> str:
    customer = client.post(
        "/api/clients",
        json={"name": "Tools Co", "is_active": True},
    ).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"], "provider": "openrouter", "model": "gpt-5", "name": "Toolo",
            "instructions": "", "personality": "", "is_active": True,
        },
    ).json()
    return agent["id"]


HTTP_TOOL = {
    "type": "http",
    "name": "check_order",
    "description": "Look up an order",
    "url": "https://api.example.test/orders/{order_id}",
    "http_method": "GET",
    "prompt_instructions": "Use when the customer asks about an order.",
    "query_params": [{"name": "verbose", "type": "boolean", "description": "Include details", "required": False}],
    "headers": {"Authorization": "Bearer sk-hidden"},
}


def test_http_tool_crud_and_validation(authenticated_client: TestClient):
    client = authenticated_client
    agent_id = _setup_agent(client)

    created = client.post(f"/api/agents/{agent_id}/tools", json=HTTP_TOOL)
    assert created.status_code == 201, created.text
    tool = created.json()
    assert tool["has_headers"] is True
    assert "headers" not in tool and "encrypted_headers" not in tool

    # Duplicate name on the same agent.
    assert client.post(f"/api/agents/{agent_id}/tools", json=HTTP_TOOL).status_code == 409

    # Invalid names: not snake_case / consecutive underscores (reserved separator).
    for bad in ("Bad Name", "a__b", "_lead", "1num"):
        response = client.post(f"/api/agents/{agent_id}/tools", json={**HTTP_TOOL, "name": bad})
        assert response.status_code == 422, bad

    # Body params are rejected for GET tools.
    with_body = {**HTTP_TOOL, "name": "other", "body_params": [{"name": "qty", "type": "integer"}]}
    assert client.post(f"/api/agents/{agent_id}/tools", json=with_body).status_code == 422

    # PATCH without headers keeps the stored secret.
    updated = client.patch(f"/api/agents/{agent_id}/tools/{tool['id']}", json={"description": "Order lookup"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "Order lookup"
    assert updated.json()["has_headers"] is True

    listed = client.get(f"/api/agents/{agent_id}/tools").json()
    assert [item["name"] for item in listed] == ["check_order"]

    assert client.delete(f"/api/agents/{agent_id}/tools/{tool['id']}").status_code == 204
    assert client.get(f"/api/agents/{agent_id}/tools").json() == []


def test_mcp_test_connection_and_create(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    discovered = [{"name": "lookup", "description": "Find things", "input_schema": {"type": "object", "properties": {}}}]

    monkeypatch.setattr(agent_tools_router, "discover_mcp_tools", AsyncMock(return_value=discovered))
    tested = client.post(f"/api/agents/{agent_id}/tools/test-mcp", json={"url": "https://mcp.example.test/mcp"})
    assert tested.status_code == 200
    assert tested.json() == {"ok": True, "tools": [{"name": "lookup", "description": "Find things", "read_only": False, "destructive": False}]}

    created = client.post(
        f"/api/agents/{agent_id}/tools",
        json={"type": "mcp", "name": "orders", "url": "https://mcp.example.test/mcp", "transport": "streamable_http"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["cached_tools"] == discovered
    assert created.json()["tools_cached_at"] is not None

    # Unreachable server: no row is saved.
    monkeypatch.setattr(agent_tools_router, "discover_mcp_tools", AsyncMock(side_effect=ConnectionError("boom")))
    failed = client.post(
        f"/api/agents/{agent_id}/tools",
        json={"type": "mcp", "name": "broken", "url": "https://down.example.test/mcp"},
    )
    assert failed.status_code == 502
    assert [item["name"] for item in client.get(f"/api/agents/{agent_id}/tools").json()] == ["orders"]


def test_mcp_enabled_tools_selection(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    discovered = [
        {"name": "lookup", "description": "Find things", "input_schema": {"type": "object", "properties": {}}, "read_only": True, "destructive": False},
        {"name": "purge", "description": "Delete things", "input_schema": {"type": "object", "properties": {}}, "read_only": False, "destructive": True},
    ]
    monkeypatch.setattr(agent_tools_router, "discover_mcp_tools", AsyncMock(return_value=discovered))

    tested = client.post(f"/api/agents/{agent_id}/tools/test-mcp", json={"url": "https://mcp.example.test/mcp"})
    assert [(t["name"], t["read_only"], t["destructive"]) for t in tested.json()["tools"]] == [("lookup", True, False), ("purge", False, True)]

    # Unknown and duplicate names are dropped from the selection at save time.
    created = client.post(
        f"/api/agents/{agent_id}/tools",
        json={"type": "mcp", "name": "orders", "url": "https://mcp.example.test/mcp", "enabled_tools": ["purge", "ghost", "purge"]},
    )
    assert created.status_code == 201, created.text
    tool_id = created.json()["id"]
    assert created.json()["enabled_tools"] == ["purge"]

    # Omitting the field keeps the selection; null exposes every tool again.
    kept = client.patch(f"/api/agents/{agent_id}/tools/{tool_id}", json={"description": "Orders"})
    assert kept.json()["enabled_tools"] == ["purge"]
    cleared = client.patch(f"/api/agents/{agent_id}/tools/{tool_id}", json={"enabled_tools": None})
    assert cleared.json()["enabled_tools"] is None

    # A re-discovery that no longer lists a selected tool prunes it.
    client.patch(f"/api/agents/{agent_id}/tools/{tool_id}", json={"enabled_tools": ["lookup", "purge"]})
    monkeypatch.setattr(agent_tools_router, "discover_mcp_tools", AsyncMock(return_value=discovered[:1]))
    moved = client.patch(f"/api/agents/{agent_id}/tools/{tool_id}", json={"url": "https://mcp2.example.test/mcp"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["enabled_tools"] == ["lookup"]

    # HTTP tools never carry a selection.
    http_tool = client.post(
        f"/api/agents/{agent_id}/tools",
        json={"type": "http", "name": "ping", "url": "https://api.example.test/ping"},
    ).json()
    patched = client.patch(f"/api/agents/{agent_id}/tools/{http_tool['id']}", json={"enabled_tools": ["x"]})
    assert patched.status_code == 200 and patched.json()["enabled_tools"] is None


def test_specs_honour_enabled_tools():
    cached = [
        {"name": "lookup", "description": "Find", "input_schema": {"type": "object", "properties": {}}},
        {"name": "purge", "description": "Delete", "input_schema": {"type": "object", "properties": {}}},
    ]
    row = AgentTool(type="mcp", name="orders", url="https://mcp.example.test/mcp", cached_tools=cached, enabled_tools=None)
    assert [spec.name for spec in build_tool_specs([row])] == ["orders__lookup", "orders__purge"]
    row.enabled_tools = ["purge"]
    assert [spec.name for spec in build_tool_specs([row])] == ["orders__purge"]
    row.enabled_tools = []
    assert build_tool_specs([row]) == []


def test_tool_urls_are_trimmed():
    from app.schemas_tools import HttpToolIn, McpTestIn

    assert McpTestIn(url="  https://mcp.example.test/mcp ").url == "https://mcp.example.test/mcp"
    tool = HttpToolIn(type="http", name="check", url=" https://api.example.test/x ")
    assert tool.url == "https://api.example.test/x"


def test_describe_mcp_error_hints():
    from app.services.tools.mcp_client import describe_mcp_error

    def status_error(code: int) -> httpx.HTTPStatusError:
        return httpx.HTTPStatusError(
            f"HTTP {code}",
            request=httpx.Request("POST", "https://mcp.example.test/mcp"),
            response=httpx.Response(code),
        )

    assert "credentials (HTTP 401)" in describe_mcp_error(status_error(401))
    assert "HTTP 404" in describe_mcp_error(status_error(404))
    assert "HTTP 500" in describe_mcp_error(status_error(500))
    assert "could not be reached" in describe_mcp_error(httpx.ConnectError("refused"))
    assert "timed out" in describe_mcp_error(TimeoutError())
    assert "connection failed while talking" in describe_mcp_error(httpx.ReadError("broken pipe"))
    assert "connection failed while talking" in describe_mcp_error(httpx.RemoteProtocolError("bad chunk"))
    # Real causes arrive wrapped in nested anyio ExceptionGroups.
    grouped = BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [status_error(403)])])
    assert "credentials (HTTP 403)" in describe_mcp_error(grouped)
    assert "check the URL, transport and auth headers" in describe_mcp_error(RuntimeError("misc"))


def test_test_mcp_endpoint_surfaces_error_hint(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    unauthorized = httpx.HTTPStatusError(
        "HTTP 401",
        request=httpx.Request("POST", "https://mcp.example.test/mcp"),
        response=httpx.Response(401),
    )
    monkeypatch.setattr(agent_tools_router, "discover_mcp_tools", AsyncMock(side_effect=unauthorized))
    failed = client.post(f"/api/agents/{agent_id}/tools/test-mcp", json={"url": "https://mcp.example.test/mcp"})
    assert failed.status_code == 502
    assert "credentials (HTTP 401)" in failed.json()["detail"]


def _http_tool_row(**overrides) -> AgentTool:
    row = AgentTool(
        type="http",
        name="check_order",
        description="Look up an order",
        url="https://api.example.test/orders/{order_id}",
        http_method="GET",
        prompt_instructions="Use for order questions.",
        body_params=[],
        query_params=[],
        timeout_seconds=10,
        encrypted_headers=encrypt_secret(json.dumps({"Authorization": "Bearer sk-hidden"})),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class _ScriptedLLM:
    """Fake httpx.AsyncClient for the provider loop: pops one JSON response per POST."""

    def __init__(self, responses, captured):
        self.responses = responses
        self.captured = captured

    def __call__(self, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        self.captured.append({"url": url, "headers": headers, "payload": json})

        class Response:
            status_code = 200
            _data = self.responses.pop(0)

            def json(self):
                return self._data

        return Response()


class _FakeToolEndpoint:
    """Fake httpx.AsyncClient for the HTTP tool execution."""

    def __init__(self, captured, status_code=200, body='{"status": "shipped"}', content_type="application/json", content=None):
        self.captured = captured
        self.status_code = status_code
        self.body = body
        self.content_type = content_type
        self._content = content

    def __call__(self, **kwargs):
        self.captured["client_kwargs"] = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, method, url, **kwargs):
        self.captured.update({"method": method, "url": url, **kwargs})

        class Response:
            status_code = self.status_code
            text = self.body
            headers = {"content-type": self.content_type}
            content = self._content if self._content is not None else self.body.encode()

        return Response()


def _allow_all_urls(monkeypatch):
    monkeypatch.setattr(http_exec_module, "_blocked_reason", lambda _url: None)


def _patch_httpx(monkeypatch, module, client_factory):
    """Replace a module's `httpx` reference with a namespace exposing the fake
    client. Patching httpx.AsyncClient directly would leak across modules —
    they all share the real httpx module object."""
    fake = types.SimpleNamespace(HTTPError=httpx.HTTPError, ReadTimeout=httpx.ReadTimeout, AsyncClient=client_factory)
    monkeypatch.setattr(module, "httpx", fake)


def _tool_call_reply(call_id: str, name: str, arguments: str, usage: dict | None = None) -> dict:
    """A chat completion whose assistant turn asks for one tool."""
    return {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}},
            ]},
        }],
        "usage": usage or {},
    }


def _text_reply(text: str, usage: dict | None = None) -> dict:
    # A generated answer always reports usage; one without it is treated as
    # synthetic by the transport and asked again.
    return {
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
        "usage": usage or {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_tool_loop_round_trip(monkeypatch):
    specs = build_tool_specs([_http_tool_row()])
    llm_calls: list[dict] = []
    tool_call: dict = {}
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
        _tool_call_reply("call_1", "check_order", '{"order_id": "42"}', {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001}),
        _text_reply("Your order shipped.", {"prompt_tokens": 20, "completion_tokens": 7, "cost": 0.002}),
    ], llm_calls))
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint(tool_call))
    _allow_all_urls(monkeypatch)

    completion = asyncio.run(tool_loop(
        "https://openrouter.test/api/v1", "key", "openai/gpt-5.6-luna",
        [{"role": "system", "content": "Be helpful"}, {"role": "user", "content": "Where is order 42?"}],
        specs, None, None,
    ))

    first = llm_calls[0]["payload"]
    assert llm_calls[0]["url"].endswith("/chat/completions")
    # Every turn asks OpenRouter to price the call, so the reply carries the real cost.
    assert first["usage"] == {"include": True}
    assert first["messages"][0] == {"role": "system", "content": "Be helpful"}
    tool = first["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "check_order"
    assert "When to use:" in tool["function"]["description"]
    assert tool["function"]["parameters"]["required"] == ["order_id"]
    # Stated explicitly: an omitted strict is read as strict mode by some routes.
    assert tool["function"]["strict"] is False

    # The tool endpoint got the substituted path and decrypted auth header.
    assert tool_call["url"] == "https://api.example.test/orders/42"
    assert tool_call["method"] == "GET"
    assert tool_call["headers"]["Authorization"] == "Bearer sk-hidden"

    # The assistant turn that asked for the tool is echoed back, then the tool message.
    second = llm_calls[1]["payload"]["messages"]
    assert second[-2]["role"] == "assistant"
    assert second[-2]["tool_calls"][0]["id"] == "call_1"
    assert second[-1] == {"role": "tool", "tool_call_id": "call_1", "content": 'HTTP 200: {"status": "shipped"}'}

    assert completion.text == "Your order shipped."
    assert completion.input_tokens == 30 and completion.output_tokens == 12
    assert completion.cost_usd == 0.003
    assert completion.tool_calls == [{
        "name": "check_order",
        "arguments": {"order_id": "42"},
        "result_preview": 'HTTP 200: {"status": "shipped"}',
        "is_error": False,
    }]


def test_loop_caps_iterations(monkeypatch):
    specs = build_tool_specs([_http_tool_row()])
    tool_use = _tool_call_reply("t", "check_order", '{"order_id": "1"}')
    final = _text_reply("Done.")
    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([tool_use] * MAX_TOOL_ITERATIONS + [final], llm_calls))
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}))
    _allow_all_urls(monkeypatch)

    completion = asyncio.run(tool_loop(
        "https://openrouter.test/api/v1", "key", "anthropic/claude-sonnet-5",
        [{"role": "user", "content": "hi"}], specs, None, None,
    ))
    assert completion.text == "Done."
    assert len(llm_calls) == MAX_TOOL_ITERATIONS + 1
    assert llm_calls[-1]["payload"]["tool_choice"] == "none"
    assert all("tool_choice" not in call["payload"] for call in llm_calls[:-1])


def test_http_exec_edge_cases(monkeypatch):
    _allow_all_urls(monkeypatch)

    # Missing path parameter.
    result, is_error, _files = asyncio.run(http_exec_module.execute_http_tool(_http_tool_row(), {}))
    assert is_error and "order_id" in result

    # Non-2xx marks the result as an error but still returns the body.
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}, status_code=404, body="not found", content_type="text/plain"))
    result, is_error, _files = asyncio.run(http_exec_module.execute_http_tool(_http_tool_row(), {"order_id": "9"}))
    assert is_error and result == "HTTP 404: not found"

    # Oversized bodies are truncated.
    huge = "x" * (http_exec_module.MAX_RESPONSE_CHARS + 50)
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}, body=huge, content_type="text/plain"))
    result, _is_error, _files = asyncio.run(http_exec_module.execute_http_tool(_http_tool_row(), {"order_id": "9"}))
    assert result.endswith("... [truncated]")
    assert len(result) < len(huge)

    # Transport failures never raise.
    class ExplodingClient:
        def __call__(self, **_kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            raise http_exec_module.httpx.ReadTimeout("slow")

    _patch_httpx(monkeypatch, http_exec_module, ExplodingClient())
    result, is_error, _files = asyncio.run(http_exec_module.execute_http_tool(_http_tool_row(), {"order_id": "9"}))
    assert is_error and "ReadTimeout" in result


def test_ssrf_guard(monkeypatch):
    row = _http_tool_row(url="https://internal.example.test/{order_id}")

    def fake_getaddrinfo(_host, _port):
        return [(2, 1, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(http_exec_module.socket, "getaddrinfo", fake_getaddrinfo)
    result, is_error, _files = asyncio.run(http_exec_module.execute_http_tool(row, {"order_id": "1"}))
    assert is_error and "private or reserved" in result

    # Self-hosted opt-out lets the request through.
    settings = http_exec_module.get_settings().model_copy(update={"tools_allow_private_urls": True})
    monkeypatch.setattr(http_exec_module, "get_settings", lambda: settings)
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}))
    result, is_error, _files = asyncio.run(http_exec_module.execute_http_tool(row, {"order_id": "1"}))
    assert not is_error


def test_extract_tool_files_strips_bytes():
    pdf = b"%PDF-1.4" + b"0" * 5000
    encoded = base64.b64encode(pdf).decode()

    # A base64 file field in a JSON body: bytes come out, everything else stays.
    body = json.dumps({"status": "ok", "filename": "recibo.pdf", "mime": "application/pdf",
                       "file": encoded, "share_url": "https://x/y"})
    text, files = extract_tool_files(200, "application/json", body.encode(), body)
    assert len(files) == 1
    assert files[0].data == pdf and files[0].filename == "recibo.pdf" and files[0].mime == "application/pdf"
    assert encoded not in text and "share_url" in text

    # A name without an extension gets the one the mime implies: the chat UI
    # and WhatsApp classify the document by it.
    body = json.dumps({"name": "cotizacion_autos", "mime": "application/pdf", "file": encoded})
    _text, files = extract_tool_files(200, "application/json", body.encode(), body)
    assert files[0].filename == "cotizacion_autos.pdf"
    # A name that already has one is kept as is.
    body = json.dumps({"filename": "recibo.PDF", "mime": "application/pdf", "file": encoded})
    _text, files = extract_tool_files(200, "application/json", body.encode(), body)
    assert files[0].filename == "recibo.PDF"

    # A binary body is the file wholesale, named by its type.
    text, files = extract_tool_files(200, "application/pdf", pdf, "garbled")
    assert len(files) == 1 and files[0].data == pdf and files[0].filename == "file.pdf"
    assert "%PDF" not in text

    # A data URL anywhere in the JSON is picked up.
    data_url = "data:image/png;base64," + base64.b64encode(b"\x89PNG" + b"1" * 4000).decode()
    body = json.dumps({"result": {"img": data_url}})
    text, files = extract_tool_files(200, "application/json", body.encode(), body)
    assert len(files) == 1 and files[0].mime == "image/png" and "base64" not in text


def test_extract_tool_files_leaves_plain_responses():
    # Plain JSON without a file is untouched.
    body = json.dumps({"status": "shipped"})
    assert extract_tool_files(200, "application/json", body.encode(), body) == (body, [])
    # Plain text is untouched.
    assert extract_tool_files(200, "text/plain", b"hello", "hello") == ("hello", [])
    # A short base64-looking id is not a file.
    body = json.dumps({"data": "YWJjZGVm"})
    assert extract_tool_files(200, "application/json", body.encode(), body) == (body, [])


def test_tool_loop_keeps_file_bytes_out_of_context(monkeypatch):
    specs = build_tool_specs([_http_tool_row()])
    pdf = b"%PDF-1.4" + b"0" * 5000
    encoded = base64.b64encode(pdf).decode()
    tool_body = json.dumps({"filename": "recibo.pdf", "mime": "application/pdf", "file": encoded})
    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
        _tool_call_reply("call_1", "check_order", '{"order_id": "42"}'),
        _text_reply("Here is your receipt."),
    ], llm_calls))
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}, body=tool_body))
    _allow_all_urls(monkeypatch)

    completion = asyncio.run(tool_loop(
        "https://openrouter.test/api/v1", "key", "openai/gpt-5.6-luna",
        [{"role": "user", "content": "Send me my receipt"}], specs, None, None,
    ))

    # The tool message the model saw never carried the base64 payload.
    tool_message = llm_calls[1]["payload"]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert encoded not in tool_message["content"]
    assert "recibo.pdf" in tool_message["content"]
    # The file rode out on the completion for the channel layer to deliver.
    assert len(completion.attachments) == 1
    assert completion.attachments[0].data == pdf
    assert completion.text == "Here is your receipt."


def test_conversation_uses_tools_end_to_end(authenticated_client: TestClient, monkeypatch):
    """Full flow: agent with an HTTP tool answers through the tool loop and
    the assistant message persists the tool metadata."""
    client = authenticated_client
    agent_id = _setup_agent(client)
    created = client.post(f"/api/agents/{agent_id}/tools", json=HTTP_TOOL)
    assert created.status_code == 201

    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
        _tool_call_reply("c1", "check_order", '{"order_id": "42"}', {"prompt_tokens": 3, "completion_tokens": 2}),
        _text_reply("It shipped.", {"prompt_tokens": 4, "completion_tokens": 3}),
    ], llm_calls))
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}))
    _allow_all_urls(monkeypatch)

    conversation = client.post("/api/conversations", json={"agent_id": agent_id}).json()
    sent = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Where is order 42?"})
    assert sent.status_code == 200, sent.text
    assistant = sent.json()["messages"][-1]
    assert assistant["content"] == "It shipped."
    assert assistant["tool_calls"][0]["name"] == "check_order"
    assert assistant["tool_calls"][0]["is_error"] is False
    assert len(llm_calls) == 2
    # With tools active, the system prompt carries the no-fallback rule.
    assert "do not answer from memory" in llm_calls[0]["payload"]["messages"][0]["content"]


def test_failed_tool_result_is_marked(monkeypatch):
    """A failing tool feeds an explicit failure marker back to the model."""
    specs = build_tool_specs([_http_tool_row()])
    llm_calls: list[dict] = []
    _patch_httpx(monkeypatch, ai_module, _ScriptedLLM([
        _tool_call_reply("call_1", "check_order", '{"order_id": "42"}'),
        _text_reply("That is unavailable right now."),
    ], llm_calls))
    _patch_httpx(monkeypatch, http_exec_module, _FakeToolEndpoint({}, status_code=301, body=""))
    _allow_all_urls(monkeypatch)

    completion = asyncio.run(tool_loop(
        "https://openrouter.test/api/v1", "key", "anthropic/claude-sonnet-5",
        [{"role": "user", "content": "Where is order 42?"}], specs, None, None,
    ))
    result_message = llm_calls[1]["payload"]["messages"][-1]
    assert result_message["role"] == "tool"
    assert result_message["content"].startswith("Tool call failed: HTTP 301")
    assert completion.tool_calls[0]["is_error"] is True
    assert completion.tool_calls[0]["result_preview"].startswith("Tool call failed:")
