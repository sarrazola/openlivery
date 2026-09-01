"""Provider tool-calling loops over raw HTTP payloads.

Mirrors the request building in services/ai.py (OpenAI Responses API and
Anthropic Messages API) but keeps requesting until the model stops asking for
tools. Mid-loop responses may contain no text, so this module never routes
them through the plain-completion text extractors until the loop ends.
"""

import json

from ..ai import ANTHROPIC_VERSION, Completion, _post_json, extract_openai_text
from .http_exec import execute_http_tool
from .mcp_client import call_mcp_tool
from .specs import ToolSpec, find_spec

MAX_TOOL_ITERATIONS = 5
RESULT_PREVIEW_CHARS = 500


async def _execute(spec: ToolSpec, args: dict) -> tuple[str, bool]:
    if spec.handler is not None:
        return spec.handler(args)
    if spec.mcp_tool_name is not None:
        result, is_error = await call_mcp_tool(spec.tool, spec.mcp_tool_name, args)
    else:
        result, is_error = await execute_http_tool(spec.tool, args)
    if is_error:
        # Unambiguous failure marker for both providers (the OpenAI item shape
        # has no error flag) so the no-fallback rule in the system prompt kicks in.
        result = f"Tool call failed: {result}"
    return result, is_error


def _record(metadata: list[dict], name: str, args: dict, result: str, is_error: bool) -> None:
    preview = result[:RESULT_PREVIEW_CHARS] + ("…" if len(result) > RESULT_PREVIEW_CHARS else "")
    metadata.append({"name": name, "arguments": args, "result_preview": preview, "is_error": is_error})


async def anthropic_tool_loop(
    base_url: str, api_key: str, model: str, messages: list[dict], specs: list[ToolSpec],
    temperature: float | None, max_tokens: int | None,
) -> Completion:
    url = f"{base_url.rstrip('/')}/messages"
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    convo: list[dict] = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    tools = [{"name": s.name, "description": s.description, "input_schema": s.input_schema} for s in specs]
    sampling: dict = {} if temperature is None else {"temperature": temperature}
    input_tokens = output_tokens = 0
    metadata: list[dict] = []

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        payload: dict = {"model": model, "messages": convo, "max_tokens": max_tokens or 2048, "tools": tools}
        if system:
            payload["system"] = system
        if iteration == MAX_TOOL_ITERATIONS:
            # Cap reached: tools stay in the payload (required when the history
            # contains tool_use blocks) but the model must answer with text.
            payload["tool_choice"] = {"type": "none"}
        data = await _post_json(url, headers, payload, sampling)
        usage = data.get("usage") or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        content = data.get("content", [])
        tool_uses = [block for block in content if block.get("type") == "tool_use"]
        if data.get("stop_reason") != "tool_use" or not tool_uses:
            text = "".join(block.get("text", "") for block in content if block.get("type") == "text").strip()
            if not text:
                raise ValueError("empty response")
            return Completion(text, input_tokens, output_tokens, tool_calls=metadata or None)
        convo.append({"role": "assistant", "content": content})
        results = []
        for block in tool_uses:
            spec = find_spec(specs, block.get("name", ""))
            args = block.get("input") or {}
            if spec is None:
                result, is_error = f"Error: unknown tool '{block.get('name')}'", True
            else:
                result, is_error = await _execute(spec, args)
            _record(metadata, block.get("name", ""), args, result, is_error)
            results.append({"type": "tool_result", "tool_use_id": block.get("id"), "content": result, "is_error": is_error})
        convo.append({"role": "user", "content": results})
    raise ValueError("tool loop did not converge")


async def openai_tool_loop(
    base_url: str, api_key: str, model: str, messages: list[dict], specs: list[ToolSpec],
    temperature: float | None, max_tokens: int | None,
) -> Completion:
    url = f"{base_url.rstrip('/')}/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    instructions = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    input_items: list[dict] = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    # The Responses API uses a flat function-tool shape (unlike chat completions).
    tools = [{"type": "function", "name": s.name, "description": s.description, "parameters": s.input_schema} for s in specs]
    sampling: dict = {}
    if temperature is not None:
        sampling["temperature"] = temperature
    if max_tokens is not None:
        sampling["max_output_tokens"] = max_tokens
    input_tokens = output_tokens = 0
    metadata: list[dict] = []

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        payload: dict = {"model": model, "input": input_items, "tools": tools}
        if instructions:
            payload["instructions"] = instructions
        if iteration == MAX_TOOL_ITERATIONS:
            payload["tool_choice"] = "none"
        data = await _post_json(url, headers, payload, sampling)
        usage = data.get("usage") or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        output = data.get("output", [])
        calls = [item for item in output if item.get("type") == "function_call"]
        if not calls:
            return Completion(extract_openai_text(data), input_tokens, output_tokens, tool_calls=metadata or None)
        # The API requires the function_call items echoed back in the input.
        input_items.extend(output)
        for call in calls:
            try:
                args = json.loads(call.get("arguments") or "{}")
            except ValueError:
                args = {}
            spec = find_spec(specs, call.get("name", ""))
            if spec is None:
                result, is_error = f"Error: unknown tool '{call.get('name')}'", True
            else:
                result, is_error = await _execute(spec, args)
            _record(metadata, call.get("name", ""), args, result, is_error)
            input_items.append({"type": "function_call_output", "call_id": call.get("call_id"), "output": result})
    raise ValueError("tool loop did not converge")
