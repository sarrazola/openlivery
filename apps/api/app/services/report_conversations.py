"""The conversation list behind the reports: one row per conversation.

The operational report (``report_operations``) rolls conversations up; this
is the same population, unrolled, so a person can see which conversations a
period, a channel or an ad brought in, filter them and take the list away as
CSV. It never reads message content: counts and timestamps only.

Filters extend ``ConversationFilters`` (range on when the conversation
started, client, agent, channel) with the case's state, who holds it, and
the ad referral stored in ``conversations.acquisition``. The referral keys
are not fixed in the UI: ``facets()`` reports which keys and values the
filtered range actually has, and the page builds a selector per key.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .report_operations import _CONV_FROM, _CONV_METRICS, ConversationFilters, _conv_row, _rows

# Referral keys a person can filter and group by. ``ctwa_clid`` identifies
# one click, so it is kept out: every value would have a count of one.
AD_FIELDS = ("source_type", "source_id", "source_url", "headline", "body", "media_type")
SORTS = {"created_at", "resolved_at", "first_reply_at", "last_message_at"}
MAX_FACET_VALUES = 50
MAX_EXPORT_ROWS = 5000

_PLAYGROUND = "playground"


class ConversationListFilters(ConversationFilters):
    """Everything ``ConversationFilters`` narrows, plus the case's state, who
    holds it, the ad it came from and a contact search. ``client_scope``
    marks a portal listing: one client, no playground, and no social archive
    that was only imported (those never started a case in that inbox)."""

    def __init__(self, agency_id: uuid.UUID, *, date_from: date | None, date_to: date | None,
                 client_id: uuid.UUID | None = None, agent_id: uuid.UUID | None = None, channel: str | None = None,
                 tz: str | None = None, status: str | None = None, mode: str | None = None,
                 assignee_id: uuid.UUID | None = None, team_id: uuid.UUID | None = None,
                 ad: str | None = None, ad_values: dict[str, str] | None = None, q: str | None = None,
                 client_scope: bool = False) -> None:
        super().__init__(agency_id, date_from=date_from, date_to=date_to, client_id=client_id,
                         agent_id=agent_id, channel=channel, tz=tz)
        self.status = status if status in {"open", "resolved"} else None
        self.mode = mode if mode in {"ai", "human"} else None
        self.assignee_id = assignee_id
        self.team_id = team_id
        self.ad = ad if ad in {"any", "none"} else None
        self.ad_values = {key: value.strip()[:500] for key, value in (ad_values or {}).items()
                          if key in AD_FIELDS and value and value.strip()}
        self.q = (q or "").strip()[:120]
        self.client_scope = client_scope

    def without_ad_values(self) -> "ConversationListFilters":
        clone = ConversationListFilters.__new__(ConversationListFilters)
        clone.__dict__.update(self.__dict__)
        clone.ad_values = {}
        return clone

    def where(self, alias: str = "c", stamp: str | None = None) -> tuple[str, dict]:
        base, params = super().where(alias, stamp)
        # The range is read as local days in the viewer's zone: "today" means
        # the day on their clock, not the UTC day.
        zone = ZoneInfo(self.tz)
        if self.date_from:
            params["date_from"] = datetime.combine(self.date_from, time.min, tzinfo=zone)
        if self.date_to:
            params["date_to"] = datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=zone)
        clauses = [base]
        if self.status:
            clauses.append(f"{alias}.status = :status")
            params["status"] = self.status
        if self.mode:
            clauses.append(f"{alias}.mode = :mode")
            params["mode"] = self.mode
        if self.assignee_id:
            clauses.append(f"{alias}.assignee_id = :assignee_id")
            params["assignee_id"] = self.assignee_id
        if self.team_id:
            clauses.append(f"{alias}.team_id = :team_id")
            params["team_id"] = self.team_id
        if self.ad == "any":
            clauses.append(f"{alias}.acquisition IS NOT NULL")
        elif self.ad == "none":
            clauses.append(f"{alias}.acquisition IS NULL")
        for index, (key, value) in enumerate(sorted(self.ad_values.items())):
            clauses.append(f"({alias}.acquisition ->> :ad_key_{index}) = :ad_value_{index}")
            params[f"ad_key_{index}"] = key
            params[f"ad_value_{index}"] = value
        if self.q:
            # ``ct`` is the contacts join every query here carries.
            clauses.append(f"(COALESCE(ct.name, '') ILIKE :q OR COALESCE({alias}.contact_name, '') ILIKE :q OR COALESCE(ct.phone, '') ILIKE :q)")
            params["q"] = f"%{self.q}%"
        if self.client_scope:
            clauses.append(f"{alias}.channel <> :playground")
            params["playground"] = _PLAYGROUND
            clauses.append(
                f"({alias}.social_channel_id IS NULL OR EXISTS (SELECT 1 FROM messages mi WHERE mi.conversation_id = {alias}.id "
                f"AND mi.kind = 'message' AND mi.is_historical = false))"
            )
        return " AND ".join(clauses), params


_LIST_SELECT = """
    c.id, c.created_at, c.status, c.resolved_at, c.archived_at, c.mode, c.channel,
    c.client_id, cl.name AS client_name,
    c.agent_id, ag.name AS agent_name,
    c.contact_id, COALESCE(NULLIF(ct.name, ''), c.contact_name) AS contact_name, ct.phone AS contact_phone,
    c.assignee_id, pu.name AS assignee_name,
    c.team_id, tm.name AS team_name,
    c.first_reply_at, c.taken_over_at, c.acquisition,
    EXTRACT(EPOCH FROM (c.first_reply_at - c.created_at)) AS first_reply_s,
    EXTRACT(EPOCH FROM (c.resolved_at - c.created_at)) AS resolution_s,
    mc.inbound, mc.ai_replies, mc.human_replies, mc.last_message_at
