from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..models import User
from ..schemas import ModelCatalogOut
from ..services import model_catalog
from ..services.model_catalog import get_model, list_models


router = APIRouter(prefix="/catalog", tags=["Model catalog"])


@router.get("/available")
def available_models(user: User = Depends(get_current_user)):
    """Model ids this workspace can pick, per provider and capability. A
    module call on purpose, so a deployment can narrow the answer."""
    return model_catalog.available_models()


@router.get("/models", response_model=list[ModelCatalogOut])
def list_catalog_models(user: User = Depends(get_current_user)):
    return [asdict(model) for model in list_models()]


@router.get("/models/{model_id:path}", response_model=ModelCatalogOut)
def get_catalog_model(model_id: str, user: User = Depends(get_current_user)):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found in the catalog")
    return asdict(model)
