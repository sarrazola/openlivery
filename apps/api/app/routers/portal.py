import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Header, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import Interval, and_, case, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import get_settings
from ..database import get_db
from ..models import Agency, Agent, CannedResponse, Client, Contact, Conversation, Message, PortalUser, Team, TeamMember, WhatsAppChannel, WhatsAppCloudChannel, now_utc
from ..ratelimit import login_rate_limit, public_asset_rate_limit
from ..schemas import (
    AgentSummary,
    CannedResponseCreate,
    CannedResponseOut,
    CannedResponseUpdate,
    ContactCreate,
    ContactMergeRequest,
    ContactOut,
    ContactUpdate,
    ConversationStart,
    PortalChannelOut,
    PortalReport,
    ReportAgentRow,
    ReportChannelRow,
    ReportDay,
    TemplateCreate,
    TemplateOut,
    TemplateSend,
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
    PortalAvailabilityUpdate,
    ReactionRequest,
    SendMessageRequest,
    ConversationTeamUpdate,
    TeamOut,
    TeamUpsert,
)
from ..security import create_portal_token, decode_portal_token, verify_password
from ..services.contacts import display_name, merge_contacts, normalize_phone, rename_conversations
from ..services.whatsapp_templates import (
    create_template,
    delete_template,
    list_templates,
    render,
    send_template,
    validate_template_name,
    window_is_open,
    window_open_until,
)
from ..services.conversation_state import record_activity
from ..security import decrypt_secret
from ..services.conversation_state import ConversationClosed, assign, note_reply, set_mode, set_status, set_team
from ..services.routing import route_conversation
from ..services.notifications import notify_assigned
from ..services.attachments import attachment_response, conversation_attachment, logo_response
from ..services.operator_media import store_operator_media_reply
from ..services.whatsapp import deliver_reaction, resolve_quote, send_channel_message, signal_channel_read


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
    if not user or not user.is_active:
        return None
    # A cheap heartbeat: the portal polls every few seconds, so last_seen_at
    # tracks real presence with one write a minute at most.
    now = now_utc()
    if user.last_seen_at is None or (now - user.last_seen_at).total_seconds() > 60:
        user.last_seen_at = now
        db.commit()
    return user


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


def _last_inbound_at(conversation: Conversation):
    stamps = [m.created_at for m in conversation.messages if m.kind == "message" and m.sender_type == "visitor"]
    return max(stamps) if stamps else None


def _window_fields(conversation: Conversation, last_inbound_at) -> dict:
    if conversation.channel != "whatsapp_cloud":
        return {"reply_window_until": None, "reply_window_open": True}
    return {"reply_window_until": window_open_until(last_inbound_at), "reply_window_open": window_is_open(last_inbound_at)}


