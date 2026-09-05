import uuid

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..services.conversation_state import exchanged_only
from ..models import Agency, Agent, Client, Conversation, Message, MessageAttachment, WidgetChannel, now_utc
from ..ratelimit import public_asset_rate_limit, widget_poll_rate_limit, widget_rate_limit
from ..schemas import WidgetConfigOut, WidgetMessageIn, WidgetReply
from ..services.attachments import (
    MAX_ATTACHMENT_BYTES,
    MAX_WIDGET_ATTACHMENTS,
    attachment_kind,
    attachment_response,
    conversation_attachment,
    ensure_uploadable,
    llm_text,
    logo_response,
    store_attachment,
)
from ..services.tools import run_completion
from ..services.knowledge import build_system_prompt, retrieve_knowledge
from ..services.providers import resolve_agent_credentials
from ..services.usage import record_usage
from ..services.notifications import notify_needs_human
from ..services.whatsapp_inbound import InboundMessage, resolve_inbound_content


router = APIRouter(prefix="/widget", tags=["Widget"])

HISTORY_LIMIT = 50


def _message_out(item: Message) -> dict:
    return {
        "id": item.id,
        "role": item.role,
        "content": item.content,
        "created_at": item.created_at,
        "sender_type": item.sender_type,
        "sender_name": item.sender_name,
        "attachments": [
            {"id": a.id, "kind": a.kind, "mime": a.mime, "filename": a.filename, "size_bytes": a.size_bytes}
            for a in item.attachments
        ],
    }


