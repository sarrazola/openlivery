"""Cost reports: what the agency's agents cost, rolled up and reply by reply.

Every reply leaves a usage record with what it cost as the provider reported
it (``usage_records.cost_usd``) and, since 0043, the conversation and
message it belongs to. Records that carry no cost (from before, or from a
provider that reported none) are valued at the catalog's list price and
flagged as estimated.
"""

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import Date, String, cast, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, Client, Conversation, Message, UsageRecord, User
from ..schemas import ConversationFacets, ConversationReportPage, CostReport, RepliesPage
from ..services.model_catalog import get_model
from ..services.report_conversations import AD_FIELDS, ConversationListFilters, export_csv, facets, list_conversations
from ..services.report_operations import ConversationFilters, filter_options, operations

router = APIRouter(prefix="/reports", tags=["Reports"])

MAX_EXPORT_ROWS = 5000
MAX_RANGE_DAYS = 366


def _estimated_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """List price from the catalog for usage the provider did not price."""
    info = get_model(model)
    if info is None:
        return Decimal(0)
    return (
        Decimal(input_tokens) / 1000 * Decimal(str(info.input_price_per_1k))
        + Decimal(output_tokens) / 1000 * Decimal(str(info.output_price_per_1k))
    )


def _group_cost(metered, model: str, unpriced_in, unpriced_out) -> Decimal:
    """A grouped row's cost: what its replies reported plus the estimate for
    the replies that reported nothing."""
    total = Decimal(metered or 0)
    unpriced_in, unpriced_out = int(unpriced_in or 0), int(unpriced_out or 0)
    if unpriced_in or unpriced_out:
        total += _estimated_cost(model, unpriced_in, unpriced_out)
    return total


def _money(value: Decimal) -> float:
    return float(round(value, 8))


def _safe_tz(tz: str | None) -> str:
    if not tz:
        return "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return tz


class Filters:
    def __init__(self, agency_id: uuid.UUID, date_from: date, date_to: date,
                 client_id: uuid.UUID | None, agent_id: uuid.UUID | None, model: str | None, q: str | None) -> None:
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        if (date_to - date_from).days > MAX_RANGE_DAYS:
            date_from = date_to - timedelta(days=MAX_RANGE_DAYS)
        self.agency_id = agency_id
        self.date_from = date_from
        self.date_to = date_to
        self.client_id = client_id
        self.agent_id = agent_id
        self.model = (model or "").strip()[:180] or None
        self.q = (q or "").strip()[:120]

    def apply(self, query):
        query = query.where(
            UsageRecord.agency_id == self.agency_id,
            UsageRecord.created_at >= datetime.combine(self.date_from, time.min, tzinfo=timezone.utc),
            UsageRecord.created_at < datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=timezone.utc),
        )
        if self.client_id:
            query = query.where(Conversation.client_id == self.client_id)
        if self.agent_id:
            query = query.where(UsageRecord.agent_id == self.agent_id)
        if self.model:
            query = query.where(UsageRecord.model == self.model)
        if self.q:
            query = query.where(
                Conversation.contact_name.ilike(f"%{self.q}%")
                | cast(UsageRecord.conversation_id, String).like(f"{self.q.lower()}%")
            )
        return query


def _joined(query):
    """Usage records with the reply's context, when the record has it."""
    return (
        query.select_from(UsageRecord)
        .outerjoin(Conversation, Conversation.id == UsageRecord.conversation_id)
        .outerjoin(Client, Client.id == Conversation.client_id)
        .outerjoin(Agent, Agent.id == UsageRecord.agent_id)
    )


# Per group and model: replies, tokens, what the replies reported, and the
# tokens of the replies that reported nothing (priced per model afterwards).
_AGGREGATES = (
    func.count(UsageRecord.id),
    func.coalesce(func.sum(UsageRecord.input_tokens), 0),
    func.coalesce(func.sum(UsageRecord.output_tokens), 0),
    func.sum(UsageRecord.cost_usd),
    func.sum(UsageRecord.input_tokens).filter(UsageRecord.cost_usd.is_(None)),
    func.sum(UsageRecord.output_tokens).filter(UsageRecord.cost_usd.is_(None)),
)


def _grouped(db: Session, filters: Filters, *key_columns):
    """Rows of (key columns..., model, replies, tokens in, tokens out,
    metered cost, unpriced in, unpriced out), one per key and model."""
    query = filters.apply(_joined(select(*key_columns, UsageRecord.model, *_AGGREGATES)))
    return db.execute(query.group_by(*key_columns, UsageRecord.model)).all()


