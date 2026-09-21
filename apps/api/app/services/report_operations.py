"""Operational reports: how the agency's agents attended conversations.

The cost side lives in ``routers/reports.py`` (what replies cost). This is
the other half of the reports page: conversations, contacts, how many the AI
resolved, timing and message volume, rolled up and broken down by client and
channel. Everything here reads core tables (``conversations``, ``messages``,
``agents``, ``contacts``, ``clients``); nothing external.

Written as raw SQL because the metrics lean on window/percentile functions and
a lateral join that read poorly through the ORM. The session's search_path is
already the caller's, whatever the deployment set it to, and every query is
scoped to the agency by id.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

BUCKETS = {"day", "week", "month", "year"}
MAX_RANGE_DAYS = 366


def safe_bucket(value: str | None) -> str:
    return value if value in BUCKETS else "day"


def safe_tz(tz: str | None) -> str:
    if not tz:
        return "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return tz


class ConversationFilters:
    """Range and scope for conversation-level reports. The range applies to
    when the conversation started; client, agent and channel narrow it."""

    def __init__(self, agency_id: uuid.UUID, *, date_from: date | None, date_to: date | None,
                 client_id: uuid.UUID | None, agent_id: uuid.UUID | None, channel: str | None,
                 tz: str | None, model: str | None = None, provider: str | None = None, bucket: str | None = None) -> None:
        if date_from and date_to:
            if date_to < date_from:
                date_from, date_to = date_to, date_from
            if (date_to - date_from).days > MAX_RANGE_DAYS:
                date_from = date_to - timedelta(days=MAX_RANGE_DAYS)
        self.agency_id = agency_id
        self.date_from = date_from
        self.date_to = date_to
        self.client_id = client_id
        self.agent_id = agent_id
        self.channel = (channel or "").strip()[:40] or None
        self.tz = safe_tz(tz)
        self.model = (model or "").strip()[:180] or None
        self.provider = (provider or "").strip()[:30] or None
        self.bucket = safe_bucket(bucket)

    def where(self, alias: str = "c", stamp: str | None = None) -> tuple[str, dict]:
        stamp = stamp or f"{alias}.created_at"
        clauses = [f"{alias}.agency_id = :agency_id"]
        params: dict = {"agency_id": self.agency_id, "tz": self.tz, "bucket": self.bucket}
        start = datetime.combine(self.date_from, time.min, tzinfo=timezone.utc) if self.date_from else datetime(1970, 1, 1, tzinfo=timezone.utc)
        params["date_from"] = start
        clauses.append(f"{stamp} >= :date_from")
        if self.date_to:
            clauses.append(f"{stamp} < :date_to")
            params["date_to"] = datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if self.client_id:
            clauses.append(f"{alias}.client_id = :client_id")
            params["client_id"] = self.client_id
        if self.agent_id:
            clauses.append(f"{alias}.agent_id = :agent_id")
            params["agent_id"] = self.agent_id
        if self.channel:
            clauses.append(f"{alias}.channel = :channel")
            params["channel"] = self.channel
        if self.model:
            clauses.append("ag.model = :model")
            params["model"] = self.model
        if self.provider:
            clauses.append("ag.provider = :provider")
            params["provider"] = self.provider
        return " AND ".join(clauses), params


_CONV_METRICS = """
    COUNT(*) AS conversations,
    COUNT(DISTINCT c.contact_id) AS contacts,
    COUNT(DISTINCT c.contact_id) FILTER (WHERE ct.created_at >= :date_from) AS new_contacts,
    COUNT(*) FILTER (WHERE c.resolved_at IS NOT NULL AND c.taken_over_at IS NULL) AS ai_resolved,
    COUNT(*) FILTER (WHERE c.taken_over_at IS NOT NULL) AS handoffs,
    COUNT(*) FILTER (WHERE c.resolved_at IS NULL) AS open,
    COUNT(*) FILTER (WHERE c.first_reply_at IS NULL) AS unanswered,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (c.first_reply_at - c.created_at))) AS first_reply_s,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (c.resolved_at - c.created_at))) AS resolution_s,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (hr.first_human_at - c.taken_over_at))) AS human_wait_s
