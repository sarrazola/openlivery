import re

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Agency, User
from ..schemas import AgencyOut, AgencyUpdate
from ..slugs import slugify


router = APIRouter(prefix="/agency", tags=["Agency"])
MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}


def present(agency: Agency) -> AgencyOut:
    """The agency plus the deployment's store links, which live in settings
    rather than on the row: every deployment publishes one app, not one per
    agency."""
    settings = get_settings()
    out = AgencyOut.model_validate(agency)
    out.ios_app_url = (settings.portal_ios_app_url or "").strip() or None
    out.android_app_url = (settings.portal_android_app_url or "").strip() or None
    return out


@router.get("", response_model=AgencyOut)
def get_agency(user: User = Depends(get_current_user)):
    return present(user.agency)


@router.patch("", response_model=AgencyOut)
def update_agency(
    payload: AgencyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agency = user.agency
    values = payload.model_dump(exclude_unset=True)
    if "slug" in values and values["slug"]:
        candidate = slugify(values["slug"])
        if db.scalar(select(Agency).where(Agency.slug == candidate, Agency.id != agency.id)):
            raise HTTPException(status_code=409, detail="That identifier is already in use")
        values["slug"] = candidate
    if "brand_color" in values and not re.fullmatch(r"#[0-9a-fA-F]{6}", values["brand_color"] or ""):
        raise HTTPException(status_code=400, detail="The color must use the #075985 format")
    for key, value in values.items():
        setattr(agency, key, value)
    db.commit()
    db.refresh(agency)
    return present(agency)


@router.post("/logo", response_model=AgencyOut)
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail="Use a PNG, JPG, WebP or SVG logo")
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="The logo exceeds the 2 MB limit")
    user.agency.logo_data = data
    user.agency.logo_mime = file.content_type
    db.commit()
    db.refresh(user.agency)
    return present(user.agency)


@router.get("/logo")
def get_logo(user: User = Depends(get_current_user)):
    agency = user.agency
    if not agency.logo_data or not agency.logo_mime:
        raise HTTPException(status_code=404, detail="The agency does not have a logo yet")
    return Response(content=agency.logo_data, media_type=agency.logo_mime, headers={"Cache-Control": "no-store"})


@router.delete("/logo", status_code=status.HTTP_204_NO_CONTENT)
def delete_logo(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.agency.logo_data = None
    user.agency.logo_mime = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
