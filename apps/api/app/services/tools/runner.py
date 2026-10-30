"""Single entry point for generating an agent reply, with or without tools.

Drop-in replacement for chat_completion at the chat call sites: same error
semantics (HTTPException 502 on provider failure), same Completion result —
plus tool_calls metadata when tools ran.
"""

import time
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Agent, AgentTool
from ..ai import Completion, chat_completion
from .loop import tool_loop
from .specs import build_tool_specs
from .stream import stream_tool_loop

# Injected whenever the agent has tools: a failing tool must never be papered
# over with the model's own knowledge.
TOOL_FAILURE_RULE = (
    "Tool usage rules: when the user's request depends on a tool and the tool call fails or returns an error, "
    "do not answer from memory and do not invent data. Tell the user that the information or action is not "
    "available right now and that they can try again later."
)


def _with_tool_rules(messages: list[dict]) -> list[dict]:
    amended = list(messages)
    for index, message in enumerate(amended):
        if message["role"] == "system":
            amended[index] = {**message, "content": f"{message['content']}\n\n{TOOL_FAILURE_RULE}"}
            return amended
    return [{"role": "system", "content": TOOL_FAILURE_RULE}, *amended]


async def run_completion(
    db: Session,
    agent: Agent,
    base_url: str,
    api_key: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_specs: list | None = None,
    model: str | None = None,
) -> Completion:
    """``model`` overrides the agent's for this completion (a phone line thinks
    with a lighter one than the chat)."""
    model = (model or agent.model).strip()
    rows = db.scalars(select(AgentTool).where(AgentTool.agent_id == agent.id, AgentTool.enabled.is_(True))).all()
    specs = build_tool_specs(list(rows)) + list(extra_specs or [])
    started = time.perf_counter()
    if not specs:
        completion = await chat_completion(agent.provider, base_url, api_key, model, messages, temperature=temperature, max_tokens=max_tokens)
    else:
        messages = _with_tool_rules(messages)
        try:
            completion = await tool_loop(base_url, api_key, model, messages, specs, temperature, max_tokens)
        except HTTPException:
            raise
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not get a valid response from the AI provider. Check the API key and the model.",
            ) from exc
    completion.duration_ms = int((time.perf_counter() - started) * 1000)
    return completion


async def stream_completion(
    db: Session,
    agent: Agent,
    base_url: str,
    api_key: str,
    messages: list[dict],
    done: list[Completion],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_specs: list | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """``run_completion`` for a caller that speaks as it goes: yields the
    reply's text as the model writes it, then appends the ``Completion`` to
    ``done``. Provider failures raise as they do there."""
    model = (model or agent.model).strip()
    rows = db.scalars(select(AgentTool).where(AgentTool.agent_id == agent.id, AgentTool.enabled.is_(True))).all()
    specs = build_tool_specs(list(rows)) + list(extra_specs or [])
    if specs:
        messages = _with_tool_rules(messages)
    started = time.perf_counter()
    try:
        async for piece in stream_tool_loop(base_url, api_key, model, messages, specs, temperature, max_tokens, done):
            yield piece
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not get a valid response from the AI provider. Check the API key and the model.",
        ) from exc
    if done:
        done[-1].duration_ms = int((time.perf_counter() - started) * 1000)
