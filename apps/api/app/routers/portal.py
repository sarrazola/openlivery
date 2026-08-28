import uuid

from fastapi import APIRouter, Cookie, Depends, Header, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import get_settings
from ..database import get_db
from ..models import Agency, Agent, Client, Conversation, Message, PortalUser, now_utc
from ..ratelimit import login_rate_limit, public_asset_rate_limit
from ..schemas import (
    AgentSummary,
    ConversationDetail,
    ConversationModeUpdate,
    ConversationStatusUpdate,
    ConversationOut,
    PortalInboxSummary,
    PortalLoginRequest,
    PortalPublicOut,
    PortalSessionOut,
    SendMessageRequest,
)
from ..security import create_portal_token, decode_portal_token, verify_password
from ..services.conversation_state import note_reply, set_mode, set_status
from ..services.attachments import attachment_response, conversation_attachment, logo_response
from ..services.operator_media import store_operator_media_reply
from ..services.whatsapp import send_channel_message


router = APIRouter(prefix="/portal", tags=["Client portal"])


def _public_client(db: Session, slug: str) -> Client:
    client = db.scalar(select(Client).where(Client.portal_slug == slug, Client.portal_enabled.is_(True)))
    if not client:
        raise HTTPException(status_code=404, detail="Portal not found or disabled")
    return client


