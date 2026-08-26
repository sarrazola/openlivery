"""Entry point for the mobile client.

The mobile app talks to the portal API, which is already scoped to a single
client and carries everything the app needs: conversations, replies, human
takeover and branding. Two things the browser portal takes for granted are not
available on a phone, and this module supplies them:

* The portal is addressed by slug, which the app cannot know. A person signing
  in types a server URL, an e-mail and a password, so sign-in resolves the
  client from the credentials alone.
* Sessions live in an httpOnly cookie. The app receives the same token in the
  response body and sends it back as a bearer credential.

Everything else the app calls is the existing portal router.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Agency, Client
from ..ratelimit import login_rate_limit
from ..security import create_portal_token, decode_portal_token, verify_password


router = APIRouter(prefix="/mobile", tags=["Mobile"])

# Kept in the payload so the app can show the server it is talking to and warn
# when it is older than the client expects.
API_VERSION = 1


class MobileSignInRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MobileBranding(BaseModel):
    agency_name: str
    client_name: str
    portal_title: str
    brand_color: str
    agency_logo_url: str | None = None
    client_logo_url: str | None = None


class MobileSession(BaseModel):
    token: str
    portal_slug: str
    client_id: uuid.UUID
    branding: MobileBranding
    api_version: int = API_VERSION


def _branding(client: Client, agency: Agency) -> MobileBranding:
    slug = client.portal_slug
    return MobileBranding(
        agency_name=agency.name,
        client_name=client.name,
        portal_title=client.portal_title or f"{client.name} Inbox",
        brand_color=agency.brand_color or "#075985",
        agency_logo_url=f"/api/portal/{slug}/logo" if agency.logo_data else None,
        client_logo_url=f"/api/portal/{slug}/client-logo" if client.logo_mime else None,
    )


@router.post("/sign-in", response_model=MobileSession, dependencies=[Depends(login_rate_limit)])
def mobile_sign_in(payload: MobileSignInRequest, db: Session = Depends(get_db)):
    """Resolve a portal from its credentials and issue a bearer token.

    The e-mail alone does not identify a portal - nothing stops two clients from
    using the same address - so every candidate is checked against the password
    and the first that verifies wins. The failure response never distinguishes an
    unknown address from a wrong password.
    """
    email = payload.email.lower()
    candidates = db.scalars(
        select(Client).where(Client.portal_enabled.is_(True), Client.portal_email.is_not(None))
    ).all()
    for client in candidates:
        if (client.portal_email or "").lower() != email:
            continue
        if not client.portal_password_hash or not verify_password(payload.password, client.portal_password_hash):
            continue
        agency = db.get(Agency, client.agency_id)
        if not agency:
            continue
        return MobileSession(
            token=create_portal_token(str(client.id), client.portal_slug),
            portal_slug=client.portal_slug,
            client_id=client.id,
            branding=_branding(client, agency),
        )
    raise HTTPException(status_code=401, detail="Incorrect e-mail or password")


@router.get("/session", response_model=MobileSession)
def mobile_session(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Re-validate a stored token on launch and return fresh branding.

    Lets the app skip the sign-in screen when the token is still good, and pick
    up a colour or logo the agency changed since last time.
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    payload = decode_portal_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="The session expired")
    try:
        client_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    client = db.scalar(select(Client).where(Client.id == client_id, Client.portal_enabled.is_(True)))
    if not client or client.portal_slug != payload.get("portal_slug"):
        raise HTTPException(status_code=401, detail="This portal is no longer available")
    agency = db.get(Agency, client.agency_id)
    if not agency:
        raise HTTPException(status_code=401, detail="This portal is no longer available")
    return MobileSession(
        token=token,
        portal_slug=client.portal_slug,
        client_id=client.id,
        branding=_branding(client, agency),
    )
