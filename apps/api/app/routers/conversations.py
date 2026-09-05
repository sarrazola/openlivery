import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..services.conversation_state import ConversationClosed, STATUSES, note_reply, set_mode, set_status
from ..models import Agent, Conversation, Message, User, now_utc
from ..schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationInboxOut,
    ConversationModeUpdate,
    ConversationStatusUpdate,
    ConversationOut,
    ReactionRequest,
    SendMessageRequest,
)
from ..services.attachments import (
    MAX_ATTACHMENT_BYTES,
    attachment_kind,
    attachment_response,
    conversation_attachment,
    llm_text,
    store_attachment,
)
from ..services.tools import run_completion
from ..services.knowledge import build_system_prompt, retrieve_knowledge
from ..services.operator_media import store_operator_media_reply
from ..services.providers import resolve_agent_credentials
from ..services.usage import record_usage
from ..services.whatsapp import deliver_reaction, resolve_quote, send_channel_message, signal_channel_read
from ..services.whatsapp_inbound import InboundMessage, resolve_inbound_content


router = APIRouter(prefix="/conversations", tags=["Conversations"])

MAX_MEDIA_BYTES = MAX_ATTACHMENT_BYTES


def _conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(
            selectinload(Conversation.messages).selectinload(Message.attachments),
            joinedload(Conversation.agent).joinedload(Agent.client),
        )
        .execution_options(populate_existing=True)
        .where(Conversation.id == conversation_id, Conversation.agency_id == user.agency_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    agent_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Conversation).where(Conversation.agency_id == user.agency_id)
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
    if client_id:
        query = query.where(Conversation.client_id == client_id)
    # Same rule as the inbox: only a new visitor message moves a row up.
    last_inbound = (
        select(Message.conversation_id.label("cid"), func.max(Message.created_at).label("at"))
        .where(Message.kind == "message", Message.sender_type == "visitor")
        .group_by(Message.conversation_id)
        .subquery()
    )
    query = query.outerjoin(last_inbound, last_inbound.c.cid == Conversation.id).order_by(
        func.coalesce(last_inbound.c.at, Conversation.created_at).desc(), Conversation.created_at.desc()
    )
    return db.scalars(query).all()


@router.get("/inbox", response_model=list[ConversationInboxOut])
def inbox(
    agent_id: uuid.UUID | None = None,
    channel: str | None = None,
    mode: str | None = None,
    search: str | None = None,
    unread: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Latest message per conversation, resolved in SQL so we never load full
    # message histories just to build the list.
    ranked = (
        select(
            Message.conversation_id.label("cid"),
            Message.content.label("content"),
            Message.sender_type.label("sender_type"),
            Message.created_at.label("created_at"),
            func.row_number().over(partition_by=Message.conversation_id, order_by=Message.created_at.desc()).label("rn"),
        )
        .where(Message.kind == "message")
        .subquery()
    )
    last = select(ranked).where(ranked.c.rn == 1).subquery()
    unread_counts = (
        select(Message.conversation_id.label("cid"), func.count(Message.id).label("n"))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.sender_type == "visitor",
            or_(Conversation.operator_read_at.is_(None), Message.created_at > Conversation.operator_read_at),
        )
        .group_by(Message.conversation_id)
    ).subquery()
    unread_count = func.coalesce(unread_counts.c.n, 0)
    last_inbound = (
        select(Message.conversation_id.label("cid"), func.max(Message.created_at).label("at"))
        .where(Message.kind == "message", Message.sender_type == "visitor")
        .group_by(Message.conversation_id)
        .subquery()
    )

    query = (
        select(Conversation, Agent.name, last.c.content, unread_count.label("unread_count"), last_inbound.c.at.label("last_inbound_at"))
        .join(Agent, Agent.id == Conversation.agent_id)
        .outerjoin(last, last.c.cid == Conversation.id)
        .outerjoin(unread_counts, unread_counts.c.cid == Conversation.id)
        .outerjoin(last_inbound, last_inbound.c.cid == Conversation.id)
        .where(Conversation.agency_id == user.agency_id)
    )
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
    if channel:
        query = query.where(Conversation.channel == channel)
    if mode in ("ai", "human"):
        query = query.where(Conversation.mode == mode)
    if unread:
        query = query.where(unread_count > 0)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Conversation.title).like(term),
                func.lower(func.coalesce(Conversation.contact_name, "")).like(term),
                func.lower(func.coalesce(last.c.content, "")).like(term),
            )
        )
    # Same rule as the portal: only a new visitor message moves a row up.
    rows = db.execute(
        query.order_by(func.coalesce(last_inbound.c.at, Conversation.created_at).desc(), Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": conv.id,
            "agent_id": conv.agent_id,
            "agent_name": agent_name or "",
            "client_id": conv.client_id,
            "title": conv.title,
            "contact_name": conv.contact_name,
            "channel": conv.channel,
            "mode": conv.mode,
            "preview": (content or "")[:140].strip(),
            "unread": int(row_unread_count) > 0,
            "unread_count": int(row_unread_count),
            "updated_at": conv.updated_at,
            "last_inbound_at": last_inbound_at,
        }
        for conv, agent_name, content, row_unread_count, last_inbound_at in rows
    ]


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.scalar(select(Agent).where(Agent.id == payload.agent_id, Agent.agency_id == user.agency_id))
    if not agent:
        raise HTTPException(status_code=400, detail="The selected agent does not exist")
    conversation = Conversation(
        agency_id=user.agency_id,
        client_id=agent.client_id,
        agent_id=agent.id,
    )
    db.add(conversation)
    db.commit()
    return _conversation(db, user, conversation.id)


