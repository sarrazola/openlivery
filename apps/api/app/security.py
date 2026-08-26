import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet

from .config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def create_portal_token(client_id: str, portal_slug: str, portal_user_id: str | None = None) -> str:
    """Session for a client's portal.

    ``sub`` stays the client, so tokens issued before portal users existed keep
    resolving. ``pu`` names the person when there is one, which is what lets a
    reply be attributed and a device be tied to someone rather than to the whole
    business.
    """
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload: dict = {"sub": client_id, "portal_slug": portal_slug, "type": "portal", "exp": expires}
    if portal_user_id:
        payload["pu"] = portal_user_id
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_portal_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        if payload.get("type") != "portal":
            return None
        return payload
    except jwt.PyJWTError:
        return None


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().encryption_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:3]}••••••••{value[-4:]}"
