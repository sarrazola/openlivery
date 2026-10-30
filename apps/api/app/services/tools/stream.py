"""The tool loop, streamed: the reply's text is handed on as the model writes it.

Same rounds as ``loop.tool_loop``, for a caller that cannot wait for a whole
reply before using it: on a phone call the voice starts on the first words.
Each round's text goes out as it arrives; tool calls are gathered from the
stream, run like in the plain loop, and the next round streams on.
"""

import json
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException

from ..ai import Completion, Usage, _is_sampling_param_error, _safe_provider_error, auth_headers, chat_url, read_usage, sampling_params
from .loop import MAX_TOOL_ITERATIONS, _execute, _record
from .specs import ToolSpec, find_spec

TIMEOUT = httpx.Timeout(60, connect=10)


async def _chunks(client: httpx.AsyncClient, url: str, headers: dict, payload: dict, sampling: dict) -> AsyncIterator[dict]:
    """The decoded chunks of one streamed completion. A sampling parameter the
    model refuses is dropped and the request made again, as in ``_post_json``."""
    for attempt in (sampling, {}):
        async with client.stream("POST", url, headers=headers, json={**payload, **attempt}) as response:
            if response.status_code >= 400:
                await response.aread()
                if attempt and _is_sampling_param_error(response):
                    continue
                raise HTTPException(status_code=502, detail=f"The AI provider responded with an error: {_safe_provider_error(response)}")
            async for line in response.aiter_lines():
                # Anything but a data line is a keep-alive comment.
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise HTTPException(status_code=502, detail="The AI provider stopped the reply with an error.")
                yield chunk
            return


async def stream_tool_loop(
    base_url: str, api_key: str, model: str, messages: list[dict], specs: list[ToolSpec],
    temperature: float | None, max_tokens: int | None, done: list[Completion],
) -> AsyncIterator[str]:
    """Yield the reply's text as it comes; once the model is finished, the
    whole ``Completion`` (all rounds' text, usage and the tools that ran) is
    appended to ``done``."""
    url = chat_url(base_url)
    headers = auth_headers(api_key)
    convo: list[dict] = [{"role": m["role"], "content": m["content"]} for m in messages]
    tools = [
        {"type": "function", "function": {"name": s.name, "description": s.description, "parameters": s.input_schema, "strict": False}}
        for s in specs
    ]
    sampling = sampling_params(temperature, max_tokens)
    usage = Usage()
    metadata: list[dict] = []
    said: list[str] = []
    served_by = generation_id = ""

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for iteration in range(MAX_TOOL_ITERATIONS + 1):
            payload: dict = {
                "model": model, "messages": convo, "stream": True,
                "stream_options": {"include_usage": True}, "usage": {"include": True},
            }
            if tools:
                payload["tools"] = tools
                if iteration == MAX_TOOL_ITERATIONS:
                    payload["tool_choice"] = "none"
            text: list[str] = []
            calls: dict[int, dict] = {}
            round_usage = Usage()
            async for chunk in _chunks(client, url, headers, payload, sampling):
                served_by = str(chunk.get("provider") or served_by)
                generation_id = str(chunk.get("id") or generation_id)
                # The round's usage rides on its last chunk.
                if chunk.get("usage"):
                    round_usage = read_usage(chunk)
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        # A round after a tool call picks up where the last
                        # one's words ended: keep a space between them.
                        if not text and any(said) and not piece[:1].isspace():
                            yield " "
                        text.append(piece)
                        yield piece
                    # A call arrives in pieces keyed by its index: the id and
                    # name first, the arguments spread over several chunks.
                    for part in delta.get("tool_calls") or []:
                        call = calls.setdefault(part.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] = part.get("id") or call["id"]
                        function = part.get("function") or {}
                        call["function"]["name"] += function.get("name") or ""
                        call["function"]["arguments"] += function.get("arguments") or ""
            usage = usage + round_usage
            said.append("".join(text))
            if not calls:
                break
            ordered = [calls[index] for index in sorted(calls)]
            convo.append({"role": "assistant", "content": "".join(text), "tool_calls": ordered})
            for call in ordered:
                function = call["function"]
                try:
                    args = json.loads(function["arguments"] or "{}")
                except ValueError:
                    args = {}
                spec = find_spec(specs, function["name"])
                if spec is None:
                    result, is_error = f"Error: unknown tool '{function['name']}'", True
                else:
                    result, is_error, _ = await _execute(spec, args)
                _record(metadata, function["name"], args, result, is_error)
                convo.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    done.append(Completion(
        " ".join(part.strip() for part in said if part.strip()),
        usage.input_tokens,
        usage.output_tokens,
        tool_calls=metadata or None,
        cost_usd=usage.cost_usd,
        cached_tokens=usage.cached_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        served_by=served_by,
        generation_id=generation_id,
    ))