@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = _conversation(db, user, conversation_id)
    conversation.operator_read_at = now_utc()
    db.commit()
    # Opening the thread is the operator reading it: blue-tick the latest
    # visitor message on WhatsApp too. Best-effort by design.
    latest_external = db.scalar(
        select(Message.external_message_id)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "user",
            Message.external_message_id.is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if latest_external:
        await signal_channel_read(db, conversation, [latest_external], typing=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _conversation(db, user, conversation_id)


def _ready_agent(db: Session, conversation: Conversation) -> tuple[Agent, tuple[str, str]]:
    """Validate the conversation can produce an AI reply and return the agent + credentials."""
    agent = conversation.agent
    if not agent.is_active:
        raise HTTPException(status_code=400, detail="This agent is inactive")
    credentials = resolve_agent_credentials(db, agent)
    if not credentials or not agent.model.strip():
        raise HTTPException(
            status_code=400,
            detail="This agent is not ready: set its model and add the provider API key in Settings.",
        )
    if conversation.mode == "human":
        raise HTTPException(status_code=409, detail="This conversation is being handled by a person")
    return agent, credentials


async def _generate_reply(
    db: Session,
    user: User,
    conversation: Conversation,
    agent: Agent,
    credentials: tuple[str, str],
    query: str,
) -> Conversation:
    """Run the agent over the current conversation and store the assistant reply."""
    knowledge = await retrieve_knowledge(db, agent, query)
    refreshed = _conversation(db, user, conversation.id)
    exchanged = [item for item in refreshed.messages if item.kind == "message"]
    recent = exchanged[-agent.memory_limit:] if agent.memory_limit else []
    history = [{"role": item.role, "content": llm_text(item)} for item in recent]
    messages = [{"role": "system", "content": build_system_prompt(agent, knowledge.text)}, *history]
    base_url, api_key = credentials
    completion = await run_completion(
        db, agent, base_url, api_key, messages, temperature=agent.temperature, max_tokens=agent.max_tokens
    )
    note_reply(conversation)
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=completion.text,
            sources=knowledge.sources,
            tool_calls=completion.tool_calls,
            sender_type="ai",
            sender_name=agent.name,
        )
    )
    record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
    conversation.updated_at = now_utc()
    db.commit()
    return _conversation(db, user, conversation.id)


