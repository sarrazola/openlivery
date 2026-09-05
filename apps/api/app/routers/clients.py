import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from .. import industries
from ..models import Client, PortalUser, PushDevice, User, new_domain_token, Team
from ..schemas import (
    ClientCreate,
    ClientDomainOut,
    ClientDomainSet,
    ClientOut,
    ClientPortalUpdate,
    ClientUpdate,
    PortalUserCreate,
    PortalUserOut,
    PortalUserUpdate,
)
from ..security import hash_password
from ..services.attachments import logo_response
from ..services import dns as dns_service
from ..slugs import slugify, unique_slug


router = APIRouter(prefix="/clients", tags=["Clients"])
MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}


def _domain_out(client: Client) -> ClientDomainOut:
    if not client.portal_domain:
        return ClientDomainOut(domain=None, verified=False, txt_host=None, txt_value=None)
    return ClientDomainOut(
        domain=client.portal_domain,
        verified=client.portal_domain_verified,
        txt_host=dns_service.challenge_host(client.portal_domain),
        txt_value=client.portal_domain_token,
    )


def _check_industry(industry: str, business_type: str) -> None:
    error = industries.validate(industry, business_type)
    if error:
        raise HTTPException(status_code=422, detail=error)


def _client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.scalar(
        select(Client)
        .options(selectinload(Client.agents))
        .where(Client.id == client_id, Client.agency_id == user.agency_id)
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(Client)
        .options(selectinload(Client.agents))
        .where(Client.agency_id == user.agency_id)
        .order_by(Client.created_at.desc())
    ).all()


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _check_industry(payload.industry, payload.business_type)
    client = Client(
        agency_id=user.agency_id,
        portal_slug=unique_slug(db, Client, "portal_slug", payload.name),
        **payload.model_dump(),
    )
    db.add(client)
    db.commit()
    return _client(db, user, client.id)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _client(db, user, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: uuid.UUID, payload: ClientUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    values = payload.model_dump(exclude_unset=True)
    industry = values.get("industry", client.industry)
    business_type = values.get("business_type", client.business_type)
    # Changing the industry drops a type that no longer belongs to it.
    if "industry" in values and "business_type" not in values and industries.get_type(industry, business_type) is None:
        values["business_type"] = ""
        business_type = ""
    _check_industry(industry, business_type)
    for key, value in values.items():
        setattr(client, key, value)
    db.commit()
    return _client(db, user, client_id)


@router.post("/{client_id}/logo", response_model=ClientOut)
async def upload_client_logo(
    client_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = _client(db, user, client_id)
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail="Use a PNG, JPG, WebP or SVG logo")
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="The logo exceeds the 2 MB limit")
    client.logo_data = data
    client.logo_mime = file.content_type
    db.commit()
    return _client(db, user, client_id)


