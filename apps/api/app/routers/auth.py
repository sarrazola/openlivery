from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Agency, User
from ..ratelimit import login_rate_limit
from ..schemas import LoginRequest, RegisterRequest, UserOut
from ..security import create_access_token, hash_password, verify_password
from ..slugs import unique_slug


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=create_access_token(str(user.id)),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_minutes * 60,
        path="/",
    )


def _registration_open(db: Session) -> bool:
    if get_settings().allow_multi_agency:
        return True
    return db.scalar(select(Agency.id).limit(1)) is None


@router.get("/status", dependencies=[Depends(login_rate_limit)])
def auth_status(db: Session = Depends(get_db)):
    # Public: lets the login page decide between first-run setup (no agency
    # yet) and sign-in only (single-agency instance already configured).
    has_agency = db.scalar(select(Agency.id).limit(1)) is not None
    return {
        "needs_setup": not has_agency,
        "registration_open": get_settings().allow_multi_agency or not has_agency,
    }


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(login_rate_limit)],
)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if not _registration_open(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed on this instance",
        )
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    agency_name = payload.agency_name.strip()
    agency = Agency(name=agency_name, slug=unique_slug(db, Agency, "slug", agency_name))
    user = User(
        agency=agency,
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut, dependencies=[Depends(login_rate_limit)])
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    _set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie("access_token", path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