@router.post("/{conversation_id}/messages", response_model=ConversationDetail)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    agent, credentials = _ready_agent(db, conversation)

    content = payload.content.strip()
    if not conversation.messages:
        conversation.title = content[:80]
    conversation.updated_at = now_utc()
    db.add(Message(conversation_id=conversation.id, role="user", content=content, sender_type="visitor", sender_name="You"))
    db.commit()
    return await _generate_reply(db, user, conversation, agent, credentials, content)


@router.post("/{conversation_id}/media", response_model=ConversationDetail)
async def send_media_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    agent, credentials = _ready_agent(db, conversation)

    content_type = (file.content_type or "").lower() or "application/octet-stream"
    kind = attachment_kind(content_type)
    data = await file.read(MAX_MEDIA_BYTES + 1)
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large (20 MB max)")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    caption = caption.strip()

    # Same orchestration as the WhatsApp channels: the chat keeps the original
    # file as an attachment, the LLM gets a description/transcript (or a
    # placeholder when the capability is off or no OpenAI key is configured).
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

    if not conversation.messages and caption:
        conversation.title = caption[:80]
    conversation.updated_at = now_utc()
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content=display_content,
        llm_content=llm_content if llm_content != display_content else None,
        sender_type="visitor",
        sender_name="You",
    )
    db.add(message)
    db.flush()
    store_attachment(db, message, data=data, mime=content_type, filename=file.filename, kind=kind)
    db.commit()
    return await _generate_reply(db, user, conversation, agent, credentials, llm_content)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Discard a playground rehearsal. Customer conversations are history and stay."""
    conversation = _conversation(db, user, conversation_id)
    if conversation.channel != "playground":
        raise HTTPException(status_code=409, detail="Only playground conversations can be deleted")
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/attachments/{attachment_id}")
def get_attachment(
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    return attachment_response(conversation_attachment(db, conversation, attachment_id))


@router.patch("/{conversation_id}/mode", response_model=ConversationDetail)
def set_conversation_mode(
    conversation_id: uuid.UUID,
    payload: ConversationModeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    try:
        changed = set_mode(db, conversation, payload.mode, actor=user.name)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if changed:
        db.commit()
    return _conversation(db, user, conversation_id)


@router.patch("/{conversation_id}/status", response_model=ConversationDetail)
def set_conversation_status(
    conversation_id: uuid.UUID,
    payload: ConversationStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    try:
        changed = set_status(db, conversation, payload.status, actor=user.name)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if changed:
        db.commit()
    return _conversation(db, user, conversation_id)


@router.post("/{conversation_id}/reply", response_model=ConversationDetail)
async def reply_as_human(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    quoted_id, quoted_external = resolve_quote(db, conversation, payload.quoted_message_id)
    external_message_id = await send_channel_message(
        db, conversation, payload.content.strip(), quoted_external_id=quoted_external
    )
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=payload.content.strip(),
            sender_type="human",
            sender_name=user.name,
            external_message_id=external_message_id,
            quoted_message_id=quoted_id,
        )
    )
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
    return _conversation(db, user, conversation_id)


@router.post("/{conversation_id}/messages/{message_id}/reaction", response_model=ConversationDetail)
async def react_to_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ReactionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before reacting")
    target = db.scalar(select(Message).where(Message.id == message_id, Message.conversation_id == conversation.id))
    if not target:
        raise HTTPException(status_code=404, detail="Message not found")
    if target.role != "user":
        raise HTTPException(status_code=409, detail="Reactions go on the customer's messages")
    emoji = payload.emoji.strip()
    await deliver_reaction(db, conversation, target, emoji)
    target.reaction = emoji or None
    db.commit()
    return _conversation(db, user, conversation_id)


@router.post("/{conversation_id}/reply-media", response_model=ConversationDetail)
async def reply_media_as_human(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    await store_operator_media_reply(db, conversation, file=file, caption=caption, sender_name=user.name)
    return _conversation(db, user, conversation_id)
