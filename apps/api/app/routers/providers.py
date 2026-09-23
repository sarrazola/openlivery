from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ProviderCredential, User
from ..schemas import ProviderKeyUpdate, ProviderOut
from ..security import decrypt_secret, encrypt_secret, mask_secret
from ..services.ai import test_provider
from ..services.providers import PROVIDERS, SUPPORTED, base_url_for, credential_source


router = APIRouter(prefix="/providers", tags=["AI providers"])


def _require_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown provider")


def _credential(db: Session, user: User, provider: str) -> ProviderCredential | None:
    return db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.agency_id == user.agency_id,
            ProviderCredential.provider == provider,
        )
    )


def _out(provider: str, credential: ProviderCredential | None, source: str | None = None) -> dict:
    # "configured" is what the UI asks before letting an agent reply: true when
    # the agency stored a key, and also when the deployment lends one.
    source = source or ("agency" if credential is not None else "none")
    return {
        "provider": provider,
        "label": PROVIDERS[provider]["label"],
        "configured": source != "none",
        "source": source,
        "api_key_masked": mask_secret(decrypt_secret(credential.encrypted_api_key)) if credential else "",
    }


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    by_provider = {c.provider: c for c in db.scalars(
        select(ProviderCredential).where(ProviderCredential.agency_id == user.agency_id)
    ).all()}
    return [
        _out(provider, by_provider.get(provider), credential_source(db, user.agency_id, provider))
        for provider in SUPPORTED
    ]


@router.put("/{provider}", response_model=ProviderOut)
def set_provider_key(provider: str, payload: ProviderKeyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if credential:
        credential.encrypted_api_key = encrypt_secret(payload.api_key)
    else:
        credential = ProviderCredential(agency_id=user.agency_id, provider=provider, encrypted_api_key=encrypt_secret(payload.api_key))
        db.add(credential)
    db.commit()
    return _out(provider, credential)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_key(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if credential:
        db.delete(credential)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{provider}/test")
async def test_provider_key(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if not credential:
        raise HTTPException(status_code=400, detail="No API key configured for this provider")
    return await test_provider(provider, base_url_for(provider), decrypt_secret(credential.encrypted_api_key))


@router.post("/{provider}/validate")
async def validate_provider_key(provider: str, payload: ProviderKeyUpdate, user: User = Depends(get_current_user)):
    """Verify a raw key against the provider before it is stored."""
    _require_provider(provider)
    return await test_provider(provider, base_url_for(provider), payload.api_key)
