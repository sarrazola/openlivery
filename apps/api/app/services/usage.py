import asyncio
import logging
import uuid
from collections.abc import Callable

import httpx
from sqlalchemy.orm import Session

from ..database import new_session
from ..models import Conversation, Message, UsageRecord, new_uuid
from .ai import Completion, auth_headers

logger = logging.getLogger(__name__)

# A deployment may want to know about each usage record as it is written (to
# attribute it, meter it, or note which key answered) without replacing this
# module. Hooks run inside the caller's session before the commit and must not
# fail the reply: an error is logged and the record stands.
UsageHook = Callable[..., None]
_usage_hooks: list[UsageHook] = []


def register_usage_hook(hook: UsageHook) -> None:
    """``hook(db, record, completion, conversation=..., message=...)`` after every record."""
    if hook not in _usage_hooks:
        _usage_hooks.append(hook)

# The router indexes a call's record some ten seconds after answering. These
# are the waits between reads of it, about two minutes in all.
RECONCILE_DELAYS = (8.0, 8.0, 15.0, 30.0, 60.0)


def record_usage(
    db: Session,
    agency_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    provider: str,
    model: str,
    completion: Completion,
    *,
    conversation: Conversation | None = None,
    message: Message | None = None,
) -> UsageRecord | None:
    """Store what a completion used and cost, linked to the reply it produced.

    ``conversation`` and ``message`` are the reply's context when the caller
    has them: a pending ``Message`` gets its id here so the link holds once
    the session flushes. The caller owns the commit. Returns the pending
    record (with its id), or None when there was nothing to record.
    """
    if completion.input_tokens <= 0 and completion.output_tokens <= 0:
        return None
    if message is not None and message.id is None:
        message.id = new_uuid()
    record = UsageRecord(
        id=new_uuid(),
        agency_id=agency_id,
        agent_id=agent_id,
        provider=provider,
        model=model,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        cost_usd=completion.cost_usd,
        cached_tokens=completion.cached_tokens,
        reasoning_tokens=completion.reasoning_tokens,
        served_by=(completion.served_by or "")[:60],
        duration_ms=completion.duration_ms,
        conversation_id=conversation.id if conversation is not None else None,
        message_id=message.id if message is not None else None,
    )
    db.add(record)
    for hook in _usage_hooks:
        try:
            hook(db, record, completion, conversation=conversation, message=message)
        except Exception:  # noqa: BLE001 - a hook must never fail the reply
            logger.exception("Usage hook %s failed", getattr(hook, "__name__", hook))
    return record


_reconciling: set["asyncio.Task[None]"] = set()


def schedule_generation_reconcile(record: UsageRecord | None, completion: Completion, base_url: str, api_key: str) -> None:
    """When the response left the cost out but named the call, fill the
    record in from the router's record once it exists. Runs in the
    background of the current event loop; a no-op when there is nothing to
    reconcile or no loop (a synchronous caller)."""
    if record is None or completion.cost_usd is not None or not completion.generation_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(reconcile_generation(record.id, base_url, api_key, completion.generation_id))
    _reconciling.add(task)
    task.add_done_callback(_reconciling.discard)


async def fetch_generation(base_url: str, api_key: str, generation_id: str) -> dict | None:
    """The router's record of one call (``total_cost``,
    ``upstream_inference_cost``, ``provider_name``), or None if it is not
    there yet."""
    url = f"{base_url.rstrip('/')}/generation"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=auth_headers(api_key), params={"id": generation_id})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return (response.json() or {}).get("data") or None
    except ValueError:
        return None


async def reconcile_generation(record_id: uuid.UUID, base_url: str, api_key: str, generation_id: str) -> None:
    """Read the router's record of the call and write its cost and vendor on
    the usage record. Gives up quietly after the last delay: the row then
    stays unpriced and Reports values it at list price, marked estimated."""
    for delay in RECONCILE_DELAYS:
        await asyncio.sleep(delay)
        stats = await fetch_generation(base_url, api_key, generation_id)
        if not stats:
            continue
        total, upstream = stats.get("total_cost"), stats.get("upstream_inference_cost")
        if total is None and upstream is None:
            continue
        db = new_session()
        try:
            record = db.get(UsageRecord, record_id)
            if record is None:
                # The request that made it has not committed yet; try again later.
                continue
            record.cost_usd = float(total or 0) + float(upstream or 0)
            served_by = str(stats.get("provider_name") or "")
            if served_by:
                record.served_by = served_by[:60]
            db.commit()
        except Exception:  # noqa: BLE001 - the report loses a price, nothing else
            logger.exception("Could not reconcile usage %s with generation %s", record_id, generation_id)
            db.rollback()
        finally:
            db.close()
        return
