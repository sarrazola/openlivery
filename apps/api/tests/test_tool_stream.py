import asyncio
import json

import httpx

from app.services.tools.specs import ToolSpec
from app.services.tools.stream import stream_tool_loop


def _sse(*chunks: dict) -> bytes:
    lines = [": PROCESSING"] + [f"data: {json.dumps(chunk)}" for chunk in chunks] + ["data: [DONE]"]
    return ("\n\n".join(lines) + "\n\n").encode()


def _delta(**delta) -> dict:
    return {"id": "gen-1", "provider": "Google", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}


def test_the_reply_streams_as_written_and_tool_calls_run_between_rounds(monkeypatch):
    rounds = [
        _sse(
            _delta(content="Claro"), _delta(content=", Juan."),
            _delta(tool_calls=[{"index": 0, "id": "call_1", "type": "function", "function": {"name": "save_contact", "arguments": '{"na'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": 'me": "Juan"}'}}]),
            {"id": "gen-1", "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001}},
        ),
        _sse(
            _delta(content="Quedó"), _delta(content=" guardado."),
            {"id": "gen-2", "choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 5, "cost": 0.002}},
        ),
    ]
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, content=rounds[len(sent) - 1], headers={"content-type": "text/event-stream"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    saved: list[dict] = []
    spec = ToolSpec("save_contact", "Save the caller's name.", {"type": "object"}, handler=lambda args: (saved.append(args) or "Saved.", False))
    done: list = []

    async def collect() -> list[str]:
        return [piece async for piece in stream_tool_loop("https://openrouter.ai/api/v1", "key", "google/gemini-3.5-flash-lite",
                                                          [{"role": "user", "content": "Soy Juan"}], [spec], 0.7, 400, done)]

    pieces = asyncio.run(collect())
    # Words go out as they arrive; the second round is spaced from the first.
    assert pieces == ["Claro", ", Juan.", " ", "Quedó", " guardado."]
    assert saved == [{"name": "Juan"}]
    assert sent[0]["stream"] is True and sent[0]["tools"][0]["function"]["name"] == "save_contact"
    # The second round carries the call and its result back to the model.
    assert sent[1]["messages"][-2]["tool_calls"][0]["function"]["arguments"] == '{"name": "Juan"}'
    assert sent[1]["messages"][-1] == {"role": "tool", "tool_call_id": "call_1", "content": "Saved."}

    completion = done[0]
    assert completion.text == "Claro, Juan. Quedó guardado."
    assert (completion.input_tokens, completion.output_tokens) == (220, 15)
    assert round(completion.cost_usd, 3) == 0.003
    assert completion.tool_calls[0]["name"] == "save_contact" and completion.served_by == "Google"
