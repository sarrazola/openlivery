import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Client, User, new_domain_token
from ..schemas import ClientCreate, ClientDomainOut, ClientDomainSet, ClientOut, ClientPortalUpdate, ClientUpdate
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
    for key, value in payload.model_dump(exclude_unset=True).items():
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
    password = values.pop("portal_password", None)
    if password:
        client.portal_password_hash = hash_password(password)
    if "portal_email" in values and values["portal_email"]:
        values["portal_email"] = str(values["portal_email"]).lower()
    if "portal_slug" in values and values["portal_slug"]:
        candidate = slugify(values["portal_slug"])
        existing = db.scalar(select(Client).where(Client.portal_slug == candidate, Client.id != client.id))
        if existing:
            raise HTTPException(status_code=409, detail="That portal URL is already in use")
        values["portal_slug"] = candidate
    for key, value in values.items():
        setattr(client, key, value)
    if client.portal_enabled and (not client.portal_email or not client.portal_password_hash):
        raise HTTPException(status_code=400, detail="Set an email and a password before enabling the portal")
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
