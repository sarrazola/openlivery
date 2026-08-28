import uuid

from fastapi import APIRouter, Cookie, Depends, Header, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import get_settings
from ..database import get_db
from ..models import Agency, Agent, Client, Contact, Conversation, Message, PortalUser, now_utc
from ..ratelimit import login_rate_limit, public_asset_rate_limit
from ..schemas import (
    AgentSummary,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    ConversationDetail,
    ConversationAssignmentUpdate,
    ConversationModeUpdate,
    ConversationStatusUpdate,
    ConversationOut,
    PortalInboxSummary,
    PortalLoginRequest,
    PortalMemberOut,
    PortalPublicOut,
    PortalSessionOut,
    SendMessageRequest,
)
from ..security import create_portal_token, decode_portal_token, verify_password
from ..services.contacts import display_name, normalize_phone, rename_conversations
from ..services.conversation_state import ConversationClosed, assign, note_reply, set_mode, set_status
from ..services.notifications import notify_assigned
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


def _present(conversation: Conversation) -> ConversationDetail:
    assignee = conversation.assignee
    return ConversationDetail.model_validate(conversation).model_copy(
        update={"assignee_name": (assignee.name.strip() or assignee.email) if assignee else None}
    )


def _detail(db: Session, client: Client, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages).selectinload(Message.attachments), joinedload(Conversation.agent), joinedload(Conversation.assignee))
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
    return {
        "client_id": client.id,
        "client_name": client.name,
        "portal_slug": client.portal_slug,
        "agency_name": agency.name,
        "user_id": portal_user.id,
        "user_name": portal_user.name.strip() or portal_user.email,
    }


@router.post("/{slug}/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(response: Response):
    response.delete_cookie("portal_access_token", path="/")


@router.get("/{slug}/me", response_model=PortalSessionOut)
def portal_me(
    slug: str,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    db: Session = Depends(get_db),
):
    agency = db.get(Agency, client.agency_id)
    return {
        "client_id": client.id,
        "client_name": client.name,
        "portal_slug": client.portal_slug,
        "agency_name": agency.name,
        "user_id": user.id if user else None,
        "user_name": (user.name.strip() or user.email) if user else None,
    }


@router.get("/{slug}/members", response_model=list[PortalMemberOut])
def portal_members(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    """The people a conversation can be handed to."""
    rows = db.scalars(
        select(PortalUser).where(PortalUser.client_id == client.id, PortalUser.is_active.is_(True)).order_by(PortalUser.name, PortalUser.email)
    ).all()
    return [{"id": row.id, "name": row.name.strip() or row.email, "email": row.email} for row in rows]


@router.get("/{slug}/agents", response_model=list[AgentSummary])
def portal_agents(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return db.scalars(select(Agent).where(Agent.client_id == client.id).order_by(Agent.name)).all()


@router.get("/{slug}/conversations", response_model=list[ConversationOut])
def portal_conversations(
    slug: str,
    status: str | None = None,
    mode: str | None = None,
    assignee: str | None = None,
    search: str | None = None,
    unread: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
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
    # has looked. While the AI answers there is nothing to act on, and a
    # conversation a colleague holds is theirs to catch up on, so unread only
    # counts what is mine or nobody's.
    concerns_me = or_(Conversation.assignee_id.is_(None), Conversation.assignee_id == (user.id if user else None))
    unread_count = case(
        (and_(Conversation.mode == "human", concerns_me), func.coalesce(unread_counts.c.n, 0)),
        else_=0,
    )

    query = (
        select(Conversation, last.c.content, unread_count.label("unread_count"), PortalUser.name.label("assignee_name"), PortalUser.email.label("assignee_email"))
        .outerjoin(last, last.c.cid == Conversation.id)
        .outerjoin(unread_counts, unread_counts.c.cid == Conversation.id)
        .outerjoin(PortalUser, PortalUser.id == Conversation.assignee_id)
        .where(Conversation.client_id == client.id)
    )
    if assignee == "me" and user:
        query = query.where(Conversation.assignee_id == user.id)
    elif assignee == "none":
        query = query.where(Conversation.mode == "human", Conversation.assignee_id.is_(None))
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
                "assignee_name": ((assignee_name or "").strip() or assignee_email) if conv.assignee_id else None,
            }
        )
        for conv, content, row_unread_count, assignee_name, assignee_email in rows
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


def _contact_stats():
    per_contact = (
        select(
            Conversation.contact_id.label("cid"),
            func.count(Conversation.id).label("total"),
            func.count(Conversation.id).filter(Conversation.status == "open").label("open"),
            func.max(Conversation.updated_at).label("last_activity_at"),
        )
        .where(Conversation.contact_id.is_not(None))
        .group_by(Conversation.contact_id)
        .subquery()
    )
    return per_contact


def _contact_out(contact: Contact, stats) -> ContactOut:
    # Built by hand: the ORM object's ``conversations`` is the relationship,
    # not the count the portal wants.
    return ContactOut(
        id=contact.id,
        name=contact.name,
        phone=contact.phone,
        email=contact.email,
        notes=contact.notes,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        conversation_count=int((stats.total if stats is not None else None) or 0),
        open_count=int((stats.open if stats is not None else None) or 0),
        last_activity_at=stats.last_activity_at if stats is not None else None,
    )


def _portal_contact(db: Session, client: Client, contact_id: uuid.UUID) -> Contact:
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.client_id == client.id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


def _assert_phone_free(db: Session, client: Client, phone: str, *, except_id: uuid.UUID | None = None) -> None:
    query = select(Contact.id).where(Contact.client_id == client.id, Contact.phone == phone)
    if except_id:
        query = query.where(Contact.id != except_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="A contact with this phone number already exists")


@router.get("/{slug}/contacts", response_model=list[ContactOut])
def portal_contacts(
    slug: str,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    stats = _contact_stats()
    query = select(Contact, stats).outerjoin(stats, stats.c.cid == Contact.id).where(Contact.client_id == client.id)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Contact.name).like(term),
                func.coalesce(Contact.phone, "").like(term),
                func.lower(func.coalesce(Contact.email, "")).like(term),
            )
        )
    rows = db.execute(
        query.order_by(func.coalesce(stats.c.last_activity_at, Contact.updated_at).desc()).limit(limit).offset(offset)
    ).all()
    return [_contact_out(row[0], row) for row in rows]