"""

# ``ag`` and ``ct`` match the aliases the filters expect.
_LIST_FROM = """
FROM conversations c
LEFT JOIN clients cl ON cl.id = c.client_id
LEFT JOIN agents ag ON ag.id = c.agent_id
LEFT JOIN contacts ct ON ct.id = c.contact_id
LEFT JOIN portal_users pu ON pu.id = c.assignee_id
LEFT JOIN teams tm ON tm.id = c.team_id
LEFT JOIN LATERAL (
    SELECT COUNT(*) FILTER (WHERE m.sender_type = 'visitor') AS inbound,
           COUNT(*) FILTER (WHERE m.sender_type = 'ai') AS ai_replies,
           COUNT(*) FILTER (WHERE m.sender_type = 'human') AS human_replies,
           MAX(m.created_at) AS last_message_at
    FROM messages m WHERE m.conversation_id = c.id AND m.kind = 'message'
) mc ON true
"""

_COUNT_FROM = "FROM conversations c LEFT JOIN agents ag ON ag.id = c.agent_id LEFT JOIN contacts ct ON ct.id = c.contact_id"


def _row(row) -> dict:
    acquisition = row["acquisition"] if isinstance(row["acquisition"], dict) else None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "resolved_at": row["resolved_at"],
        "archived_at": row["archived_at"],
        "mode": row["mode"],
        "channel": row["channel"],
        "client_id": row["client_id"],
        "client_name": row["client_name"],
        "agent_id": row["agent_id"],
        "agent_name": row["agent_name"],
        "contact_id": row["contact_id"],
        "contact_name": row["contact_name"],
        "contact_phone": row["contact_phone"],
        "assignee_id": row["assignee_id"],
        "assignee_name": row["assignee_name"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
        "first_reply_at": row["first_reply_at"],
        "taken_over_at": row["taken_over_at"],
        "first_reply_s": float(row["first_reply_s"]) if row["first_reply_s"] is not None else None,
        "resolution_s": float(row["resolution_s"]) if row["resolution_s"] is not None else None,
        "inbound": int(row["inbound"] or 0),
        "ai_replies": int(row["ai_replies"] or 0),
        "human_replies": int(row["human_replies"] or 0),
        "last_message_at": row["last_message_at"],
        "acquisition": acquisition,
    }


def _order(sort: str | None, order: str | None) -> str:
    column = sort if sort in SORTS else "created_at"
    direction = "ASC" if order == "asc" else "DESC"
    expression = "mc.last_message_at" if column == "last_message_at" else f"c.{column}"
    return f"{expression} {direction} NULLS LAST, c.id {direction}"


def list_conversations(db: Session, filters: ConversationListFilters, *, sort: str | None = None,
                       order: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """One page of conversations, the total behind the filters, and the
    rolled-up figures for that same population (so the page can head the
    list with how many the AI resolved, how many were handed over, and the
    median first reply)."""
    where, params = filters.where("c")
    items = [_row(row) for row in _rows(
        db, f"SELECT {_LIST_SELECT} {_LIST_FROM} WHERE {where} ORDER BY {_order(sort, order)} LIMIT :limit OFFSET :offset",
        {**params, "limit": limit, "offset": offset},
    )]
    total = int(_rows(db, f"SELECT COUNT(*) AS n {_COUNT_FROM} WHERE {where}", params)[0]["n"] or 0)
    summary = _conv_row(_rows(db, f"SELECT {_CONV_METRICS} {_CONV_FROM} WHERE {where}", params)[0])
    return {"items": items, "total": total, "summary": summary}


def facets(db: Session, filters: ConversationListFilters) -> dict:
    """Which referral keys the filtered range carries and, per key, its
    values with how many conversations each brought. Computed without the
    referral value filters themselves, so a selector keeps its other options
    while one is picked. Also how many conversations came from an ad at all."""
    base = filters.without_ad_values()
    where, params = base.where("c")
    counts = _rows(
        db,
        f"SELECT COUNT(*) FILTER (WHERE c.acquisition IS NOT NULL) AS with_ad, "
        f"COUNT(*) FILTER (WHERE c.acquisition IS NULL) AS without_ad {_COUNT_FROM} WHERE {where}",
        params,
    )[0]
    rows = _rows(
        db,
        f"SELECT kv.key AS key, kv.value AS value, COUNT(*) AS n {_COUNT_FROM}, "
        f"LATERAL json_each_text(c.acquisition) kv WHERE {where} AND c.acquisition IS NOT NULL "
        f"AND kv.key = ANY(:keys) AND kv.value <> '' GROUP BY 1, 2 ORDER BY 1, 3 DESC, 2",
        {**params, "keys": list(AD_FIELDS)},
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        values = grouped.setdefault(row["key"], [])
        if len(values) < MAX_FACET_VALUES:
            values.append({"value": row["value"], "count": int(row["n"])})
    return {
        "with_ad": int(counts["with_ad"] or 0),
        "without_ad": int(counts["without_ad"] or 0),
        "facets": [{"key": key, "values": grouped[key]} for key in AD_FIELDS if key in grouped],
    }


CSV_COLUMNS = (
    "started_at", "conversation", "status", "resolved_at", "mode", "channel", "client", "agent", "contact", "phone",
    "assignee", "team", "first_reply_s", "resolution_s", "inbound", "ai_replies", "human_replies", "last_message_at",
    *(f"ad_{field}" for field in AD_FIELDS),
)


def export_csv(db: Session, filters: ConversationListFilters, *, sort: str | None = None, order: str | None = None) -> str:
    """The whole filtered list (up to MAX_EXPORT_ROWS), newest first unless
    told otherwise, with the referral flattened into one column per key."""
    where, params = filters.where("c")
    rows = _rows(
        db, f"SELECT {_LIST_SELECT} {_LIST_FROM} WHERE {where} ORDER BY {_order(sort, order)} LIMIT :limit",
        {**params, "limit": MAX_EXPORT_ROWS},
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for raw in rows:
        item = _row(raw)
        acquisition = item["acquisition"] or {}
        stamp = lambda value: value.isoformat() if value else ""  # noqa: E731
        number = lambda value: "" if value is None else (int(value) if float(value).is_integer() else round(value, 1))  # noqa: E731
        writer.writerow([
            stamp(item["created_at"]), str(item["id"]), item["status"], stamp(item["resolved_at"]), item["mode"], item["channel"],
            item["client_name"] or "", item["agent_name"] or "", item["contact_name"] or "", item["contact_phone"] or "",
            item["assignee_name"] or "", item["team_name"] or "", number(item["first_reply_s"]), number(item["resolution_s"]),
            item["inbound"], item["ai_replies"], item["human_replies"], stamp(item["last_message_at"]),
            *(acquisition.get(field, "") for field in AD_FIELDS),
        ])
    return buffer.getvalue()