"""

_CONV_FROM = """
FROM conversations c
LEFT JOIN agents ag ON ag.id = c.agent_id
LEFT JOIN contacts ct ON ct.id = c.contact_id
LEFT JOIN LATERAL (
    SELECT MIN(m.created_at) AS first_human_at FROM messages m
    WHERE m.conversation_id = c.id AND m.sender_type = 'human' AND m.created_at >= c.taken_over_at
) hr ON c.taken_over_at IS NOT NULL
"""

_MSG_METRICS = """
    COUNT(*) FILTER (WHERE m.sender_type = 'visitor') AS inbound,
    COUNT(*) FILTER (WHERE m.sender_type = 'ai') AS ai_replies,
    COUNT(*) FILTER (WHERE m.sender_type = 'human') AS human_replies,
    COUNT(*) FILTER (WHERE m.delivery_status = 'failed') AS delivery_failures,
    COALESCE(SUM((
        SELECT COUNT(*) FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(m.tool_calls::jsonb) = 'array' THEN m.tool_calls::jsonb ELSE '[]'::jsonb END
        ) e WHERE COALESCE((e->>'is_error')::boolean, false)
    )), 0) AS tool_errors
"""

_MSG_FROM = "FROM messages m JOIN conversations c ON c.id = m.conversation_id LEFT JOIN agents ag ON ag.id = c.agent_id"


def _conv_row(row) -> dict:
    conversations = int(row["conversations"] or 0)
    return {
        "conversations": conversations,
        "contacts": int(row["contacts"] or 0),
        "new_contacts": int(row["new_contacts"] or 0),
        "ai_resolved": int(row["ai_resolved"] or 0),
        "ai_resolved_pct": round(100 * int(row["ai_resolved"] or 0) / conversations, 1) if conversations else 0.0,
        "handoffs": int(row["handoffs"] or 0),
        "open": int(row["open"] or 0),
        "unanswered": int(row["unanswered"] or 0),
        "first_reply_s": float(row["first_reply_s"]) if row["first_reply_s"] is not None else None,
        "resolution_s": float(row["resolution_s"]) if row["resolution_s"] is not None else None,
        "human_wait_s": float(row["human_wait_s"]) if row["human_wait_s"] is not None else None,
    }


def _msg_row(row) -> dict:
    return {
        "inbound": int(row["inbound"] or 0),
        "ai_replies": int(row["ai_replies"] or 0),
        "human_replies": int(row["human_replies"] or 0),
        "delivery_failures": int(row["delivery_failures"] or 0),
        "tool_errors": int(row["tool_errors"] or 0),
    }


def _rows(db: Session, sql: str, params: dict):
    return db.execute(text(sql), params).mappings().all()


def operations(db: Session, filters: ConversationFilters) -> dict:
    """Totals, breakdowns and timing for the conversations that started in
    the range. Message counts cover messages sent in the range, whichever
    conversation they belong to, so a long-running chat still counts."""
    where, params = filters.where("c")
    msg_where, msg_params = filters.where("c", stamp="m.created_at")
    msg_params["date_from"] = params["date_from"]

    totals = _rows(db, f"SELECT {_CONV_METRICS} {_CONV_FROM} WHERE {where}", params)[0]
    messages = _rows(db, f"SELECT {_MSG_METRICS} {_MSG_FROM} WHERE m.kind = 'message' AND {msg_where}", msg_params)[0]

    by_client_rows = _rows(
        db,
        f"SELECT c.client_id, cl.name AS client_name, {_CONV_METRICS} {_CONV_FROM} "
        f"LEFT JOIN clients cl ON cl.id = c.client_id WHERE {where} GROUP BY 1, 2",
        params,
    )
    by_client_msgs = _rows(
        db,
        f"SELECT c.client_id, {_MSG_METRICS} {_MSG_FROM} WHERE m.kind = 'message' AND {msg_where} GROUP BY 1",
        msg_params,
    )
    by_channel_rows = _rows(db, f"SELECT c.channel, {_CONV_METRICS} {_CONV_FROM} WHERE {where} GROUP BY 1", params)
    by_channel_msgs = _rows(
        db, f"SELECT c.channel, {_MSG_METRICS} {_MSG_FROM} WHERE m.kind = 'message' AND {msg_where} GROUP BY 1", msg_params
    )
    daily_conversations = _rows(
        db,
        f"SELECT date_trunc(:bucket, c.created_at AT TIME ZONE :tz)::date AS day, COUNT(*) AS conversations, "
        f"COUNT(*) FILTER (WHERE c.taken_over_at IS NOT NULL) AS handoffs FROM conversations c "
        f"LEFT JOIN agents ag ON ag.id = c.agent_id WHERE {where} GROUP BY 1 ORDER BY 1",
        params,
    )
    daily_messages = _rows(
        db,
        f"SELECT date_trunc(:bucket, m.created_at AT TIME ZONE :tz)::date AS day, COUNT(*) FILTER (WHERE m.sender_type = 'visitor') AS inbound, "
        f"COUNT(*) FILTER (WHERE m.sender_type IN ('ai', 'human')) AS outbound {_MSG_FROM} "
        f"WHERE m.kind = 'message' AND {msg_where} GROUP BY 1 ORDER BY 1",
        msg_params,
    )

    msgs_by_client = {str(row["client_id"]): _msg_row(row) for row in by_client_msgs if row["client_id"]}
    msgs_by_channel = {row["channel"]: _msg_row(row) for row in by_channel_msgs}
    empty_msgs = _msg_row({"inbound": 0, "ai_replies": 0, "human_replies": 0, "delivery_failures": 0, "tool_errors": 0})

    days: dict[str, dict] = {}
    for row in daily_conversations:
        days.setdefault(row["day"].isoformat(), {"day": row["day"].isoformat(), "conversations": 0, "handoffs": 0, "inbound": 0, "outbound": 0})
        days[row["day"].isoformat()].update(conversations=int(row["conversations"]), handoffs=int(row["handoffs"]))
    for row in daily_messages:
        entry = days.setdefault(row["day"].isoformat(), {"day": row["day"].isoformat(), "conversations": 0, "handoffs": 0, "inbound": 0, "outbound": 0})
        entry.update(inbound=int(row["inbound"] or 0), outbound=int(row["outbound"] or 0))

    return {
        "tz": filters.tz,
        "bucket": filters.bucket,
        "totals": {**_conv_row(totals), **_msg_row(messages)},
        "by_client": sorted(
            [{"id": str(row["client_id"]) if row["client_id"] else None, "name": row["client_name"] or "",
              **_conv_row(row), **msgs_by_client.get(str(row["client_id"]), empty_msgs)} for row in by_client_rows],
            key=lambda entry: -entry["conversations"],
        ),
        "by_channel": sorted(
            [{"id": row["channel"], "name": row["channel"] or "", **_conv_row(row), **msgs_by_channel.get(row["channel"], empty_msgs)}
             for row in by_channel_rows],
            key=lambda entry: -entry["conversations"],
        ),
        "by_period": [days[key] for key in sorted(days)],
    }


def filter_options(db: Session, agency_id: uuid.UUID) -> dict:
    """The clients, agents, channels and models the agency has, for the report
    filter dropdowns."""
    clients = _rows(db, "SELECT id, name FROM clients WHERE agency_id = :a ORDER BY name", {"a": agency_id})
    agents = _rows(db, "SELECT id, name, client_id FROM agents WHERE agency_id = :a AND deleted_at IS NULL ORDER BY name", {"a": agency_id})
    channels = _rows(db, "SELECT DISTINCT channel FROM conversations WHERE agency_id = :a AND channel <> '' ORDER BY channel", {"a": agency_id})
    models = _rows(db, "SELECT DISTINCT model FROM usage_records WHERE agency_id = :a AND model <> '' ORDER BY model", {"a": agency_id})
    return {
        "clients": [{"id": str(row["id"]), "name": row["name"]} for row in clients],
        "agents": [{"id": str(row["id"]), "name": row["name"], "client_id": str(row["client_id"])} for row in agents],
        "channels": [row["channel"] for row in channels],
        "models": [row["model"] for row in models],
    }