def _channel(db: Session, public_id: str) -> WidgetChannel:
    """The client's web chat behind a public id: only while it is enabled and
    the client is active."""
    channel = db.scalar(
        select(WidgetChannel)
        .join(Client, Client.id == WidgetChannel.client_id)
        .options(joinedload(WidgetChannel.agent).joinedload(Agent.client))
        .where(WidgetChannel.public_id == public_id, WidgetChannel.is_enabled.is_(True), Client.is_active.is_(True))
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Widget not found")
    return channel


def _session_filters(channel: WidgetChannel, session_id: str):
    return (Conversation.widget_channel_id == channel.id, Conversation.external_chat_id == f"widget:{session_id}")


def _find_conversation(db: Session, channel: WidgetChannel, session_id: str) -> Conversation | None:
    """The visitor's latest case. Earlier, resolved ones stay as history."""
    return db.scalar(
        select(Conversation).where(*_session_filters(channel, session_id)).order_by(Conversation.created_at.desc()).limit(1)
    )


def _session_messages(
    db: Session,
    channel: WidgetChannel,
    session_id: str,
    *,
    after: datetime | None = None,
    conversation_id: uuid.UUID | None = None,
) -> list[Message]:
    """What was exchanged with this visitor, oldest first: one case when
    ``conversation_id`` is given, otherwise everything since ``after``.
    Activity lines never leave the inbox."""
    query = (
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .options(selectinload(Message.attachments))
        .where(*_session_filters(channel, session_id), Message.kind == "message")
    )
    if after is not None:
        query = query.where(Message.created_at > after)
    if conversation_id is not None:
        query = query.where(Conversation.id == conversation_id)
    rows = db.scalars(query.order_by(Message.created_at.desc()).limit(HISTORY_LIMIT)).all()
    return list(reversed(rows))


def _previous_cases(db: Session, channel: WidgetChannel, session_id: str, current: Conversation) -> list[dict]:
    """The visitor's earlier cases, newest first, with how much each holds."""
    counts = (
        select(Message.conversation_id.label("cid"), func.count(Message.id).label("n"))
        .where(Message.kind == "message")
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(Conversation, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.cid == Conversation.id)
        .where(*_session_filters(channel, session_id), Conversation.id != current.id)
        .order_by(Conversation.created_at.desc())
        .limit(20)
    ).all()
    return [
        {"id": conv.id, "title": conv.title, "created_at": conv.created_at, "resolved_at": conv.resolved_at, "message_count": int(n)}
        for conv, n in rows
    ]


def _conversation(db: Session, channel: WidgetChannel, session_id: str) -> Conversation:
    """The open case for this visitor, or a fresh one: like WhatsApp, a
    message after a resolution starts a new conversation."""
    conversation = _find_conversation(db, channel, session_id)
    if conversation is not None and conversation.status == "resolved":
        conversation = None
    if not conversation:
        conversation = Conversation(
            agency_id=channel.agency_id,
            client_id=channel.client_id,
            agent_id=channel.agent_id,
            widget_channel_id=channel.id,
            channel="widget",
            external_chat_id=f"widget:{session_id}",
            title="Web chat",
        )
        db.add(conversation)
        db.flush()
    return conversation


@router.get("/{public_id}", response_model=WidgetConfigOut)
def widget_config(public_id: str, db: Session = Depends(get_db)):
    channel = _channel(db, public_id)
    agent = channel.agent
    agency = db.get(Agency, channel.agency_id)
    client = db.get(Client, channel.client_id)
    has_logo = (client and client.logo_mime) or (agency and agency.logo_data)
    return {
        "title": agent.name,
        "greeting": channel.greeting,
        "color": channel.color or (agency.brand_color if agency else ""),
        "position": channel.position,
        "agency_name": agency.name if agency else "",
        "logo_url": f"/api/widget/{public_id}/logo" if has_logo else None,
    }


@router.get("/{public_id}/logo", dependencies=[Depends(public_asset_rate_limit)])
def widget_logo(public_id: str, db: Session = Depends(get_db)):
    """Public logo for the widget header: the client's own logo when set,
    otherwise the agency logo."""
    channel = _channel(db, public_id)
    client = db.get(Client, channel.client_id)
    if client and client.logo_data and client.logo_mime:
        return logo_response(client.logo_data, client.logo_mime)
    agency = db.get(Agency, channel.agency_id)
    if agency and agency.logo_data and agency.logo_mime:
        return logo_response(agency.logo_data, agency.logo_mime)
    raise HTTPException(status_code=404, detail="No logo")


@router.get("/{public_id}/history", response_model=WidgetReply, dependencies=[Depends(widget_rate_limit)])
def widget_history(public_id: str, session_id: str, db: Session = Depends(get_db)):
    channel = _channel(db, public_id)
    conversation = _find_conversation(db, channel, session_id)
    if not conversation:
        return {"mode": "ai", "status": "open", "reply": None, "messages": []}
    # The current case only; earlier ones are listed, and fetched on demand.
    return {
        "mode": conversation.mode,
        "status": conversation.status,
        "conversation_id": conversation.id,
        "reply": None,
        "messages": [_message_out(item) for item in _session_messages(db, channel, session_id, conversation_id=conversation.id)],
        "previous": _previous_cases(db, channel, session_id, conversation),
    }


@router.get("/{public_id}/conversations/{conversation_id}", response_model=WidgetReply, dependencies=[Depends(widget_rate_limit)])
def widget_case(public_id: str, conversation_id: uuid.UUID, session_id: str, db: Session = Depends(get_db)):
    """One earlier case of this visitor, read-only."""
    channel = _channel(db, public_id)
    conversation = db.scalar(select(Conversation).where(*_session_filters(channel, session_id), Conversation.id == conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "mode": conversation.mode,
        "status": conversation.status,
        "conversation_id": conversation.id,
        "reply": None,
        "messages": [_message_out(item) for item in _session_messages(db, channel, session_id, conversation_id=conversation.id)],
    }


@router.get("/{public_id}/updates", response_model=WidgetReply, dependencies=[Depends(widget_poll_rate_limit)])
def widget_updates(
    public_id: str,
    session_id: str,
    after: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """What arrived since ``after``: a person's replies while they hold the
    conversation, an agent's replies, and where the case stands. The widget
    polls this while it is open, so a human taking over is visible live."""
    channel = _channel(db, public_id)
    conversation = _find_conversation(db, channel, session_id)
    if not conversation:
        return {"mode": "ai", "status": "open", "reply": None, "messages": []}
    return {
        "mode": conversation.mode,
        "status": conversation.status,
        "conversation_id": conversation.id,
        "reply": None,
        "messages": [_message_out(item) for item in _session_messages(db, channel, session_id, after=after, conversation_id=conversation.id)],
    }


@router.get("/{public_id}/attachments/{attachment_id}", dependencies=[Depends(widget_rate_limit)])
def widget_attachment(public_id: str, attachment_id: uuid.UUID, session_id: str, db: Session = Depends(get_db)):
    channel = _channel(db, public_id)
    # The attachment may belong to an earlier, resolved case of the same visitor.
    conversation = db.scalar(
        select(Conversation)
        .join(Message, Message.conversation_id == Conversation.id)
        .join(MessageAttachment, MessageAttachment.message_id == Message.id)
        .where(*_session_filters(channel, session_id), MessageAttachment.id == attachment_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment_response(conversation_attachment(db, conversation, attachment_id))


async def _widget_ai_reply(db: Session, agent: Agent, conversation: Conversation, query: str) -> str | None:
    """Generate and store the AI reply for a widget conversation; None when the
    agent is not ready or the completion fails."""
    if conversation.mode == "human":
        return None
    credentials = resolve_agent_credentials(db, agent)
    if not agent.is_active or not credentials or not agent.model.strip():
        return None

    knowledge = await retrieve_knowledge(db, agent, query)
    db.refresh(conversation)
    history = db.scalars(
        exchanged_only(select(Message).where(Message.conversation_id == conversation.id))
        .order_by(Message.created_at.desc())
        .limit(agent.memory_limit or HISTORY_LIMIT)
    ).all()
    history = list(reversed(history))
    messages = [
        {"role": "system", "content": build_system_prompt(agent, knowledge.text)},
        *[{"role": item.role, "content": llm_text(item)} for item in history],
    ]
    base_url, api_key = credentials
    try:
        completion = await run_completion(
            db, agent, base_url, api_key, messages,
            temperature=agent.temperature, max_tokens=agent.max_tokens,
        )
    except HTTPException:
        return None

    conversation.updated_at = now_utc()
    db.add(Message(conversation_id=conversation.id, role="assistant", content=completion.text, sources=knowledge.sources, tool_calls=completion.tool_calls, sender_type="ai", sender_name=agent.name))
    record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
    db.commit()
    return completion.text


@router.post("/{public_id}/messages", response_model=WidgetReply, dependencies=[Depends(widget_rate_limit)])
async def widget_message(public_id: str, payload: WidgetMessageIn, db: Session = Depends(get_db)):
    channel = _channel(db, public_id)
    agent = channel.agent
    conversation = _conversation(db, channel, payload.session_id)

    content = payload.content.strip()
    if conversation.title == "Web chat":
        conversation.title = content[:80]
    conversation.updated_at = now_utc()
    db.add(Message(conversation_id=conversation.id, role="user", content=content, sender_type="visitor", sender_name="Visitor"))
    db.commit()

    if conversation.mode == "human":
        await notify_needs_human(db, conversation, content)
        return {"mode": "human", "status": conversation.status, "conversation_id": conversation.id, "reply": None, "messages": []}
    reply = await _widget_ai_reply(db, agent, conversation, content)
    return {"mode": "ai", "status": conversation.status, "conversation_id": conversation.id, "reply": reply, "reply_at": now_utc() if reply else None, "messages": []}


@router.post("/{public_id}/media", response_model=WidgetReply, dependencies=[Depends(widget_rate_limit)])
async def widget_media(
    public_id: str,
    session_id: str = Form(...),
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    db: Session = Depends(get_db),
):
    channel = _channel(db, public_id)
    agent = channel.agent
    conversation = _conversation(db, channel, session_id)

    content_type = (file.content_type or "").lower() or "application/octet-stream"
    ensure_uploadable(content_type)
    stored = db.scalar(
        select(func.count(MessageAttachment.id))
        .join(Message, Message.id == MessageAttachment.message_id)
        .where(Message.conversation_id == conversation.id)
    )
    if (stored or 0) >= MAX_WIDGET_ATTACHMENTS:
        raise HTTPException(status_code=429, detail="This conversation reached its attachment limit")
    kind = attachment_kind(content_type)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large (20 MB max)")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    caption = caption.strip()[:8000]

    display_content, llm_content = await resolve_inbound_content(
        db,
        agent,
        InboundMessage(
            external_message_id="",
            external_chat_id="",
            text=caption,
            media_kind=kind,
            media_bytes=data,
            media_mime=content_type,
        ),
    )
    if conversation.title == "Web chat" and caption:
        conversation.title = caption[:80]
    conversation.updated_at = now_utc()
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content=display_content,
        llm_content=llm_content if llm_content != display_content else None,
        sender_type="visitor",
        sender_name="Visitor",
    )
    db.add(message)
    db.flush()
    store_attachment(db, message, data=data, mime=content_type, filename=file.filename, kind=kind)
    db.commit()

    mode = "human" if conversation.mode == "human" else "ai"
    if mode == "human":
        await notify_needs_human(db, conversation, display_content or llm_content)
    reply = None if mode == "human" else await _widget_ai_reply(db, agent, conversation, llm_content)
    # Return the refreshed history so the client can render the new attachment.
    history = _session_messages(db, channel, session_id, conversation_id=conversation.id)
    return {"mode": mode, "status": conversation.status, "conversation_id": conversation.id, "reply": reply, "messages": [_message_out(item) for item in history]}