def _present(conversation: Conversation) -> ConversationDetail:
    assignee = conversation.assignee
    return ConversationDetail.model_validate(conversation).model_copy(
        update={
            "assignee_name": (assignee.name.strip() or assignee.email) if assignee else None,
            "team_name": conversation.team.name if conversation.team else None,
            **_window_fields(conversation, _last_inbound_at(conversation)),
        }
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


_TEAM_CHANNELS = {"whatsapp", "whatsapp_cloud", "widget"}


def _portal_team(db: Session, client: Client, team_id: uuid.UUID) -> Team:
    team = db.scalar(select(Team).where(Team.id == team_id, Team.client_id == client.id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _team_out(db: Session, team: Team) -> dict:
    open_count, unassigned_count = db.execute(
        select(
            func.count(Conversation.id),
            func.count(Conversation.id).filter(Conversation.assignee_id.is_(None)),
        ).where(Conversation.team_id == team.id, Conversation.status == "open")
    ).one()
    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "strategy": team.strategy,
        "channels": list(team.channels or []),
        "is_default": team.is_default,
        "members": [
            {
                "id": member.portal_user.id,
                "name": member.portal_user.name.strip() or member.portal_user.email,
                "email": member.portal_user.email,
                "availability": member.portal_user.availability,
            }
            for member in team.members
            if member.portal_user
        ],
        "open_count": int(open_count),
        "unassigned_count": int(unassigned_count),
    }


def _apply_team_payload(db: Session, client: Client, team: Team, payload: TeamUpsert) -> None:
    if set(payload.channels) - _TEAM_CHANNELS:
        raise HTTPException(status_code=422, detail="Unknown channel for a team")
    duplicate = db.scalar(
        select(Team.id).where(Team.client_id == client.id, Team.name == payload.name.strip(), Team.id != team.id)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    team.name = payload.name.strip()
    team.description = payload.description.strip()
    team.strategy = payload.strategy
    team.channels = sorted(set(payload.channels))
    if payload.is_default and not team.is_default:
        for other in db.scalars(select(Team).where(Team.client_id == client.id, Team.is_default.is_(True))):
            other.is_default = False
    team.is_default = payload.is_default
    team.updated_at = now_utc()

    wanted = set(payload.member_ids)
    if wanted:
        users = db.scalars(
            select(PortalUser).where(PortalUser.client_id == client.id, PortalUser.id.in_(wanted))
        ).all()
        if len(users) != len(wanted):
            raise HTTPException(status_code=422, detail="Every member must be a portal user of this client")
    existing = {member.portal_user_id: member for member in team.members}
    for portal_user_id, member in existing.items():
        if portal_user_id not in wanted:
            db.delete(member)
    for portal_user_id in wanted - set(existing):
        db.add(TeamMember(team_id=team.id, portal_user_id=portal_user_id))


@router.get("/{slug}/teams", response_model=list[TeamOut])
def portal_teams(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    teams = db.scalars(select(Team).where(Team.client_id == client.id).order_by(Team.name)).all()
    return [_team_out(db, team) for team in teams]


@router.post("/{slug}/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def portal_create_team(
    slug: str, payload: TeamUpsert, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    # Checked before the row exists so a duplicate is a clean 409, not a
    # constraint blowup at flush time.
    if db.scalar(select(Team.id).where(Team.client_id == client.id, Team.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    team = Team(client_id=client.id, name=payload.name.strip())
    db.add(team)
    db.flush()
    _apply_team_payload(db, client, team, payload)
    db.commit()
    db.refresh(team)
    return _team_out(db, team)


@router.patch("/{slug}/teams/{team_id}", response_model=TeamOut)
def portal_update_team(
    slug: str,
    team_id: uuid.UUID,
    payload: TeamUpsert,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    team = _portal_team(db, client, team_id)
    _apply_team_payload(db, client, team, payload)
    db.commit()
    db.refresh(team)
    return _team_out(db, team)


@router.delete("/{slug}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def portal_delete_team(
    slug: str, team_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    # Conversations keep living; the FK sets their tray to NULL.
    team = _portal_team(db, client, team_id)
    db.delete(team)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{slug}/me", response_model=PortalMemberOut)
def portal_update_availability(
    slug: str,
    payload: PortalAvailabilityUpdate,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    db: Session = Depends(get_db),
):
    if not user or user.client_id != client.id:
        raise HTTPException(status_code=401, detail="Sign in with your own user to change availability")
    user.availability = payload.availability
    db.commit()
    return {
        "id": user.id,
        "name": user.name.strip() or user.email,
        "email": user.email,
        "availability": user.availability,
    }


@router.get("/{slug}/agents", response_model=list[AgentSummary])
def portal_agents(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return db.scalars(select(Agent).where(Agent.client_id == client.id).order_by(Agent.name)).all()


@router.get("/{slug}/conversations", response_model=list[ConversationOut])
def portal_conversations(
    slug: str,
    status: str | None = None,
    mode: str | None = None,
    assignee: str | None = None,
    team: uuid.UUID | None = None,
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

    last_inbound = (
        select(Message.conversation_id.label("cid"), func.max(Message.created_at).label("at"))
        .where(Message.kind == "message", Message.sender_type == "visitor")
        .group_by(Message.conversation_id)
        .subquery()
    )
    query = (
        select(Conversation, last.c.content, unread_count.label("unread_count"), PortalUser.name.label("assignee_name"), PortalUser.email.label("assignee_email"), last_inbound.c.at.label("last_inbound_at"), Team.name.label("team_name"))
        .outerjoin(last, last.c.cid == Conversation.id)
        .outerjoin(unread_counts, unread_counts.c.cid == Conversation.id)
        .outerjoin(PortalUser, PortalUser.id == Conversation.assignee_id)
        .outerjoin(last_inbound, last_inbound.c.cid == Conversation.id)
        .outerjoin(Team, Team.id == Conversation.team_id)
        .where(Conversation.client_id == client.id)
    )
    if team is not None:
        query = query.where(Conversation.team_id == team)
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
    # A conversation moves up only when the contact writes. Reading it,
    # replying, assigning or resolving all touch updated_at, and none of them
    # should reshuffle the list under the person working it.
    rows = db.execute(
        query.order_by(func.coalesce(last_inbound.c.at, Conversation.created_at).desc(), Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        ConversationOut.model_validate(conv).model_copy(
            update={
                "preview": (content or "")[:140].strip(),
                "unread": int(row_unread_count) > 0,
                "unread_count": int(row_unread_count),
                "assignee_name": ((assignee_name or "").strip() or assignee_email) if conv.assignee_id else None,
                "last_inbound_at": last_inbound_at,
                "team_name": team_name,
                **_window_fields(conv, last_inbound_at),
            }
        )
        for conv, content, row_unread_count, assignee_name, assignee_email, last_inbound_at, team_name in rows
    ]


@router.post("/{slug}/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def portal_mark_read(
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


@router.post("/{slug}/contacts/{contact_id}/merge", response_model=ContactOut)
def portal_merge_contact(
    slug: str,
    contact_id: uuid.UUID,
    payload: ContactMergeRequest,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    """Fold the addressed contact into the primary one; the addressed contact
    is deleted and its conversations move over."""
    merged = _portal_contact(db, client, contact_id)
    if payload.primary_contact_id == merged.id:
        raise HTTPException(status_code=409, detail="Pick a different contact to merge into")
    primary = _portal_contact(db, client, payload.primary_contact_id)
    merge_contacts(db, primary, merged)
    db.commit()
    db.refresh(primary)
    stats = _contact_stats()
    row = db.execute(select(stats).where(stats.c.cid == primary.id)).first()
    return _contact_out(primary, row)


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


WINDOW_CLOSED = "The 24-hour reply window is closed. Send an approved template to reach this person."


def _require_open_window(conversation: Conversation) -> None:
    if conversation.channel == "whatsapp_cloud" and not window_is_open(_last_inbound_at(conversation)):
        raise HTTPException(status_code=409, detail=WINDOW_CLOSED)


def _cloud_channel(db: Session, client: Client) -> WhatsAppCloudChannel | None:
    return db.scalar(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.client_id == client.id))


def _qr_channel(db: Session, client: Client) -> WhatsAppChannel | None:
    return db.scalar(select(WhatsAppChannel).where(WhatsAppChannel.client_id == client.id))


def _template_credentials(channel: WhatsAppCloudChannel | None) -> tuple[str, str]:
    if not channel or not channel.encrypted_access_token or not channel.waba_id:
        raise HTTPException(
            status_code=409,
            detail="Templates need the WhatsApp API channel with its access token and WhatsApp Business account id",
        )
    return decrypt_secret(channel.encrypted_access_token), channel.waba_id


@router.get("/{slug}/channels", response_model=list[PortalChannelOut])
def portal_channels(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    """Which WhatsApp lines this business has, so the portal knows how it can
    reach a contact first."""
    out = []
    cloud = _cloud_channel(db, client)
    if cloud and cloud.is_enabled:
        out.append({
            "channel": "whatsapp_cloud", "status": cloud.status, "phone_number": cloud.phone_number,
            "display_name": cloud.display_name, "supports_templates": bool(cloud.encrypted_access_token and cloud.waba_id),
        })
    qr = _qr_channel(db, client)
    if qr and qr.is_enabled:
        out.append({"channel": "whatsapp", "status": qr.status, "phone_number": qr.phone_number, "display_name": qr.display_name})
    return out


@router.get("/{slug}/templates", response_model=list[TemplateOut])
async def portal_templates(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    token, waba_id = _template_credentials(_cloud_channel(db, client))
    return await list_templates(token, waba_id)


@router.post("/{slug}/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def portal_create_template(
    slug: str, payload: TemplateCreate, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    token, waba_id = _template_credentials(_cloud_channel(db, client))
    return await create_template(
        token,
        waba_id,
        name=validate_template_name(payload.name),
        language=payload.language.strip(),
        category=payload.category,
        body=payload.body.strip(),
        footer=payload.footer,
        examples=payload.examples,
    )


@router.delete("/{slug}/templates/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def portal_delete_template(
    slug: str,
    name: str,
    hsm_id: str | None = Query(default=None, max_length=64),
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    """Remove a template from the business account. Meta offers no way to
    disable one, so deletion is how a template is retired."""
    token, waba_id = _template_credentials(_cloud_channel(db, client))
    await delete_template(token, waba_id, name=validate_template_name(name), hsm_id=hsm_id)


def _canned_response(db: Session, client: Client, canned_id: uuid.UUID) -> CannedResponse:
    canned = db.scalar(
        select(CannedResponse).where(CannedResponse.id == canned_id, CannedResponse.client_id == client.id)
    )
    if not canned:
        raise HTTPException(status_code=404, detail="Saved reply not found")
    return canned


def _require_free_shortcut(db: Session, client: Client, shortcut: str, but: uuid.UUID | None = None) -> None:
    clash = db.scalar(
        select(CannedResponse).where(
            CannedResponse.client_id == client.id, CannedResponse.shortcut == shortcut, CannedResponse.id != but
        )
    )
    if clash:
        raise HTTPException(status_code=409, detail="A saved reply already uses that shortcut")


@router.get("/{slug}/canned-responses", response_model=list[CannedResponseOut])
def portal_canned_responses(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    """The saved replies the composer offers when the operator types a slash."""
    return db.scalars(
        select(CannedResponse).where(CannedResponse.client_id == client.id).order_by(CannedResponse.shortcut)
    ).all()


@router.post("/{slug}/canned-responses", response_model=CannedResponseOut, status_code=status.HTTP_201_CREATED)
def portal_create_canned_response(
    slug: str, payload: CannedResponseCreate, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    _require_free_shortcut(db, client, payload.shortcut)
    canned = CannedResponse(client_id=client.id, shortcut=payload.shortcut, content=payload.content.strip())
    db.add(canned)
    db.commit()
    db.refresh(canned)
    return canned


@router.patch("/{slug}/canned-responses/{canned_id}", response_model=CannedResponseOut)
def portal_update_canned_response(
    slug: str,
    canned_id: uuid.UUID,
    payload: CannedResponseUpdate,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    canned = _canned_response(db, client, canned_id)
    if payload.shortcut is not None:
        _require_free_shortcut(db, client, payload.shortcut, but=canned.id)
        canned.shortcut = payload.shortcut
    if payload.content is not None:
        canned.content = payload.content.strip()
    db.commit()
    db.refresh(canned)
    return canned


@router.delete("/{slug}/canned-responses/{canned_id}", status_code=status.HTTP_204_NO_CONTENT)
def portal_delete_canned_response(
    slug: str, canned_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)
):
    db.delete(_canned_response(db, client, canned_id))
    db.commit()


@router.get("/{slug}/reports", response_model=PortalReport)
def portal_report(
    slug: str,
    from_: date = Query(alias="from"),
    to: date = Query(),
    tz_offset: int = Query(default=0, ge=-840, le=840),
    channel: str | None = Query(default=None, max_length=40),
    assignee_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    """Basic activity metrics over a local-day range. ``tz_offset`` is the
    viewer's UTC offset in minutes as JavaScript reports it (positive west),
    so days group the way the operator's clock reads them. ``channel``,
    ``assignee_id`` and ``team_id`` narrow every conversation-based number."""
    if to < from_ or (to - from_).days > 366:
        raise HTTPException(status_code=422, detail="Pick a range of at most a year, oldest day first")
    shift = timedelta(minutes=tz_offset)
    start = datetime.combine(from_, time.min, tzinfo=timezone.utc) + shift
    end = datetime.combine(to, time.min, tzinfo=timezone.utc) + shift + timedelta(days=1)
    conv_filters = [Conversation.client_id == client.id]
    if channel:
        conv_filters.append(Conversation.channel == channel)
    if assignee_id:
        conv_filters.append(Conversation.assignee_id == assignee_id)
    if team_id:
        conv_filters.append(Conversation.team_id == team_id)

    def local_day(column):
        return func.date(column - literal(shift, Interval))

    started_day = local_day(Conversation.created_at)
    started_rows = db.execute(
        select(started_day, func.count())
        .where(*conv_filters, Conversation.created_at >= start, Conversation.created_at < end)
        .group_by(started_day)
    ).all()
    resolved_day = local_day(Conversation.resolved_at)
    resolved_rows = db.execute(
        select(resolved_day, func.count())
        .where(*conv_filters, Conversation.resolved_at >= start, Conversation.resolved_at < end)
        .group_by(resolved_day)
    ).all()
    days = {from_ + timedelta(days=i): ReportDay(date=from_ + timedelta(days=i)) for i in range((to - from_).days + 1)}
    for day, count in started_rows:
        if day in days:
            days[day].started = count
    for day, count in resolved_rows:
        if day in days:
            days[day].resolved = count

    channel_rows = db.execute(
        select(Conversation.channel, func.count())
        .where(*conv_filters, Conversation.created_at >= start, Conversation.created_at < end)
        .group_by(Conversation.channel)
        .order_by(func.count().desc())
    ).all()

    human_reply = and_(Message.role == "assistant", Message.sender_type == "human")
    inbound, human_replies, ai_replies = db.execute(
        select(
            func.count().filter(Message.role == "user"),
            func.count().filter(human_reply),
            func.count().filter(Message.role == "assistant", Message.sender_type != "human"),
        )
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            *conv_filters,
            Message.kind == "message",
            Message.created_at >= start,
            Message.created_at < end,
        )
    ).one()

    active_contacts = db.scalar(
        select(func.count(func.distinct(Conversation.contact_id))).where(
            *conv_filters,
            Conversation.contact_id.is_not(None),
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
    )
    open_now = db.scalar(
        select(func.count()).select_from(Conversation).where(*conv_filters, Conversation.status != "resolved")
    )
    avg_first_reply = db.scalar(
        select(func.avg(func.extract("epoch", Conversation.first_reply_at - Conversation.created_at))).where(
            *conv_filters,
            Conversation.first_reply_at.is_not(None),
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
    )
    avg_resolution = db.scalar(
        select(func.avg(func.extract("epoch", Conversation.resolved_at - Conversation.created_at))).where(
            *conv_filters,
            Conversation.resolved_at >= start,
            Conversation.resolved_at < end,
        )
    )

    users = db.execute(
        select(PortalUser.id, PortalUser.name, PortalUser.availability).where(PortalUser.client_id == client.id)
    ).all()
    replies_by_user = dict(
        db.execute(
            select(Message.portal_user_id, func.count())
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                *conv_filters,
                Message.kind == "message",
                human_reply,
                Message.portal_user_id.is_not(None),
                Message.created_at >= start,
                Message.created_at < end,
            )
            .group_by(Message.portal_user_id)
        ).all()
    )
    assigned_by_user = dict(
        db.execute(
            select(Conversation.assignee_id, func.count())
            .where(
                *conv_filters,
                Conversation.assignee_id.is_not(None),
                Conversation.assigned_at >= start,
                Conversation.assigned_at < end,
            )
            .group_by(Conversation.assignee_id)
        ).all()
    )
    open_by_user = dict(
        db.execute(
            select(Conversation.assignee_id, func.count())
            .where(
                *conv_filters,
                Conversation.assignee_id.is_not(None),
                Conversation.status != "resolved",
            )
            .group_by(Conversation.assignee_id)
        ).all()
    )
    agents = sorted(
        (
            ReportAgentRow(
                name=name or "",
                availability=availability,
                replies=replies_by_user.get(user_id, 0),
                assigned=assigned_by_user.get(user_id, 0),
                open_now=open_by_user.get(user_id, 0),
            )
            for user_id, name, availability in users
            if not assignee_id or user_id == assignee_id
        ),
        key=lambda row: (-row.replies, -row.assigned, row.name),
    )

    return PortalReport(
        started=sum(d.started for d in days.values()),
        resolved=sum(d.resolved for d in days.values()),
        open_now=open_now or 0,
        inbound_messages=inbound,
        human_replies=human_replies,
        ai_replies=ai_replies,
        active_contacts=active_contacts or 0,
        agents_online=sum(1 for _, _, availability in users if availability == "online"),
        avg_first_reply_seconds=float(avg_first_reply) if avg_first_reply is not None else None,
        avg_resolution_seconds=float(avg_resolution) if avg_resolution is not None else None,
        by_day=list(days.values()),
        by_channel=[ReportChannelRow(channel=channel, started=count) for channel, count in channel_rows],
        by_agent=agents,
    )


async def _send_template_to(db: Session, client: Client, to: str, payload: TemplateSend) -> tuple[str | None, str]:
    """Send the template and return (external id, text as the person reads it)."""
    channel = _cloud_channel(db, client)
    token, waba_id = _template_credentials(channel)
    approved = next(
        (t for t in await list_templates(token, waba_id)
         if t["name"] == payload.name and t["language"] == payload.language and t["status"] == "APPROVED"),
        None,
    )
    if not approved:
        raise HTTPException(status_code=409, detail="That template is not approved for this language")
    if len(payload.variables) != approved["variables"]:
        raise HTTPException(status_code=422, detail=f"This template takes {approved['variables']} values")
    external_id = await send_template(
        token, channel.phone_number_id, to, name=payload.name, language=payload.language, variables=payload.variables
    )
    text = render(approved["body"], payload.variables)
    if approved["footer"]:
        text = f"{text}\n\n{approved['footer']}"
    return external_id, text


@router.post("/{slug}/contacts/{contact_id}/conversations", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def portal_start_conversation(
    slug: str,
    contact_id: uuid.UUID,
    payload: ConversationStart,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    """Write to a contact first. On the Cloud API that means an approved
    template; on the QR line any text goes. The new conversation is the
    sender's, so the AI does not answer when the person replies."""
    contact = _portal_contact(db, client, contact_id)
    if not contact.phone:
        raise HTTPException(status_code=409, detail="This contact has no phone number")
    cloud, qr = _cloud_channel(db, client), _qr_channel(db, client)
    channel_name = payload.channel or ("whatsapp_cloud" if cloud and cloud.is_enabled else "whatsapp" if qr and qr.is_enabled else None)
    if channel_name == "whatsapp_cloud" and cloud and cloud.is_enabled:
        if not payload.template:
            raise HTTPException(status_code=422, detail="Starting a conversation on the WhatsApp API takes an approved template")
        fk_field, channel_row, external_chat_id = "whatsapp_cloud_channel_id", cloud, contact.phone
    elif channel_name == "whatsapp" and qr and qr.is_enabled:
        if not (payload.text or "").strip():
            raise HTTPException(status_code=422, detail="Write the message to send")
        fk_field, channel_row, external_chat_id = "whatsapp_channel_id", qr, f"{contact.phone}@s.whatsapp.net"
    else:
        raise HTTPException(status_code=409, detail="This business has no WhatsApp line to send from")

    fk_column = getattr(Conversation, fk_field)
    existing = db.scalar(
        select(Conversation).where(
            fk_column == channel_row.id, Conversation.external_chat_id == external_chat_id, Conversation.status != "resolved"
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="This contact already has an open conversation on that line")

    now = now_utc()
    conversation = Conversation(
        agency_id=channel_row.agency_id,
        client_id=client.id,
        agent_id=channel_row.agent_id,
        channel=channel_name,
        external_chat_id=external_chat_id,
        contact_id=contact.id,
        contact_name=contact.name or None,
        title=display_name(contact)[:240],
        mode="human",
        taken_over_at=now,
        assignee_id=user.id if user else None,
        assigned_at=now if user else None,
        **{fk_field: channel_row.id},
    )
    db.add(conversation)
    db.flush()

    if channel_name == "whatsapp_cloud":
        external_message_id, text = await _send_template_to(db, client, contact.phone, payload.template)
    else:
        text = payload.text.strip()
        external_message_id = await send_channel_message(db, conversation, text)
    record_activity(db, conversation, "started", actor=sender_name)
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=text,
            sender_type="human",
            sender_name=sender_name,
            portal_user_id=user.id if user else None,
            external_message_id=external_message_id,
        )
    )
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
    return _present(_detail(db, client, conversation.id))


@router.post("/{slug}/conversations/{conversation_id}/reply-template", response_model=ConversationDetail)
async def portal_reply_template(
    slug: str,
    conversation_id: uuid.UUID,
    payload: TemplateSend,
    client: Client = Depends(_portal_client),
    user: PortalUser | None = Depends(_portal_user),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    """Reach a person again after the window closed."""
    conversation = _detail(db, client, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    if conversation.channel != "whatsapp_cloud" or not conversation.external_chat_id:
        raise HTTPException(status_code=409, detail="Templates only exist on the WhatsApp API line")
    external_message_id, text = await _send_template_to(db, client, conversation.external_chat_id, payload)
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=text,
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


@router.patch("/{slug}/conversations/{conversation_id}/team", response_model=ConversationDetail)
async def portal_set_conversation_team(
    slug: str,
    conversation_id: uuid.UUID,
    payload: ConversationTeamUpdate,
    client: Client = Depends(_portal_client),
    sender_name: str = Depends(_sender_name),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
    team = _portal_team(db, client, payload.team_id) if payload.team_id else None
    try:
        changed = set_team(db, conversation, team, actor=sender_name)
    except ConversationClosed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    routed = None
    if changed and team and conversation.mode == "human" and conversation.assignee_id is None:
        routed = route_conversation(db, conversation, actor=sender_name)
    db.commit()
    if routed:
        await notify_assigned(db, conversation, routed, sender_name)
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
    if not payload.assignee_id:
        # A conversation is either the AI's or a person's. To let go of it,
        # hand it back to the AI rather than leaving it without an owner.
        raise HTTPException(status_code=422, detail="Choose a person, or return the conversation to the AI")
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
    _require_open_window(conversation)
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
    _require_open_window(conversation)
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
            sender_name=sender_name,
            portal_user_id=user.id if user else None,
            external_message_id=external_message_id,
            quoted_message_id=quoted_id,
        )
    )
    note_reply(conversation)
    conversation.updated_at = now_utc()
    db.commit()
    return _present(_detail(db, client, conversation_id))


@router.post(
    "/{slug}/conversations/{conversation_id}/messages/{message_id}/reaction", response_model=ConversationDetail
)
async def portal_react(
    slug: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ReactionRequest,
    client: Client = Depends(_portal_client),
    db: Session = Depends(get_db),
):
    conversation = _detail(db, client, conversation_id)
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
    return _present(_detail(db, client, conversation_id))