def _fold(rows, key_width: int, label) -> list[dict]:
    """Merge the per-model rows of _grouped into one entry per key, costed."""
    entries: dict = {}
    for row in rows:
        key = tuple(row[:key_width])
        model, replies, tokens_in, tokens_out, metered, unpriced_in, unpriced_out = row[key_width:]
        entry = entries.setdefault(key, {"replies": 0, "input_tokens": 0, "output_tokens": 0, "cost": Decimal(0)})
        entry["replies"] += int(replies)
        entry["input_tokens"] += int(tokens_in)
        entry["output_tokens"] += int(tokens_out)
        entry["cost"] += _group_cost(metered, model, unpriced_in, unpriced_out)
    result = []
    for key, entry in entries.items():
        ident, name = label(key)
        result.append({"id": ident, "name": name, "replies": entry["replies"], "input_tokens": entry["input_tokens"],
                       "output_tokens": entry["output_tokens"], "cost_usd": _money(entry["cost"])})
    return sorted(result, key=lambda item: item["cost_usd"], reverse=True)


@router.get("/costs", response_model=CostReport)
def cost_report(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    client_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    model: str | None = None,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = Filters(user.agency_id, date_from, date_to, client_id, agent_id, model, None)
    zone = _safe_tz(tz)

    by_model = _fold(_grouped(db, filters, UsageRecord.model), 1, lambda key: (key[0], key[0]))
    replies = sum(entry["replies"] for entry in by_model)
    cost = sum((Decimal(str(entry["cost_usd"])) for entry in by_model), Decimal(0))
    conversations = db.scalar(filters.apply(_joined(select(func.count(func.distinct(UsageRecord.conversation_id)))))) or 0

    days: dict = {}
    for row in _grouped(db, filters, cast(func.timezone(zone, UsageRecord.created_at), Date)):
        day, day_model, day_replies, _tokens_in, _tokens_out, metered, unpriced_in, unpriced_out = row
        entry = days.setdefault(day.isoformat(), {"replies": 0, "cost": Decimal(0)})
        entry["replies"] += int(day_replies)
        entry["cost"] += _group_cost(metered, day_model, unpriced_in, unpriced_out)

    return {
        "totals": {
            "cost_usd": _money(cost),
            "replies": replies,
            "conversations": int(conversations),
            "input_tokens": sum(entry["input_tokens"] for entry in by_model),
            "output_tokens": sum(entry["output_tokens"] for entry in by_model),
            "avg_cost_per_reply_usd": _money(cost / replies) if replies else 0.0,
        },
        "by_client": _fold(_grouped(db, filters, Conversation.client_id, Client.name), 2,
                           lambda key: (str(key[0]) if key[0] else None, key[1] or "")),
        "by_agent": _fold(_grouped(db, filters, UsageRecord.agent_id, Agent.name), 2,
                          lambda key: (str(key[0]) if key[0] else None, key[1] or "")),
        "by_model": by_model,
        "by_day": [{"date": day, "replies": entry["replies"], "cost_usd": _money(entry["cost"])}
                   for day, entry in sorted(days.items())],
        "tz": zone,
    }


def _replies_query(filters: Filters):
    query = _joined(select(
        UsageRecord, Conversation.contact_name, Conversation.channel, Conversation.client_id,
        Client.name, Agent.name, Message.tool_calls,
    )).outerjoin(Message, Message.id == UsageRecord.message_id)
    return filters.apply(query).order_by(UsageRecord.created_at.desc())


def _reply(row) -> dict:
    record, contact_name, channel, client_id, client_name, agent_name, tool_calls = row
    if record.cost_usd is not None:
        cost, estimated = Decimal(record.cost_usd), False
    else:
        cost, estimated = _estimated_cost(record.model, record.input_tokens, record.output_tokens), True
    calls = tool_calls or []
    return {
        "id": record.id,
        "created_at": record.created_at,
        "conversation_id": record.conversation_id,
        "contact_name": contact_name,
        "client_id": client_id,
        "client_name": client_name,
        "agent_id": record.agent_id,
        "agent_name": agent_name,
        "channel": channel,
        "model": record.model,
        "served_by": record.served_by or "",
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cached_tokens": record.cached_tokens,
        "reasoning_tokens": record.reasoning_tokens,
        "cost_usd": _money(cost),
        "estimated": estimated,
        "duration_ms": record.duration_ms,
        "tools": len(calls),
        "tool_errors": sum(1 for call in calls if isinstance(call, dict) and call.get("is_error")),
    }


@router.get("/replies", response_model=RepliesPage, responses={200: {"content": {"text/csv": {}}}})
def replies(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    client_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    model: str | None = None,
    q: str | None = None,
    format: str | None = None,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One line per reply, newest first; ``format=csv`` downloads the whole
    range (up to MAX_EXPORT_ROWS)."""
    filters = Filters(user.agency_id, date_from, date_to, client_id, agent_id, model, q)
    query = _replies_query(filters)
    if format == "csv":
        rows = [_reply(row) for row in db.execute(query.limit(MAX_EXPORT_ROWS)).all()]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "reply_id", "conversation", "contact", "client", "agent", "channel", "model", "served_by",
                         "input_tokens", "output_tokens", "cost_usd", "estimated", "duration_ms"])
        for item in rows:
            writer.writerow([
                item["created_at"].isoformat(), item["id"], item["conversation_id"] or "", item["contact_name"] or "",
                item["client_name"] or "", item["agent_name"] or "", item["channel"] or "", item["model"], item["served_by"],
                item["input_tokens"], item["output_tokens"], f"{item['cost_usd']:.8f}", "yes" if item["estimated"] else "",
                item["duration_ms"] if item["duration_ms"] is not None else "",
            ])
        return Response(content=buffer.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="replies-{filters.date_from.isoformat()}-{filters.date_to.isoformat()}.csv"'})
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = [_reply(row) for row in db.execute(query.limit(limit).offset(offset)).all()]
    return {"items": items, "total": int(total)}


@router.get("/operations")
def operations_report(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    client_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    channel: str | None = None,
    model: str | None = None,
    tz: str | None = None,
    bucket: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """How the agents attended the range's conversations: totals, timing and
    message volume, by client and channel and over time."""
    filters = ConversationFilters(
        user.agency_id, date_from=date_from, date_to=date_to, client_id=client_id,
        agent_id=agent_id, channel=channel, tz=tz, model=model, bucket=bucket,
    )
    return operations(db, filters)


@router.get("/filters")
def report_filters(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The clients, agents, channels and models for the report dropdowns."""
    return filter_options(db, user.agency_id)


def _list_filters(agency_id: uuid.UUID, *, date_from, date_to, client_id, agent_id, channel, tz, status, mode,
                  assignee_id, team_id, ad, ad_source_type, ad_source_id, ad_source_url, ad_headline, ad_body,
                  ad_media_type, q) -> ConversationListFilters:
    values = dict(zip(AD_FIELDS, (ad_source_type, ad_source_id, ad_source_url, ad_headline, ad_body, ad_media_type)))
    return ConversationListFilters(
        agency_id, date_from=date_from, date_to=date_to, client_id=client_id, agent_id=agent_id, channel=channel,
        tz=tz, status=status, mode=mode, assignee_id=assignee_id, team_id=team_id, ad=ad,
        ad_values={key: value for key, value in values.items() if value}, q=q,
    )


@router.get("/conversations", response_model=ConversationReportPage, responses={200: {"content": {"text/csv": {}}}})
def conversations_report(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    client_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    channel: str | None = None,
    tz: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    assignee_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    ad: str | None = None,
    ad_source_type: str | None = None,
    ad_source_id: str | None = None,
    ad_source_url: str | None = None,
    ad_headline: str | None = None,
    ad_body: str | None = None,
    ad_media_type: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    format: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One row per conversation that started in the range, newest first,
    with the figures for the filtered set; ``format=csv`` downloads the
    whole list (up to MAX_EXPORT_ROWS). ``ad`` is ``any`` or ``none``; the
    ``ad_*`` parameters match one referral key each."""
    filters = _list_filters(
        user.agency_id, date_from=date_from, date_to=date_to, client_id=client_id, agent_id=agent_id, channel=channel,
        tz=tz, status=status, mode=mode, assignee_id=assignee_id, team_id=team_id, ad=ad, ad_source_type=ad_source_type,
        ad_source_id=ad_source_id, ad_source_url=ad_source_url, ad_headline=ad_headline, ad_body=ad_body,
        ad_media_type=ad_media_type, q=q,
    )
    if format == "csv":
        return Response(
            content=export_csv(db, filters, sort=sort, order=order), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="conversations-{filters.date_from.isoformat()}-{filters.date_to.isoformat()}.csv"'},
        )
    return list_conversations(db, filters, sort=sort, order=order, limit=limit, offset=offset)


@router.get("/conversations/facets", response_model=ConversationFacets)
def conversations_facets(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    client_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    channel: str | None = None,
    tz: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    assignee_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    ad: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The referral keys and values present in the filtered range, with
    counts, for the ad selectors."""
    filters = _list_filters(
        user.agency_id, date_from=date_from, date_to=date_to, client_id=client_id, agent_id=agent_id, channel=channel,
        tz=tz, status=status, mode=mode, assignee_id=assignee_id, team_id=team_id, ad=ad, ad_source_type=None,
        ad_source_id=None, ad_source_url=None, ad_headline=None, ad_body=None, ad_media_type=None, q=q,
    )
    return facets(db, filters)