@router.get("/{client_id}/logo")
def get_client_logo(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    if not client.logo_data or not client.logo_mime:
        raise HTTPException(status_code=404, detail="This client does not have a logo yet")
    return logo_response(client.logo_data, client.logo_mime)


@router.delete("/{client_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_logo(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    client.logo_data = None
    client.logo_mime = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{client_id}/portal", response_model=ClientOut)
def update_client_portal(
    client_id: uuid.UUID,
    payload: ClientPortalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = _client(db, user, client_id)
    values = payload.model_dump(exclude_unset=True)
    if "portal_slug" in values and values["portal_slug"]:
        candidate = slugify(values["portal_slug"])
        existing = db.scalar(select(Client).where(Client.portal_slug == candidate, Client.id != client.id))
        if existing:
            raise HTTPException(status_code=409, detail="That portal URL is already in use")
        values["portal_slug"] = candidate
    for key, value in values.items():
        setattr(client, key, value)
    has_users = db.scalar(
        select(func.count(PortalUser.id)).where(
            PortalUser.client_id == client.id, PortalUser.is_active.is_(True)
        )
    )
    if client.portal_enabled and not has_users:
        raise HTTPException(status_code=400, detail="Add someone who can sign in before enabling the portal")
    db.commit()
    return _client(db, user, client_id)


@router.get("/{client_id}/domain", response_model=ClientDomainOut)
def get_client_domain(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _domain_out(_client(db, user, client_id))


@router.put("/{client_id}/domain", response_model=ClientDomainOut)
def set_client_domain(
    client_id: uuid.UUID,
    payload: ClientDomainSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = _client(db, user, client_id)
    domain = payload.domain.strip().lower()
    taken = db.scalar(select(Client).where(Client.portal_domain == domain, Client.id != client.id))
    if taken:
        raise HTTPException(status_code=409, detail="That domain is already in use")
    # Re-assigning resets verification and issues a fresh challenge token.
    if client.portal_domain != domain or not client.portal_domain_token:
        client.portal_domain_token = new_domain_token()
    client.portal_domain = domain
    client.portal_domain_verified = False
    db.commit()
    return _domain_out(_client(db, user, client_id))


@router.post("/{client_id}/domain/verify", response_model=ClientDomainOut)
def verify_client_domain(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    if not client.portal_domain:
        raise HTTPException(status_code=400, detail="Add a domain before verifying it")
    if not dns_service.txt_contains(client.portal_domain, client.portal_domain_token):
        raise HTTPException(status_code=400, detail="The verification TXT record was not found yet. DNS can take a while to propagate.")
    client.portal_domain_verified = True
    db.commit()
    return _domain_out(_client(db, user, client_id))


@router.delete("/{client_id}/domain", response_model=ClientDomainOut)
def delete_client_domain(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    client.portal_domain = None
    client.portal_domain_verified = False
    client.portal_domain_token = ""
    db.commit()
    return _domain_out(_client(db, user, client_id))


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = _client(db, user, client_id)
    db.delete(client)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _portal_user(db: Session, user: User, client_id: uuid.UUID, portal_user_id: uuid.UUID) -> PortalUser:
    # Resolving the client first keeps this inside the caller's agency.
    client = _client(db, user, client_id)
    portal_user = db.scalar(
        select(PortalUser).where(PortalUser.id == portal_user_id, PortalUser.client_id == client.id)
    )
    if not portal_user:
        raise HTTPException(status_code=404, detail="That person is not on this portal")
    return portal_user


def _portal_user_out(db: Session, portal_user: PortalUser) -> PortalUserOut:
    devices = db.scalar(
        select(func.count(PushDevice.id)).where(PushDevice.portal_user_id == portal_user.id)
    )
    return PortalUserOut(
        id=portal_user.id,
        email=portal_user.email,
        name=portal_user.name,
        is_active=portal_user.is_active,
        devices=devices or 0,
        created_at=portal_user.created_at,
    )


@router.get("/{client_id}/portal-users", response_model=list[PortalUserOut])
def list_portal_users(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Everyone who can answer for this client."""
    client = _client(db, user, client_id)
    rows = db.scalars(
        select(PortalUser).where(PortalUser.client_id == client.id).order_by(PortalUser.created_at)
    ).all()
    return [_portal_user_out(db, row) for row in rows]


@router.get("/{client_id}/teams")
def client_teams(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The client's trays, for pickers like the escalation rule editor."""
    client = _client(db, user, client_id)
    teams = db.scalars(select(Team).where(Team.client_id == client.id).order_by(Team.name)).all()
    return [{"id": str(team.id), "name": team.name, "is_default": team.is_default} for team in teams]


@router.post("/{client_id}/portal-users", response_model=PortalUserOut, status_code=status.HTTP_201_CREATED)
def create_portal_user(
    client_id: uuid.UUID,
    payload: PortalUserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = _client(db, user, client_id)
    email = payload.email.lower()
    existing = db.scalar(
        select(PortalUser).where(PortalUser.client_id == client.id, PortalUser.email == email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="That e-mail is already on this portal")
    portal_user = PortalUser(
        client_id=client.id,
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(portal_user)
    db.commit()
    db.refresh(portal_user)
    return _portal_user_out(db, portal_user)


@router.patch("/{client_id}/portal-users/{portal_user_id}", response_model=PortalUserOut)
def update_portal_user(
    client_id: uuid.UUID,
    portal_user_id: uuid.UUID,
    payload: PortalUserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    portal_user = _portal_user(db, user, client_id, portal_user_id)
    values = payload.model_dump(exclude_unset=True)
    password = values.pop("password", None)
    if password:
        portal_user.password_hash = hash_password(password)
    if values.get("email"):
        email = str(values["email"]).lower()
        clash = db.scalar(
            select(PortalUser).where(
                PortalUser.client_id == portal_user.client_id,
                PortalUser.email == email,
                PortalUser.id != portal_user.id,
            )
        )
        if clash:
            raise HTTPException(status_code=409, detail="That e-mail is already on this portal")
        values["email"] = email
    if values.get("name") is not None:
        values["name"] = str(values["name"]).strip()
    for key, value in values.items():
        setattr(portal_user, key, value)
    db.commit()
    db.refresh(portal_user)
    return _portal_user_out(db, portal_user)


@router.delete("/{client_id}/portal-users/{portal_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portal_user(
    client_id: uuid.UUID,
    portal_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove someone's access.

    Their registered devices go with them, so a phone that left the business
    stops ringing straight away.
    """
    portal_user = _portal_user(db, user, client_id, portal_user_id)
    db.delete(portal_user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
