"""Entry point for the mobile client.

The app talks to the portal API, which is already scoped to one client and
carries conversations, replies, takeover and branding. What a phone needs and a
browser does not lives here:

* The portal is addressed by slug, which nobody types. Signing in resolves the
  portal from the credentials alone.
* Sessions live in an httpOnly cookie, which a native client cannot rely on
  across restarts. The same token comes back in the body and is sent as a bearer
  credential.
* A device has to say where to reach it before it can be notified, and has
  to be told whether this server can notify it at all.

Sign-in checks portal users first and falls back to the single login a client
used to have, so an install that never created a user keeps working.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Agency, Client, PortalUser, PushDevice, now_utc
from ..ratelimit import login_rate_limit
from ..services.notifications import configured_provider, push_enabled
from ..security import create_portal_token, decode_portal_token, verify_password


router = APIRouter(prefix="/mobile", tags=["Mobile"])

# Lets the app tell an older server apart from one that speaks its dialect.
API_VERSION = 2


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


class PushConfig(BaseModel):
    """How this server expects to be able to notify the app, if at all.

    The app configures itself from this instead of baking a provider in, which
    is what lets one build work against a self-hosted server that sends nothing
    and a hosted one that does. When ``provider`` is "none" the app must not
    initialise any push SDK at all - there is nothing to subscribe to.
    """

    enabled: bool = False
    provider: str = "none"


class MobileSession(BaseModel):
    token: str
    portal_slug: str
    client_id: uuid.UUID
    user_id: uuid.UUID | None = None
    user_name: str = ""
    branding: MobileBranding
    push: PushConfig = Field(default_factory=PushConfig)
    api_version: int = API_VERSION


class DeviceRegistration(BaseModel):
    # Whatever the configured provider needs to reach this install.
    token: str = Field(min_length=8, max_length=400)
    provider: str = Field(default="", max_length=40)
    platform: str = Field(default="", max_length=20)


class DeviceOut(BaseModel):
    registered: bool
    provider: str


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


def _session_for(client: Client, agency: Agency, user: PortalUser | None) -> MobileSession:
    return MobileSession(
        token=create_portal_token(str(client.id), client.portal_slug, str(user.id) if user else None),
        portal_slug=client.portal_slug,
        client_id=client.id,
        user_id=user.id if user else None,
        user_name=(user.name or user.email) if user else "",
        branding=_branding(client, agency),
        push=PushConfig(enabled=push_enabled(), provider=configured_provider()),
    )


@router.post("/sign-in", response_model=MobileSession, dependencies=[Depends(login_rate_limit)])
def mobile_sign_in(payload: MobileSignInRequest, db: Session = Depends(get_db)):
    """Resolve a portal from its credentials and issue a bearer token.

    An e-mail does not identify a portal on its own, so every candidate is
    checked against the password and the first that verifies wins. The failure
    response never says whether the address exists.
    """
    email = payload.email.lower()

    users = db.scalars(
        select(PortalUser).where(PortalUser.email == email, PortalUser.is_active.is_(True))
    ).all()
    for user in users:
        if not verify_password(payload.password, user.password_hash):
            continue
        client = db.get(Client, user.client_id)
        if not client or not client.portal_enabled:
            continue
        agency = db.get(Agency, client.agency_id)
        if agency:
            return _session_for(client, agency, user)

    # Installs that never created portal users still sign in with the single
    # login the client carries.
    legacy = db.scalars(
        select(Client).where(Client.portal_enabled.is_(True), Client.portal_email.is_not(None))
    ).all()
    for client in legacy:
        if (client.portal_email or "").lower() != email:
            continue
        if not client.portal_password_hash or not verify_password(payload.password, client.portal_password_hash):
            continue
        agency = db.get(Agency, client.agency_id)
        if agency:
            return _session_for(client, agency, None)

    raise HTTPException(status_code=401, detail="Incorrect e-mail or password")


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _resolve(db: Session, authorization: str | None) -> tuple[Client, Agency, PortalUser | None, str]:
    token = _bearer(authorization)
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
    user = None
    raw_user = payload.get("pu")
    if raw_user:
        try:
            user = db.get(PortalUser, uuid.UUID(raw_user))
        except (ValueError, TypeError):
            user = None
        # A user who was removed or disabled loses the session with them.
        if user and (user.client_id != client.id or not user.is_active):
            raise HTTPException(status_code=401, detail="This account is no longer active")
    return client, agency, user, token


@router.get("/session", response_model=MobileSession)
def mobile_session(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Re-check a stored token on launch and return fresh branding."""
    client, agency, user, token = _resolve(db, authorization)
    session = _session_for(client, agency, user)
    # Keep the token the caller already holds rather than rotating it on launch.
    session.token = token
    return session


@router.post("/devices", response_model=DeviceOut)
def register_device(
    payload: DeviceRegistration,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Record where to reach this install.

    Keyed on the token, so reinstalling or signing in as someone else moves the
    existing row rather than leaving behind a device that would ring for the
    wrong person.

    A server that sends nothing still accepts the registration and reports what
    it is configured with, so the app can be honest about it without needing a
    separate capability call.
    """
    client, _agency, user, _token = _resolve(db, authorization)
    device = db.scalar(select(PushDevice).where(PushDevice.token == payload.token))
    if device:
        device.client_id = client.id
        device.portal_user_id = user.id if user else None
        device.provider = payload.provider or device.provider
        device.platform = payload.platform or device.platform
        device.last_seen_at = now_utc()
    else:
        device = PushDevice(
            client_id=client.id,
            portal_user_id=user.id if user else None,
            token=payload.token,
            provider=payload.provider or configured_provider(),
            platform=payload.platform,
        )
        db.add(device)
    db.commit()
    return DeviceOut(registered=push_enabled(), provider=configured_provider())


@router.delete("/devices/{device_token}", status_code=status.HTTP_204_NO_CONTENT)
def forget_device(
    device_token: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Stop notifying this install, on sign-out."""
    client, _agency, _user, _token = _resolve(db, authorization)
    device = db.scalar(
        select(PushDevice).where(PushDevice.token == device_token, PushDevice.client_id == client.id)
    )
    if device:
        db.delete(device)
        db.commit()
    return None
