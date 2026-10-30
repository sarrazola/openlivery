"""CRUD for agent custom tools (HTTP endpoints and MCP servers).

MCP servers are validated by connecting and listing their tools before any
row is saved; the discovered list is cached on the row for chat-time use.
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import AgentTool, User, now_utc
from ..schemas_tools import AgentToolIn, AgentToolOut, HttpToolUpdate, McpTestIn, McpTestOut
from ..security import decrypt_secret, encrypt_secret
from ..services import phone_calls
from ..services.tools.mcp_client import _flatten_exceptions, describe_mcp_error, discover_mcp_tools
from .agents import _agent


router = APIRouter(prefix="/agents/{agent_id}/tools", tags=["Agent tools"])
logger = logging.getLogger("openlivery.agent_tools")


def _tool(db: Session, user: User, agent_id: uuid.UUID, tool_id: uuid.UUID) -> AgentTool:
    _agent(db, user, agent_id)
    tool = db.scalar(select(AgentTool).where(AgentTool.id == tool_id, AgentTool.agent_id == agent_id))
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


def _check_name_free(db: Session, agent_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(AgentTool.id).where(AgentTool.agent_id == agent_id, AgentTool.name == name)
    if exclude_id:
        query = query.where(AgentTool.id != exclude_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="A tool with this name already exists on this agent")


def _out(tool: AgentTool) -> AgentToolOut:
    data = AgentToolOut.model_validate(tool)
    data.has_headers = bool(tool.encrypted_headers)
    return data


def _prune_selection(selection: list[str] | None, cached: list[dict]) -> list[str] | None:
    """Keep only selected names the server actually exposes. None means all."""
    if selection is None:
        return None
    known = {entry.get("name") for entry in cached}
    seen: set[str] = set()
    kept = []
    for name in selection:
        if name in known and name not in seen:
            kept.append(name)
            seen.add(name)
    return kept


async def _discover_or_502(url: str, transport: str, headers: dict[str, str] | None) -> list[dict]:
    try:
        return await discover_mcp_tools(url, transport, headers)
    except Exception as exc:
        # Exception reprs carry no header values, so this is safe to log.
        causes = "; ".join(f"{type(c).__name__}: {c}" for c in _flatten_exceptions(exc))
        logger.warning("MCP discovery failed url=%s transport=%s causes=[%s]", url, transport, causes[:500])
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to the MCP server: {describe_mcp_error(exc)}.",
        ) from exc


@router.get("", response_model=list[AgentToolOut])
def list_tools(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _agent(db, user, agent_id)
    rows = db.scalars(select(AgentTool).where(AgentTool.agent_id == agent_id).order_by(AgentTool.created_at)).all()
    return [_out(row) for row in rows]


@router.post("", response_model=AgentToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(
    agent_id: uuid.UUID, payload: AgentToolIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _agent(db, user, agent_id)
    _check_name_free(db, agent_id, payload.name)
    headers = payload.headers
    tool = AgentTool(agent_id=agent_id, **payload.model_dump(exclude={"headers", "enabled_tools"}))
    if headers:
        tool.encrypted_headers = encrypt_secret(json.dumps(headers))
    if payload.type == "mcp":
        tool.cached_tools = await _discover_or_502(payload.url, payload.transport, headers)
        tool.tools_cached_at = now_utc()
        tool.enabled_tools = _prune_selection(payload.enabled_tools, tool.cached_tools)
    db.add(tool)
    db.commit()
    db.refresh(tool)
    phone_calls.refresh_lines_soon(db, agent_id=agent_id)
    return _out(tool)


@router.patch("/{tool_id}", response_model=AgentToolOut)
async def update_tool(
    agent_id: uuid.UUID,
    tool_id: uuid.UUID,
    payload: HttpToolUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool = _tool(db, user, agent_id, tool_id)
    updates = payload.model_dump(exclude_unset=True)
    headers = updates.pop("headers", None)
    # The ellipsis sentinel tells "omitted" from "null"; HTTP rows ignore it.
    selection = updates.pop("enabled_tools", ...)
    if tool.type != "mcp":
        selection = ...
    if "name" in updates:
        _check_name_free(db, agent_id, updates["name"], exclude_id=tool.id)
    if "body_params" in updates and updates["body_params"] and updates.get("http_method", tool.http_method) in ("GET", "DELETE"):
        raise HTTPException(status_code=422, detail="Body parameters are not allowed for GET or DELETE tools")
    for key, value in updates.items():
        setattr(tool, key, value)
    if headers is not None:
        tool.encrypted_headers = encrypt_secret(json.dumps(headers)) if headers else None
    if tool.type == "mcp" and ({"url", "transport"} & updates.keys() or headers is not None):
        tool.cached_tools = await _discover_or_502(tool.url, tool.transport, _stored_headers(tool))
        tool.tools_cached_at = now_utc()
    if tool.type == "mcp":
        # A re-discovery can drop tools the selection still names; prune either way.
        tool.enabled_tools = _prune_selection(tool.enabled_tools if selection is ... else selection, tool.cached_tools)
    db.commit()
    db.refresh(tool)
    phone_calls.refresh_lines_soon(db, agent_id=agent_id)
    return _out(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(agent_id: uuid.UUID, tool_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tool = _tool(db, user, agent_id, tool_id)
    db.delete(tool)
    db.commit()
    phone_calls.refresh_lines_soon(db, agent_id=agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/test-mcp", response_model=McpTestOut)
async def test_mcp(
    agent_id: uuid.UUID, payload: McpTestIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _agent(db, user, agent_id)
    url, transport, headers = payload.url, payload.transport, payload.headers
    if payload.tool_id:
        tool = _tool(db, user, agent_id, payload.tool_id)
        url = url or tool.url
        transport = payload.transport if payload.url else tool.transport
        if headers is None:
            headers = _stored_headers(tool)
    if not url:
        raise HTTPException(status_code=422, detail="A server URL is required")
    tools = await _discover_or_502(url, transport, headers)
    return McpTestOut(
        ok=True,
        tools=[
            {
                "name": t["name"],
                "description": t["description"],
                "read_only": bool(t.get("read_only")),
                "destructive": bool(t.get("destructive")),
            }
            for t in tools
        ],
    )


def _stored_headers(tool: AgentTool) -> dict[str, str] | None:
    if not tool.encrypted_headers:
        return None
    return json.loads(decrypt_secret(tool.encrypted_headers))