@router.post("/{slug}/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def portal_create_contact(
    slug: str, payload: ContactCreate, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Enter a phone number with its country code")
    _assert_phone_free(db, client, phone)
    contact = Contact(
        client_id=client.id,
        name=payload.name.strip(),
        phone=phone,
        email=(payload.email or None),
        notes=payload.notes.strip(),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _contact_out(contact, None)


@router.get("/{slug}/contacts/{contact_id}", response_model=ContactOut)
def portal_contact(slug: str, contact_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    contact = _portal_contact(db, client, contact_id)
    stats = _contact_stats()
    row = db.execute(select(stats).where(stats.c.cid == contact.id)).first()
    return _contact_out(contact, row)


@router.patch("/{slug}/contacts/{contact_id}", response_model=ContactOut)
def portal_update_contact(
    slug: str,
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    contact = _portal_contact(db, client, contact_id)
    if payload.phone is not None:
        phone = normalize_phone(payload.phone)
        if not phone:
            raise HTTPException(status_code=422, detail="Enter a phone number with its country code")
        _assert_phone_free(db, client, phone, except_id=contact.id)
        contact.phone = phone
    if payload.name is not None:
        contact.name = payload.name.strip()
    if "email" in payload.model_fields_set:
        contact.email = payload.email or None
    if payload.notes is not None:
        contact.notes = payload.notes.strip()
    contact.updated_at = now_utc()
    rename_conversations(db, contact)
    db.commit()
    db.refresh(contact)
    stats = _contact_stats()
    row = db.execute(select(stats).where(stats.c.cid == contact.id)).first()
    return _contact_out(contact, row)


@router.delete("/{slug}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def portal_delete_contact(
    slug: str, contact_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    # Everything about the person goes with them: their conversations (and
    # with those, the messages and attachments). The portal asks the person
    # to type the contact's name before it calls this.
    contact = _portal_contact(db, client, contact_id)
    for conversation in db.scalars(select(Conversation).where(Conversation.contact_id == contact.id)).all():
        db.delete(conversation)
    db.delete(contact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{slug}/contacts/{contact_id}/conversations", response_model=list[ConversationOut])
def portal_contact_conversations(
    slug: str, contact_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    contact = _portal_contact(db, client, contact_id)
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
    rows = db.execute(
        select(Conversation, last.c.content)
        .outerjoin(last, last.c.cid == Conversation.id)
        .where(Conversation.contact_id == contact.id)
        .order_by(Conversation.created_at.desc())
    ).all()
    return [
        ConversationOut.model_validate(conv).model_copy(update={"preview": (content or "")[:140].strip()})
        for conv, content in rows
    ]


@router.get("/{slug}/conversations/summary", response_model=PortalInboxSummary)
def portal_inbox_summary(
    slug: str,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    db: Session = Depends(get_db),
):
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
    is_human = Conversation.mode == "human"
    is_mine = Conversation.assignee_id == (user.id if user else None)
    concerns_me = or_(Conversation.assignee_id.is_(None), is_mine)
    row = db.execute(
        select(
            func.count().filter(is_open).label("open"),
            func.count().filter(Conversation.status == "resolved").label("resolved"),
            func.count().filter(is_open, is_human).label("human"),
            func.count().filter(is_open, Conversation.mode == "ai").label("ai"),
            func.count().filter(is_open, is_human, concerns_me, unread_exists).label("unread"),
            func.count().filter(is_open, is_mine).label("mine"),
            func.count().filter(is_open, is_human, Conversation.assignee_id.is_(None)).label("unassigned"),
        ).where(Conversation.client_id == client.id)
    ).one()
    return {
        "open": row.open, "resolved": row.resolved, "human": row.human, "ai": row.ai,
        "unread": row.unread, "mine": row.mine, "unassigned": row.unassigned,
    }


@router.get("/{slug}/conversations/{conversation_id}", response_model=ConversationDetail)
def portal_conversation(slug: str, conversation_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return _present(_detail(db, client, conversation_id))


@router.patch("/{slug}/conversations/{conversation_id}/mode", response_model=ConversationDetail)
def portal_mode(
    slug: str,
    conversation_id: uuid.UUID,
    payload: ConversationModeUpdate,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    try:
        changed = set_mode(db, conversation, payload.mode, actor=sender_name, user=user)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if changed:
        db.commit()
    return _present(_detail(db, client, conversation_id))


@router.post("/{slug}/conversations/{conversation_id}/assignment", response_model=ConversationDetail)
async def portal_assign(
    slug: str,
    conversation_id: uuid.UUID,
    payload: ConversationAssignmentUpdate,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    assignee = None
    if payload.assignee_id:
        assignee = db.scalar(
            select(PortalUser).where(
                PortalUser.id == payload.assignee_id, PortalUser.client_id == client.id, PortalUser.is_active.is_(True)
            )
        )
        if not assignee:
            raise HTTPException(status_code=404, detail="That person is not part of this portal")
    try:
        changed = assign(db, conversation, assignee, actor=sender_name, actor_user=user)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if changed:
        db.commit()
        if assignee and (not user or assignee.id != user.id):
            await notify_assigned(db, conversation, assignee, sender_name)
    return _present(_detail(db, client, conversation_id))


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
    try:
        changed = set_status(db, conversation, payload.status, actor=sender_name)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if changed:
        db.commit()
    return _present(_detail(db, client, conversation_id))


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
    user: PortalUser | None = Depends(_portal_user),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    await store_operator_media_reply(
        db, conversation, file=file, caption=caption, sender_name=sender_name, portal_user_id=user.id if user else None
    )
    return _present(_detail(db, client, conversation_id))


@router.post("/{slug}/conversations/{conversation_id}/reply", response_model=ConversationDetail)
async def portal_reply(
    slug: str,
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
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
            portal_user_id=user.id if user else None,
            external_message_id=external_message_id,
        )
    )
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
    return _present(_detail(db, client, conversation_id))