def _portal_client(
    slug: str,
    portal_access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Client:
    # The browser portal carries the session in an httpOnly cookie. Native
    # clients cannot rely on cookie persistence across restarts, so the same
    # token is also accepted as a bearer credential.
    token = portal_access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to the portal")
    payload = decode_portal_token(token)
    if not payload or payload.get("portal_slug") != slug:
        raise HTTPException(status_code=401, detail="The portal session expired")
    try:
        client_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid portal session") from exc
    client = db.scalar(select(Client).where(Client.id == client_id, Client.portal_slug == slug, Client.portal_enabled.is_(True)))
    if not client:
        raise HTTPException(status_code=401, detail="The portal is no longer available")
    return client


def _portal_user(
    portal_access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> PortalUser | None:
    """The person behind the session, when the token names one.

    Sessions issued before portal users existed carry no person, and those keep
    working for reading. Anything that needs to know who acted should depend on
    this and treat None as "the business itself".
    """
    token = portal_access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    payload = decode_portal_token(token) if token else None
    raw_user = (payload or {}).get("pu")
    if not raw_user:
        return None
    try:
        user = db.get(PortalUser, uuid.UUID(raw_user))
    except (ValueError, TypeError):
        return None
    return user if user and user.is_active else None


def _sender_name(
    slug: str,
    user: PortalUser | None = Depends(_portal_user),
    db: Session = Depends(get_db),
) -> str:
    """Who to sign a reply as.

    Now that a portal can have several people, a reply should carry the name of
    the one who wrote it rather than the business's. Two cases fall back to the
    business: a session issued before portal users existed, and a person with no
    name set - their e-mail is a login, and this name is shown to the customer.
    """
    if user and user.name.strip():
        return user.name.strip()
    client = db.scalar(select(Client).where(Client.portal_slug == slug))
    return client.name if client else "Support"


def _detail(db: Session, client: Client, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages).selectinload(Message.attachments), joinedload(Conversation.agent))
        .execution_options(populate_existing=True)
        .where(Conversation.id == conversation_id, Conversation.client_id == client.id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/{slug}", response_model=PortalPublicOut)
def public_portal(slug: str, db: Session = Depends(get_db)):
    client = _public_client(db, slug)
    agency = db.get(Agency, client.agency_id)
    return {
        "client_name": client.name,
        "portal_title": client.portal_title or f"{client.name} Inbox",
        "portal_slug": client.portal_slug,
        "agency_name": agency.name,
        "agency_brand_color": agency.brand_color,
        # Login page uses the agency logo; the client's own space (inbox) uses
        # the client logo when set.
        "agency_logo_url": f"/api/portal/{slug}/logo" if agency.logo_data else None,
        "client_logo_url": f"/api/portal/{slug}/client-logo" if client.logo_mime else None,
    }


@router.get("/{slug}/logo", dependencies=[Depends(public_asset_rate_limit)])
def public_logo(slug: str, db: Session = Depends(get_db)):
    client = _public_client(db, slug)
    agency = db.get(Agency, client.agency_id)
    if not agency.logo_data or not agency.logo_mime:
        raise HTTPException(status_code=404, detail="Logo not found")
    return logo_response(agency.logo_data, agency.logo_mime)


@router.get("/{slug}/client-logo", dependencies=[Depends(public_asset_rate_limit)])
def public_client_logo(slug: str, db: Session = Depends(get_db)):
    client = _public_client(db, slug)
    if not client.logo_data or not client.logo_mime:
        raise HTTPException(status_code=404, detail="Logo not found")
    return logo_response(client.logo_data, client.logo_mime)


@router.post("/{slug}/login", response_model=PortalSessionOut, dependencies=[Depends(login_rate_limit)])
def portal_login(slug: str, payload: PortalLoginRequest, response: Response, db: Session = Depends(get_db)):
    client = _public_client(db, slug)
    email = payload.email.lower()
    portal_user = db.scalar(
        select(PortalUser).where(
            PortalUser.client_id == client.id,
            PortalUser.email == email,
            PortalUser.is_active.is_(True),
        )
    )
    if not portal_user or not verify_password(payload.password, portal_user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    settings = get_settings()
    response.set_cookie(
        key="portal_access_token",
        value=create_portal_token(
            str(client.id), client.portal_slug, str(portal_user.id) if portal_user else None
        ),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_minutes * 60,
        path="/",
    )
    agency = db.get(Agency, client.agency_id)
    return {"client_id": client.id, "client_name": client.name, "portal_slug": client.portal_slug, "agency_name": agency.name}


@router.post("/{slug}/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(response: Response):
    response.delete_cookie("portal_access_token", path="/")


@router.get("/{slug}/me", response_model=PortalSessionOut)
def portal_me(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    agency = db.get(Agency, client.agency_id)
    return {"client_id": client.id, "client_name": client.name, "portal_slug": client.portal_slug, "agency_name": agency.name}


@router.get("/{slug}/agents", response_model=list[AgentSummary])
def portal_agents(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return db.scalars(select(Agent).where(Agent.client_id == client.id).order_by(Agent.name)).all()


@router.get("/{slug}/conversations", response_model=list[ConversationOut])
def portal_conversations(
    slug: str,
    status: str | None = None,
    mode: str | None = None,
    search: str | None = None,
    unread: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    # Same shape as the agency inbox: the latest message and the unread count
    # are resolved in SQL, so the list never loads message histories, and the
    # filters run server-side so paging stays consistent with what is shown.
    ranked = (
        select(
            Message.conversation_id.label("cid"),
            Message.content.label("content"),
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
    # Unread is a call to action for a person: the contact wrote and nobody
    # has looked. While the AI answers there is nothing to act on, so those
    # conversations never count as unread; they live under the AI filter.
    unread_count = case(
        (Conversation.mode == "human", func.coalesce(unread_counts.c.n, 0)),
        else_=0,
    )

    query = (
        select(Conversation, last.c.content, unread_count.label("unread_count"))
        .outerjoin(last, last.c.cid == Conversation.id)
        .outerjoin(unread_counts, unread_counts.c.cid == Conversation.id)
        .where(Conversation.client_id == client.id)
    )
    # No status filter means everything, so clients that predate statuses keep
    # seeing their whole list.
    if status in ("open", "resolved"):
        query = query.where(Conversation.status == status)
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
    rows = db.execute(query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)).all()
    return [
        ConversationOut.model_validate(conv).model_copy(
            update={
                "preview": (content or "")[:140].strip(),
                "unread": int(row_unread_count) > 0,
                "unread_count": int(row_unread_count),
            }
        )
        for conv, content, row_unread_count in rows
    ]


@router.post("/{slug}/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def portal_mark_read(
    slug: str,
    conversation_id: uuid.UUID,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.client_id == client.id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.operator_read_at = now_utc()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{slug}/conversations/summary", response_model=PortalInboxSummary)
def portal_inbox_summary(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    """Counts behind the list's switches and chips, computed the same way the
    list is so a badge never promises something the filter does not show."""
    unread_exists = (
        select(Message.id)
        .where(
            Message.conversation_id == Conversation.id,
            Message.sender_type == "visitor",
            or_(Conversation.operator_read_at.is_(None), Message.created_at > Conversation.operator_read_at),
        )
        .exists()
    )
    is_open = Conversation.status == "open"
    row = db.execute(
        select(
            func.count().filter(is_open).label("open"),
            func.count().filter(Conversation.status == "resolved").label("resolved"),
            func.count().filter(is_open, Conversation.mode == "human").label("human"),
            func.count().filter(is_open, Conversation.mode == "ai").label("ai"),
            func.count().filter(is_open, Conversation.mode == "human", unread_exists).label("unread"),
        ).where(Conversation.client_id == client.id)
    ).one()
    return {"open": row.open, "resolved": row.resolved, "human": row.human, "ai": row.ai, "unread": row.unread}


@router.get("/{slug}/conversations/{conversation_id}", response_model=ConversationDetail)
def portal_conversation(slug: str, conversation_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return _detail(db, client, conversation_id)


@router.patch("/{slug}/conversations/{conversation_id}/mode", response_model=ConversationDetail)
def portal_mode(
    slug: str,
    conversation_id: uuid.UUID,
    payload: ConversationModeUpdate,
    client: Client = Depends(_portal_client),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    if set_mode(db, conversation, payload.mode, actor=sender_name):
        db.commit()
    return _detail(db, client, conversation_id)


@router.patch("/{slug}/conversations/{conversation_id}/status", response_model=ConversationDetail)
def portal_status(
    slug: str,
    conversation_id: uuid.UUID,
    payload: ConversationStatusUpdate,
    client: Client = Depends(_portal_client),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    if set_status(db, conversation, payload.status, actor=sender_name):
        db.commit()
    return _detail(db, client, conversation_id)


@router.get("/{slug}/conversations/{conversation_id}/attachments/{attachment_id}")
def portal_attachment(
    slug: str,
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    return attachment_response(conversation_attachment(db, conversation, attachment_id))


@router.post("/{slug}/conversations/{conversation_id}/reply-media", response_model=ConversationDetail)
async def portal_reply_media(
    slug: str,
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    client: Client = Depends(_portal_client),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    await store_operator_media_reply(db, conversation, file=file, caption=caption, sender_name=sender_name)
    return _detail(db, client, conversation_id)


@router.post("/{slug}/conversations/{conversation_id}/reply", response_model=ConversationDetail)
async def portal_reply(
    slug: str,
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    client: Client = Depends(_portal_client),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    external_message_id = await send_channel_message(db, conversation, payload.content.strip())
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=payload.content.strip(),
            sender_type="human",
            sender_name=sender_name,
            external_message_id=external_message_id,
        )
    )
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
    return _detail(db, client, conversation_id)
